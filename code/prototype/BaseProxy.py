from twisted.web import proxy, http
from twisted.web.client import Agent, HTTPConnectionPool, _parse
from twisted.web.http_headers import Headers
from twisted.internet import reactor
from twisted.internet.protocol import Protocol, Factory, ClientFactory, ClientCreator
from twisted.web.resource import Resource
from twisted.web.http import HTTPClient, Request, HTTPChannel

import urlparse
from urllib import quote as urlquote

import sys
import random
import urllib2
import time

sys.path.append('proxyHelpers.py')
from proxyHelpers import *
from DLP import DownloadPool
from PyBAP import *



class ProxyClient(HTTPClient):
	_finished = False
	bytes_recvd = 0

	def __init__(self, command, rest, version, headers, data, father):
		self.father = father
		self.command = command
		self.rest = rest

		if "proxy-connection" in headers:
			del headers["proxy-connection"]
		headers["connection"] = "close"
		headers.pop('keep-alive', None)
		self.headers = headers
		self.data = data
		self.stop = False
		self.log = Logger()

	def connectionMade(self):
		self.log.info('successful TCP connection established with target server')
		self.sendCommand(self.command, self.rest)
		for header, value in self.headers.items():
			self.sendHeader(header,value)
			if header == 'Range':
				self.log.parseHostInfo("range request:{}".format(value))
		self.endHeaders()
		self.transport.write(self.data)

	def handleStatus(self, version, code, message):
		self.father.setResponseCode(int(code),message)

	def handleHeader(self, key, value):
		"""
		Pass the headers to the father request object (which writes to the client)
		If the content-length is larger then the minimum file size, stop the request
		and start over with a download pool
		"""
		if key == 'Content-Length' and int(value) > MINIMUM_FILE_SIZE:
			self.log.logic('using two streams')
			pool = DownloadPool(int(value),self.father)
			pool.queryPeers()
			self.stop = True
		if key.lower() in ['server', 'date', 'content-type']:
			self.father.responseHeaders.setRawHeaders(key, [value])
		else:
			self.father.responseHeaders.addRawHeader(key, value)

	def handleResponsePart(self, buffer):
		if self.stop:
			self.handleResponseEnd()
			return 
		self.bytes_recvd += len(buffer)
		self.father.write(buffer)

	def handleResponseEnd(self):
		if self.stop:
			self.transport.loseConnection()
		elif not self._finished:
			self._finished = True
			self.transport.loseConnection()
			self.father.finish() #close normally (for a regular proxy request)


class ProxyClientFactory(ClientFactory):

	protocol = ProxyClient

	def __init__(self, command, rest, version, headers, data, father):
		self.command = command
		self.rest = rest
		self.version = version
		self.headers = headers
		self.data = data
		self.father = father

	def buildProtocol(self,addr):
		return self.protocol(self.command, self.rest, self.version,
			self.headers, self.data, self.father)

class ProxyRequest(Request):
	"""This class catches all HTTP connections coming from an end client and 
	preforms the necessary proxy functions"""

	protocols = {'http': ProxyClientFactory}
	ports = {'http': 80}

	def __init__(self, channel, queued, reactor=reactor):
		Request.__init__(self, channel, queued)
		self.reactor = reactor
		self.peers = {}
		self.protocol = None
		self.host = None
		self.port = None
		self.rest = None
		self.log = Logger()

	def parseHostInfo(self):
		"""parse the protocol, url, and extension out of the 
		uri provided in the request"""
		parsed = urlparse.urlparse(self.uri)
		self.protocol = parsed[0]
		self.host = parsed[1]
		try:
			self.port = self.ports[self.protocol]
		except KeyError:
			self.log.logic("no protocol provided, assuming http")
			self.protocol = 'http'

		if self.uri == '/':
			#from my python script, so use the host header
			headers = self.getAllHeaders().copy()
			self.host = headers['target']
			self.port = 80
			self.rest = '/'
			self.log.logic('connecting to host: {}'.format(self.host))
			return

		if ':' in self.host:
			self.host, self.port = self.host.split(':')
			self.port = int(self.port)
		self.rest = urlparse.urlunparse(('','') + parsed[2:])
		if not self.rest:
			self.rest = self.rest + '/'

	def process(self):
		"""process the request for sending"""
		self.parseHostInfo()
		class_ = self.protocols[self.protocol]
		headers = self.getAllHeaders().copy()
		if 'host' not in headers:
			headers['host'] = self.host
		self.content.seek(0, 0)
		s = self.content.read()
		
		#A client factory for the ProxyCLient needs to be created. The factory is then passed to 
		#the reactor which will call it when a TCP connection is established with the host
		self.uri = self.host
		clientFacotry = class_(self.method, self.rest, self.clientproto, headers, s, self)
		self.reactor.connectTCP(self.host,self.port,clientFacotry)


class Proxy(HTTPChannel):
	requestFactory = ProxyRequest
	router_key = None