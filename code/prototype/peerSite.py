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


import urlparse
from urllib import quote as urlquote

import sys
import random
from copy import deepcopy
import urllib2

sys.path.append('proxyHelpers.py')
from proxyHelpers import *


class RequestBodyReciever(Protocol):
	"""
	needed to actually send the response from a server (because of the way the response object works).
	Passes any data it recieves to the Peer writer. This is an unfortunate side effect of the twisted 
	architecture. A response object cannot pass it's body onwards without the use of this mitigating class
	"""

	def __init__(self,peerHelper,defered):
		self.request = request
		self.recvd = 0
		self.defered = defered #placeholder for a deferred callback (incase one is eventually needed)

	def dataReceived(self,bytes):
		self.recvd += len(bytes)
		request.write(bytes) #consider passing self.recvd to save on len calculation in PPM_DATA

	def connectionLost(self,reason):
		self.request.finish()

		
class PeerWorker():
	"""a modified variant of the persistent HTTP client class, optimized to work with the download pool 
	by using PPM headers"""

	def __init__(self):
		self.pool = HTTPConnectionPool(reactor) #the connection to be persisted
		self.agent = Agent(reactor, pool=self.pool)
		self.responseWriter = RequestBodyReciever

	def getChunk(self,request):
		"""issue the HTTP GET request for the range of the file specified"""
		headers = dict()
		for key,val in list(request.headers.getAllRawHeaders()):
	 		headers[key] = val

		defered = self.agent.request(
			'GET',
			headers['uri'],
			Headers({
				'Range' : headers['Range']
				}),
			None)
		defered.addCallback(self.responseRecieved,request)
		return defered

	def responseRecieved(self,request,response):

		if response.code > 206: #206 is the code returned for http range responses
	 		print("error with response from server")

	 	finished = Deferred()

	 	recvr = self.responseWriter(request,finished) 
		response.deliverBody(recvr)
		return finished

class peerHelper(Protocol):
	"""
	this class manages the connection between the feeding client and the server. This acts 
	as a control layer that receiving data requests from the client and handing them to HTTP deferred
	that talk to the actual server. The deferreds will write their data back to the client through a reference 
	to this class's transport object
	"""

	def __init__(self):
		self.uri = None
		self.PeerClientFactory = None
		self.headers = {}
		self.rest = None
		self.todo = []
		self.client = PeerWorker()



	def handleHeader(self, key, value):
		pass

	def handleResponseCode(self, version, code, message):
		pass


	def connectionMade(self):
		print('recieved connection')

	def dataReceived(self,data):
		message = peerProtocolMessage(data)
		self.handleMessage(message)

	def handleMessage(self,message):
		print('got message',message.data)

		if message == None:
			return
		if message.type == 'END':
			self.connectionLost()
			print("done")
			return
		if message.type == 'INIT':
			self.transport.write(PPM_ACCEPT())
			self.uri = message.uri
			parsed = urlparse.urlparse(self.uri)
			self.headers['host'] = parsed[1]
			self.rest = urlparse.urlunparse(('','') + parsed[2:])
			self.client = PeerWorker(self.uri,self,RequestBodyReciever)
			return
		if message.type == 'CHUNK' and message.range:
			self.res_len = message.getChunkSize()
			self.headers['Range'] = httpRange(message.range)

			print('uri:{} range: {}'.format(self.uri,self.headers['Range']))
			self.client.getChunk(message.range)