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

from Logger import Logger
from proxyHelpers import *


class PersistentProxyClient():
	"""
	since twisted's HTTPClient class does not support persistent HTTP connections, a custom class had 
	to be created. This uses an HTTP connection pool and spawns a deferred agent for each HTTP request to 
	the target server
	"""

	def __init__(self,host,rest,father,responseWriter,cid=None,callback=None):
		self.father = father
		self.host = host
		self.rest = rest
		self.pool = HTTPConnectionPool(reactor) #the connection to be persisted
		self.agent = Agent(reactor, pool=self.pool)
		self.id = cid
		self.index = 0
		self.callback = callback 
		self.responseWriter = responseWriter
		self.headersWritten = False
		self.log = Logger()
		self.chunk_size = 0
		
		if 'http://' not in self.host:
			self.host = 'http://{}'.format(self.host)

		self.log.logic("Dispatched for uri: {}".format(self.host + self.rest))



	def getChunk(self,range):
		"""issue the HTTP GET request for the range of the file specified"""
		if not range:
			self.log.warning("no range given for getChunk, exiting")
			return None

		self.log.info("getting chunk: {}".format(range))
		self.chunk_size = range[1] - range[0]
		defered = self.agent.request(
			'GET',
			self.host + self.rest,
			Headers({
				'Range' : [httpRange(range)]
				}),
			None)
		defered.addCallback(self.responseRecieved)
		defered.addErrback(deferedError)
		return defered

	def responseRecieved(self,response):
		if response.code > 206: #206 is the code returned for http range responses
	 		self.log.warning("error with response from server({})".format(response.code))
	 		self.father.endSession()
	 		return None
	 	else:
	 		self.father.handleResponseCode(response.code)

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