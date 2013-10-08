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

from threading import Thread
import sys
import random
from copy import deepcopy
import urllib2

MINIMUM_FILE_SIZE = 10485760 / 5

PEERPORT = 7779

class HeadRequest(urllib2.Request):
	def get_method(self):
		return "HEAD"

def getFileSize(url):
	"""Issue an http HEAD request to calculate the size of the page requested"""
	response = urllib2.urlopen(HeadRequest(url))
	try:
		size = response.info()['content-length']
	except:
		size = 0

	print("content size:{}".format(size))
	return int(size)

#log.startLogging(sys.stdout)

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

	def connectionMade(self):
		self.sendCommand(self.command, self.rest)
		for header, value in self.headers.items():
			self.sendHeader(header,value)
			if header == 'Range':
				print("range request:{}".format(value))
		self.endHeaders()
		self.transport.write(self.data)

	def handleStatus(self, version, code, message):
		self.father.setResponseCode(int(code),message)

	def handleHeader(self, key, value):
		if key.lower() in ['server', 'date', 'content-type']:
			self.father.responseHeaders.setRawHeaders(key, [value])
		else:
			self.father.responseHeaders.addRawHeader(key, value)

	def handleResponsePart(self, buffer):
		self.bytes_recvd += len(buffer)
		self.father.write(buffer)

	def handleResponseEnd(self):
		print("read {} bytes total form server",self.bytes_recvd)
		if not self._finished:
			self._finished = True
			self.father.finish()
			self.transport.loseConnection()


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

	def parseHostInfo(self):
		"""parse the protocol, url, and extension out of the 
		uri provided in the request"""
		parsed = urlparse.urlparse(self.uri)
		self.protocol = parsed[0]
		self.host = parsed[1]
		port = self.ports[self.protocol]
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

		#TODO: consider performing this check once a request is received (assuming content-length is
		#always provided by the server).
		fileSize = getFileSize(self.uri)
		if fileSize >= MINIMUM_FILE_SIZE:
			print("using 2 streams")

			pool = DownloadPool(fileSize,self)
			print('uri:',self.uri)
			PeerClientFactory = PeerProxyClientFactory(self.method,self.rest,self.clientproto,headers,s,self,pool)
			self.reactor.connectTCP(self.host,self.port,PeerClientFactory)
			return
		
		#A client factory for the ProxyCLient needs to be created. The factory is then passed to 
		#the reactor which will call it when a TCP connection is established with the host
		clientFacotry = class_(self.method, rest, self.clientproto, headers, s, self)
		self.reactor.connectTCP(host,port,clientFacotry)

class Proxy(HTTPChannel):
	requestFactory = ProxyRequest


class sendBuf():
	"""a smarter buffer used to hold data (and meta-data describing the data), 
	that comes through from a peer helper"""

	def __init__(self,id,size):
		self.id = id
		self.data = ''
		self.size = size
		self.done = False
		self.received = 0

	def writeData(self,data):
		self.data += data
		self.received += len(data)
		if self.received >= self.size:
			self.done = True

	def getData(self):
		yield self.data
		self.data = ''

	def getId(self):
		return self.id



