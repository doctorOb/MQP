from twisted.web import proxy, http
from twisted.web.client import Agent, HTTPConnectionPool, _parse
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

from proxyHelpers import *
from RecordKeeper import *
import PybaProx



def repeatCallback(client):
	range = client.downloadPool.getNextChunk(client.id)
	log = Logger()
	if range != None:
		client.getChunk(range)
	else:
		log.info("no new data to retrieve")

class RequestBodyReciever(Protocol):
	"""
	needed to actually send the response from a server (because of the way the response object works).
	Passes any data it recieves to the Peer writer. This is an unfortunate side effect of the twisted 
	architecture. A response object cannot pass it's body onwards without the use of this mitigating class
	"""

	def __init__(self,client,defered,doCallback=True):
		self.client = client #reference to client class that holds an 
									 #open TCP connection with the peer
		self.recvd = 0
		self.defered = defered #placeholder for a deferred callback (in-case one is eventually needed)
		self.doCallback = doCallback


	def dataReceived(self,bytes):
		self.recvd += len(bytes)
		self.client.timer.reset()
		self.client.downloadPool.appendData(self.client,bytes)

	def connectionLost(self,reason):
		if self.doCallback:
			repeatCallback(self.client)
		else:
			print "connection terminated ({})".format(reason)

class PeerHandler():
	"""maintains a Persistent TCP connection with the supplied neighbor. Talks to the neighbor over the new
	ppm API via HTTP deferreds. This class is meant to be instantiated for each session."""

	def __init__(self,neighbor,id,target,downloadPool):
		self.pool = HTTPConnectionPool(reactor) #the connection to be persisted
		self.agent = Agent(reactor, pool=self.pool)
		self.responseWriter = RequestBodyReciever
		self.peer_ip = neighbor.ip
		self.target = target
		self.downloadPool = downloadPool #the calling download pool that spawned the handler
		self.id = id
		self.neighbor = neighbor
		self.index = 0
		self.recvd = 0
		self.data_stop = 0
		self.verified = False
		self.trust_level = 0
		self.timer = SlidingWindow(10)
		self.assigned_chunk = None
		self.log = Logger()
		self.records = SessionRecord(neighbor.ip)
		self.records.new(target=target,req_size=downloadPool.requestSize)

	def _url(self,path):
		return 'http://{}:{}/{}'.format(self.peer_ip,PybaProx.__opts.peer_port,path)

	def _sign(self,target):
		hash = MD5.new('{}-{}'.format(IP,target)).digest()
		return self.downloadPool.key.sign(hash,'')


	def _baseHeaders(self):
		"""return a dictionary of the base headers needed in a peer request"""
		headers = Headers()
		headers.addRawHeader('target',self.target)
		headers.addRawHeader('signature',self._sign(target))

		return headers

	def _responseHeaders(self,response):
		"""process the headers from a response and return them as a dict"""
		headers = {}
		for key,val in response.headers.getAllRawHeaders():
			headers[key] = val
		return headers

	def _doRequest(self,url,headers,doCallback=True):
		defered = self.agent.request(
			'GET',
			url,
			headers,
			None)
		defered.addCallback(self.responseRecieved)
		self.checkTimeout()
		return defered

	def checkTimeout():
		"""check if a timeout has occured"""
		if self.timer.timedout():
			self.downloadPool.terminatePeer(self)

		reactor.callLater(1,self.checkTimeout)

	def getInit(self):
		"""Hit a peer with an init request for a session at the supplied url"""
		headers = self._baseHeaders()
		return self._doRequest(self._url('init'),headers)


	def getChunk(self,range):
		"""Hit a peer with a /chunk request for the range specified"""
		headers = self._baseHeaders()
		self.assigned_chunk = range
		headers.addRawHeader('Range',httpRange(range))

		return self._doRequest(self._url('chunk'),headers)

	def terminateConnection(self):
		"""
			called when the handler wishes to end its session,
			usually by the wish of the peer. This involves removing 
			the instance from the downloadPool instance's records.
		"""
		self.records.timeout()
		self.records.save()

	def responseRecieved(self,response):
		"""
			Hook in here before setting up the response body reader. 
			Look at headers to determine if the signature is valid,
			what the peer is sending back, ect.
		"""
		if response.code == 400: #peer wises to terminate it's involvement
			#add makeup chunk to downloadPool's buffers
			self.terminateConnection()
			return 

		self.timer.reset()
	 	headers = self._responseHeaders(response)

	 	finished = Deferred()
	 	recvr = self.responseWriter(self,finished,doCallback=True) 
		response.deliverBody(recvr)

		return finished