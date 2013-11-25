"""
peerDaemon.py runs on each router, and listens for messages from peer routers who wish to coordinate
bandwidth aggregation. 
"""

from twisted.internet import reactor
from twisted.internet.defer import Deferred, DeferredList
from twisted.internet.protocol import Protocol, Factory
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers
from twisted.web import proxy, http
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.internet.protocol import Protocol, Factory, ClientFactory, ClientCreator
from twisted.python import log
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.web.http import HTTPClient, Request, HTTPChannel
from twisted.internet import reactor
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.web.resource import NoResource


import urlparse
from urllib import quote as urlquote

import sys
import random
from copy import deepcopy
import urllib2

sys.path.append('proxyHelpers.py')
from proxyHelpers import *


class PeerHelper():

	def __init__(self):
		self.isBuisy = False
		self.neighbors = {
			'127.0.0.1' : Neighbor('127.0.0.1')
		}
		self.connections = []
		self.open_connections = 0
		self.worker = PeerWorker()

	def addConnection(self,request):
		"""add a client to the connection"""
		ip = request.getClientIP()
		self.connections.append(request)
		self.open_connections += 1

	def handleChunk(self,request):
		self.worker.getChunk(request)



class RequestBodyReciever(Protocol):
	"""
	needed to actually send the response from a server (because of the way the response object works).
	Passes any data it recieves to the Peer writer. This is an unfortunate side effect of the twisted 
	architecture. A response object cannot pass it's body onwards without the use of this mitigating class
	"""

	def __init__(self,request,defered):
		self.request = request
		self.recvd = 0
		self.defered = defered #placeholder for a deferred callback (incase one is eventually needed)

	def dataReceived(self,bytes):
		print bytes
		self.recvd += len(bytes)
		self.request.write(bytes) #consider passing self.recvd to save on len calculation in PPM_DATA

	def connectionLost(self,reason):
		self.request.finish()

def _headers(request):
	"""return a dict of all request headers"""
	headers = dict()
	for key,val in request.requestHeaders.getAllRawHeaders():
		headers[key] = val
	return headers

		
class PeerWorker():
	"""a modified variant of the persistent HTTP client class, optimized to work with the download pool 
	by using PPM headers"""

	def __init__(self):
		self.pool = HTTPConnectionPool(reactor) #the connection to be persisted
		self.agent = Agent(reactor, pool=self.pool)
		self.responseWriter = RequestBodyReciever

	def getChunk(self,request):
		"""issue the HTTP GET request for the range of the file specified"""
		try:
			headers = _headers(request)
			range = headers['Range']
			uri = headers['Target'][0] + ':80'
		except:
			request.setResponseCode(400) #bad request
			request.setHeader('Reason','INVALID')
			request.write(" ")#send the headers
			request.finish()
			return

		print uri,range

		request.setResponseCode(202) #Accepted
		defered = self.agent.request(
			'GET',
			uri,
			Headers({
				'Range' : range
				}),
			None)
		defered.addCallback(self.responseRecieved,request)
		return defered

	def responseRecieved(self,response,request):

		print response.code
		if response.code > 206: #206 is the code returned for http range responses
	 		print("error with response from server")

	 	finished = Deferred()
	 	recvr = self.responseWriter(request,finished) 
		response.deliverBody(recvr)
		return finished


class InitRequest(Resource):
	"""handles an INIT peer message"""

	def __init__(self,peerHelper):
		Resource.__init__(self)
		self.ph = peerHelper

	def render_GET(self,request):
		if self.ph.isBuisy:
			return 'DECLINE'
		else:
			self.ph.addConnection(request)
			headers = request.getAllHeaders()
			return 'ip:{}'.format(request.getClientIP())


class ChunkRequest(Resource):
	"""handles a CHUNK peer message"""

	def __init__(self,peerHelper):
		Resource.__init__(self)
		self.ph = peerHelper

	def render_GET(self,request):
		self.ph.handleChunk(request)
		return NOT_DONE_YET

class Dispatcher(Resource):
	"""the actual twisted resource that catches all requests to the router. dispatches them 
	to the appropriate handler, and maintains session information"""
	def __init__(self,peerHelper):
		Resource.__init__(self)
		self.ph = peerHelper

	def getChild(self,name,request):
		print('dispatching request to {} from {}'.format(name,request.getClientIP()))
		if name == 'init':
			return InitRequest(self.ph)
		elif name == 'chunk':
			return ChunkRequest(self.ph)
		else:
			return NoResource()

if __name__ == '__main__':
	ph = PeerHelper()
	root = Dispatcher(ph)
	factory = Site(root)
	reactor.listenTCP(8080, factory)
	reactor.run()