class DownloadPool():
	"""This is a manager object that delegates (maps) each chunk to a given peer handler class.
	It indirectly communicates with the peer through these. Since twisted is not inherently thread
	safe, and is heavily event driven, this class does not run as its own thread. Instead, I chose to 
	make use of twisted's Deferred class, which was recommended for use in any blocking situation.

	Background on Deferred:
	A deferred is a function that will be called after asynchronous information that it is 
	depended on comes in. Callbacks are attached to it, which will fire of in chain after the 
	deferred is triggered. From the website:

		'in cases where a function in a threaded program would block until it gets a result, 
		for Twisted it should not block. Instead, it should return a Deferred.'

	In this case, whenever a new chunk is requested by one of the peer handlers (implying that 
	it's associated peer has finished its prior work), a deferred is dispatched. It will then 
	check the head of the pools buffers for data to write. If none exist, it will reschedule 
	its self to be called in a short time."""

	def __init__(self,requestSize,father):
		self.peers = ['127.0.0.1'] #must be known ahead of time (perhaps read in from a config)
		self.requestSize = requestSize 
		self.url = father.uri

		#the proxy request (which maintains a TCP connection to the end client).
		self.father = father 
		self.sendBuffers = {} #a dictionary of buffers currently being filled by peer clients. 
		
		#the start index of the next chunk to send. This is used as a key into the pool's
		#sending buffers. It will only be moved once the sendBuf it maps to has finished
		#receiving its expected data
		self.rangeIndex = 0 
		self.chunkSize = 1024*10
		self.chunks = [] #array to hold each chunk range. This is only necessary if the 
						 #chunk size is static (non-adaptive)

		last = 0
		for i in range(self.chunkSize,requestSize,self.chunkSize):
			self.chunks.insert(0,(last,i))
			last = i + 1




	def queryPeers(self):
		"""give shared request info to each peer"""
		i = 1
		for peer in self.peers:
			peerFactory = PeerClientFactory(self.url,i,self)
			reactor.connectTCP(peer,PEERPORT,peerFactory)
			i+=1

	def getNextChunk(self,peer):
		"""this function is called by a peerHandler class when it is ready to 
		dispatch more work to a peer"""
		if len(self.chunks) <= 0:
			return None

		range = self.chunks.pop()
		self.sendBuffers[range[0]] = sendBuf(peer,self.chunkSize)
		
		#create a deferred object to handle the response
		defered = self.waitForData()
		defered.addCallback(self.writeData)

		return range

	def appendData(self,peerIndex,data):
		"""called by a peerHandler when it has data to write, passes in a
		buffer index (the start of the chunk) to write at"""
		buf = self.sendBuffers[peerIndex]
		buf.writeData(data)

	
	def waitForData(self,d=None):
		"""the heart of the callback chain. This will either trigger it's callback
		(writeData), or schedule its self to be called later (to prevent blocking)"""

		if not d:
			d = defer.Deferred()

		try:
			data = self.sendBuffers[self.rangeIndex]
			d.callback(data)
		except KeyError:
			reactor.callLater(1,self.waitForData,d)

		return d

	def writeData(self,data):
		"""write the data at the head of the buffer to the transport"""
		buf = self.sendBuffers[self.rangeIndex]
		self.father.transport.write(buf.getData())

		if buf.done:
			del self.sendBuffers[self.rangeIndex] #remove the buffer, and update the index
			self.rangeIndex+=buf.size






class PeerHandler(Protocol):
	"""Handles a persistent TCP connection between the proxy and a peer proxy. The flow it facilitates is 
	as follows:

		init: send the peer a protocol INIT message asking for help with a file from the given url
		confirm: if the peer replies 'ACCEPT', then consider them contracted for the session
		request and receive: repeat
			send CHUNK request for the next range given by the pool
			receive data from peer, and pass it to the pool
	"""

	def __init__(self,id,uri,father):
		self.father = father
		self.uri = uri
		self.data_recvd = 0
		self.id = id
		self.verified = False
		self.index = 0
		self.data_stop = 0

	def connectionMade(self):
		self.transport.write(PPM_INIT(self.uri))
		print("connection established")
		
	def clientConnectionFailed(self):
		print("connection failed")

	def queryNext(self):
		"""as the DownloadPool what range to get next, and send the request to the peer"""
		next = self.father.getNextChunk(self.id)
		if next is None:
			return 

		self.data_start = next[0]
		self.data_stop = next[1]
		self.index = next[0]
		self.transport.write(PPM_CHUNK(next))
		print("wrote to transport")

	def dataReceived(self,data):
		if not self.verified:
			print("got response from peer:",data)
			self.verified = True
			self.queryNext()
			return

		if self.index < self.data_stop:
			self.father.appendData(self.index,data)
			self.index += len(data)
			print("{}/{}".format(self.index,self.data_stop))
		
		if self.index >= self.data_stop:
			print("alignment correct")
			self.queryNext()



def PPM_INIT(url):
	return "PPM/INIT\r\n{}\r\n".format(url)

def PPM_CHUNK(range):
	"""send ppm range chunk from the supplied tuple"""
	return "PPM/CHUNK\r\n{},{}\r\n".format(*range)

def PPM_END():
	return "PPM/END\r\n"


class PeerClientFactory(Factory):

	protocol = PeerHandler

	def __init__(self, url, id,father):
		self.father = father
		self.url = url
		self.id = id

	def startedConnecting(self,ignored):
		pass

	def buildProtocol(self,addr):
		return self.protocol(self.id, self.url,self.father)

	def clientConnectionLost(self, connector, reason):
		print 'Lost connection.  Reason:', reason

	def clientConnectionFailed(self, connector, reason):
		print 'Connection failed. Reason:', reason





if __name__ == '__main__':
	factory = http.HTTPFactory()
	factory.protocol = Proxy
	reactor.listenTCP(8000, factory)
	reactor.run()