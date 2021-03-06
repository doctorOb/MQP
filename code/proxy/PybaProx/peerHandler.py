from twisted.web import proxy, http
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers
from twisted.internet import reactor, defer
from twisted.internet.protocol import Protocol, Factory, ClientFactory, ClientCreator
from twisted.python import log
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.web.http import HTTPClient, Request, HTTPChannel


from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.task import deferLater

import urlparse
from urllib import quote as urlquote

import sys
import random
import urllib2
import time
from itertools import chain

from Crypto.PublicKey import RSA

from proxyHelpers import *
from RecordKeeper import *
from Logger import Logger



class Dummy(Protocol):
	"""
	An empty responseReciever class that does nothing. If a response object is not 'delivered' to
	this class, then subsequent responses are messed up (blame twisted).
	"""
	def __init__(self):
		pass
	def dataReceived(self,bytes):
		pass
	def connectionLost(self,reason):
		pass

class PH_RequestBodyReciever(Protocol):
	"""
	needed to actually send the response from a server (because of the way the response object works).
	Passes any data it recieves to the Peer writer. This is an unfortunate side effect of the twisted 
	architecture. A response object cannot pass it's body onwards without the use of this mitigating class
	"""

	def __init__(self,handler,range):
		self.handler = handler #reference to handler class that holds an open TCP connection with the peer
		self.log = Logger()
		self.size = range[1] - range[0]
		self.start = range[0]
		self.recvd = 0

	def repeatCallback(self):
		try:
			range = self.handler.downloadPool.getNextChunk(self.handler.id)
			if range != None:
				self.handler.getChunk(range)
			else:
				pass#self.handler.terminateConnection()
		except:
			raise
			self.log.warning('error in repeat callback')

	def dataReceived(self,bytes):
		self.handler.timer.reset()
		self.recvd += len(bytes)
		self.handler.downloadPool.appendData(self.handler,self.start,bytes)

	def connectionLost(self,reason):
		if self.recvd < self.size:
			#server sent back a splash page or something other then the desired content
			self.handler.downloadPool.endSession("Mismatched response length from peer")
			return
		self.log.info("lost connection with peer (request finished)")
		self.repeatCallback()

class PeerHandler():
	"""maintains a Persistent TCP connection with the supplied neighbor. Talks to the neighbor over the new
	ppm API via HTTP deferreds. This class is meant to be instantiated for each session."""

	def __init__(self,neighbor,id,target,downloadPool):
		self.configs = reactor.configs
		self.pool = HTTPConnectionPool(reactor) #the connection to be persisted
		self.agent = Agent(reactor, pool=self.pool)
		self.responseWriter = PH_RequestBodyReciever
		self.peer_ip = neighbor.ip
		self.target = target #uri of the target resource (requested on behalf of the client)
		self.downloadPool = downloadPool #the calling download pool that spawned the handler
		self.id = id
		self.neighbor = neighbor
		self.index = 0
		self.recvd = 0
		self.data_stop = 0
		self.verified = False
		self.active = False #set to true when we receive a response
		self.trust_level = 0
		self.timer = SlidingWindow(10)
		self.assigned_chunk = None
		self.log = Logger()
		self.records = SessionRecord(neighbor.ip)
		self.records.new(target=target,req_size=downloadPool.requestSize)
		self._signature = self._sign(self.target)

	def _url(self,path):
		return 'http://{}:{}/{}'.format(self.peer_ip,self.configs.peer_port,path)

	def _sign(self,target):
		msg = '{}-{}'.format(self.configs.ip,target)
		return self.configs.key.sign(msg)[0]


	def _baseHeaders(self):
		"""return a dictionary of the base headers needed in a peer request"""
		headers = Headers()
		headers.addRawHeader('Target',self.target)
		headers.addRawHeader('Signature',self._signature)

		return headers

	def _doRequest(self,url,headers,doCallback=True):
		defered = self.agent.request(
			'GET',
			url,
			headers,
			None)
		defered.addCallback(self.responseRecieved)
		defered.addErrback(deferedError)
		return defered

	def checkTimeout(self,tmp=None):
		"""check if a timeout has occured"""
		if self.timer.timedout():
			self.terminateConnection()

		reactor.callLater(1,self.checkTimeout,None)

	def getInit(self):
		"""Hit a peer with an init request for a session at the supplied url"""
		headers = self._baseHeaders()
		return self._doRequest(self._url('init'),headers)


	def getChunk(self,range):
		"""Hit a peer with a /chunk request for the range specified"""
		headers = self._baseHeaders()
		self.assigned_chunk = range
		headers.addRawHeader('Range',httpRange(range))
		self.log.info("Handler dispatching {} to peer".format(range))

		return self._doRequest(self._url('chunk'),headers)

	def terminateConnection(self):
		"""
			called when the handler wishes to end its session,
			usually by the wish of the peer. This involves removing 
			the instance from the downloadPool instance's records.
		"""
		self.records.timeout()
		self.records.save()
		self.downloadPool.terminatePeer(self)

	def begin(self):
		"""called when a peer aggrees to participate in an aggregation session"""
		self.active = True
		chunk = self.downloadPool.getNextChunk(self.id)
		if chunk:
			return self.getChunk(chunk)

	def end(self,code):
		"""called when a peer sends an errorful response code"""
		self.log.logic("Terminating connection with peer (error: {})".format(code))
		self.terminateConnection() 

	def responseRecieved(self,response):
		"""
			Hook in here before setting up the response body reader. 
			Look at headers to determine if the signature is valid,
			what the peer is sending back, ect.
		"""
		self.log.info("Received reply from peer")

		if response.code > 206: #peer wises to terminate it's involvement
			#add makeup chunk to downloadPool's buffers
			return self.end(response.code)

		if not self.active:
			dummyRecr = Dummy()
			response.deliverBody(dummyRecr)
			return self.begin()

		self.timer.reset()
	 	headers = headersFromResponse(response)
	 	try:
		 	recvr = self.responseWriter(self,range=self.assigned_chunk)
			response.deliverBody(recvr)
		except:
			self.log.warning("error setting up reciever")
