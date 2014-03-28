"""
peerDaemon.py runs on each router, and listens for messages from peer routers who wish to coordinate
bandwidth aggregation. 
"""

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.web.http_headers import Headers
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.internet.protocol import Protocol, Factory
from twisted.python import log
from twisted.web.resource import Resource
from twisted.web.http import Request
from twisted.web.server import Site
from twisted.web.server import NOT_DONE_YET
from twisted.web.resource import NoResource

from Crypto.Hash import MD5
from Crypto.PublicKey import RSA


import urlparse
from urllib import quote as urlquote

import sys
import random
from copy import deepcopy
import urllib2

from proxyHelpers import *
from Logger import Logger

class PeerHelper():

	def __init__(self):
		self.isBuisy = False
		self.configs = reactor.configs
		self.neighbors = self.configs.neighbors
		self.connections = []
		self.open_connections = 0
		self.worker = PeerWorker()
		self.log = Logger()

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
		self.log = Logger()

	def dataReceived(self,bytes):
		self.recvd += len(bytes)
		self.log.info("writing {} bytes to peer".format(len(bytes)))
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
	"""
	a modified variant of the persistent HTTP client class, optimized to work with the download pool 
	by using PPM headers.
	"""

	def __init__(self):
		self.pool = HTTPConnectionPool(reactor) #the connection to be persisted
		self.agent = Agent(reactor, pool=self.pool)
		self.responseWriter = RequestBodyReciever
		self.log = Logger()

	def getChunk(self,request):
		"""issue the HTTP GET request for the range of the file specified"""
		try:
			headers = _headers(request)
			range = headers['Range']
			uri = headers['Target'][0]# + ':80'
		except:
			request.setResponseCode(400) #bad request
			request.setHeader('Reason','INVALID')
			request.write(" ")#send the headers
			request.finish()
			return

		self.log.logic("{}:{}".format(uri,range))

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

		self.log.info("response from resource with code {}".format(response.code))
		if response.code > 206: #206 is the code returned for http range responses
	 		self.log.warn("error with response from server")

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
			self.ph.log.logic("added peer client to active connections")
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
	"""
	the actual twisted resource that catches all requests to the router. dispatches them 
	to the appropriate handler, and maintains session information
	"""
	def __init__(self,peerHelper):
		Resource.__init__(self)
		self.ph = peerHelper
		self.configs = reactor.configs
		self.neighbors = self.configs.neighbors
		self.log = Logger()

	def verify_signature(self,request):
		"""
		verify the signature of the request, to make sure it came form someone in our network
		"""
		headers = _headers(request)
		ip = request.getClientIP()
		try:
			to_hash = "{}-{}".format(ip,headers['target'])
			signature = headers['signature']

			client_key = self.neighbors[ip].key
		except:
			self.log.warn("couldn't create hash for request from {}".format(ip))
			return False

		hash = md5hash(to_hash)
		if client_key.verify(hash,signature):
			self.log.logic("verified signature")
			return True
		else:
			self.log.logic("invalid signature")
			return False


	def getChild(self,name,request):
		self.log.info('dispatching request to {} from {}'.format(name,request.getClientIP()))
		if name == 'init':
			return InitRequest(self.ph)
		elif name == 'chunk':
			return ChunkRequest(self.ph)
		else:
			return NoResource()
