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


import urlparse
from urllib import quote as urlquote

import sys
import random
from copy import deepcopy
import urllib2

from proxyHelpers import *


class RequestBodyReciever(Protocol):
	"""needed to actually send the response from a server (because of the way the response object works).
	Passes any data it recieves to the Peer writer. This is an unfortunate side effect of the twisted 
	architecture. A response object cannot pass it's body onwards without the use of this mitigating class"""

	def __init__(self,peerHelper,defered):
		self.peerHelper = peerHelper #reference to peerHelper class that holds an 
									 #open TCP connection with the peer
		self.recvd = 0
		self.defered = defered #placeholder for a deferred callback (incase one is eventually needed)

	def dataReceived(self,bytes):
		self.recvd += len(bytes)
		self.peerHelper.father.transport.write(bytes)


	def connectionLost(self,reason):
		self.defered.callback(None)

class PersistentProxyClient():
	"""
	since twisted's HTTPClient class does not support persistent HTTP connections, a custom class had 
	to be created. This uses an HTTP connection pool and spawns a deferred agent for each HTTP request to 
	the target server
	"""

	def __init__(self,uri,father,responseWriter,cid=None,callback=None):
		self.father = father
		self.uri = uri
		self.pool = HTTPConnectionPool(reactor) #the connection to be persisted
		self.agent = Agent(reactor, pool=self.pool)
		self.id = cid
		self.index = 0
		self.callback = callback 
		self.responseWriter = responseWriter
		self.headersWritten = False
		
		if 'http://' not in self.uri:
			self.uri = 'http://' + self.uri

		print self.uri



	def getChunk(self,range):
		"""issue the HTTP GET request for the range of the file specified"""
		if not range:
			print("no range given for getChunk, exiting")
			return None

		print("getting chunk: {}".format(range))
		self.index = range[0]
		defered = self.agent.request(
			'GET',
			self.uri,
			Headers({
				'Range' : [httpRange(range)]
				}),
			None)
		defered.addCallback(self.responseRecieved)
		return defered

	def responseRecieved(self,response):

		if response.code > 206: #206 is the code returned for http range responses
	 		print("error with response from server({})".format(response.code))

	 	finished = Deferred()
	 	if not self.headersWritten:
	 		for key,val in list(response.headers.getAllRawHeaders()):
	 			self.father.handleHeader(key,val)
	 		self.headersWritten = True

	 	if self.callback:
	 		finished.addCallback(self.callback)

	 	recvr = self.responseWriter(self,finished) 
		response.deliverBody(recvr)
		return finished