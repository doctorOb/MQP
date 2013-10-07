from twisted.web import proxy, http
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers
from twisted.internet import reactor
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


class PeerProxyClient(HTTPClient):
	_finished = False
	bytes_recvd = 0
	def __init__(self, command, rest, version, headers, data, father, pool):
		self.father = father
		self.command = command
		self.rest = rest
		self.version = version
		self.headers = headers
		self.data = data
		self.father = father
		self.pool = pool
		self.id = 0 #original g

		if "proxy-connection" in headers:
			del headers["proxy-connection"]
		headers["connection"] = "close"
		headers.pop('keep-alive', None)
		self.headers = headers
		self.data = data
		self.pool.queryPeers()

	def connectionMade(self):
		self.sendCommand(self.command, self.rest)
		self.headers['Range'] = 'bytes={}-{}'.format(*self.pool.getNextChunk(self.id))
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
		self.pool.appendData(self,buffer)

	def handleResponseEnd(self):
		self.headers['Range'] = 'bytes={}-{}'.format(*self.pool.getNextChunk(self.id))
		self.endHeaders()
		print("continuing")
		
		#loop and make a new connection
		# if not self._finished:
		# 	self._finished = True
		# 	self.father.finish()
		# 	self.transport.loseConnection()

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

class PeerProxyClientFactory(ClientFactory):

	protocol = PeerProxyClient

	def __init__(self,command,rest,version,headers,data,father,pool):
		self.father = father
		self.command = command
		self.rest = rest
		self.headers = headers
		self.data = data
		self.version = version
		self.pool = pool

	def buildProtocol(self,addr):
		return self.protocol(self.command, self.rest, self.version,
			self.headers, self.data, self.father,self.pool)






class ProxyRequest(Request):

	protocols = {'http': ProxyClientFactory}
	ports = {'http': 80}

	def __init__(self, channel, queued, reactor=reactor):
		Request.__init__(self, channel, queued)
		self.reactor = reactor
		self.peers = {}

	def process(self):
		parsed = urlparse.urlparse(self.uri)
		protocol = parsed[0]
		host = parsed[1]
		port = self.ports[protocol]
		if ':' in host:
			host, port = host.split(':')
			port = int(port)
		rest = urlparse.urlunparse(('','') + parsed[2:])
		if not rest:
			rest = rest + '/'
		class_ = self.protocols[protocol]
		headers = self.getAllHeaders().copy()
		if 'host' not in headers:
			headers['host'] = host
		self.content.seek(0, 0)
		s = self.content.read()
		fileSize = getFileSize(self.uri)

		if fileSize >= MINIMUM_FILE_SIZE:
			print("using 2 streams")

			pool = DownloadPool(fileSize,self)
			print('uri:',self.uri)
			PeerClientFactory = PeerProxyClientFactory(self.method,rest,self.clientproto,headers,s,self,pool)
			self.reactor.connectTCP(host,port,PeerClientFactory)
			return

			
		clientFacotry = class_(self.method, rest, self.clientproto, headers, s, self)
		self.reactor.connectTCP(host,port,clientFacotry)

class Proxy(HTTPChannel):
	requestFactory = ProxyRequest


class sendBuf():

	def __init__(self,id,size):
		self.id = id
		self.data = ''
		self.size = size
		self.done = False

	def writeData(self,data):
		self.data += data
		if len(data) >= self.size:
			self.done = True


	def getData(self):
		return self.data

	def getId(self):
		return self.id



class DownloadPool():

	def __init__(self,requestSize,father):
		self.peers = ['127.0.0.1']
		self.requestSize = requestSize
		self.url = father.uri
		self.father = father
		self.sendBuffers = []
		self.connections = {}
		self.sendingPeer = ''
		self.rangeIndex = 0
		self.chunkSize = 1024
		self.chunks = [] #array to hold each chunk range
		self.peerBufferIndex = {} #peer id to spot in sender buffer

		last = 0
		for i in range(self.chunkSize,requestSize,self.chunkSize):
			self.chunks.insert(0,(last,i))
			last = i + 1

		self.defered = waitForData()
		self.defered.addCallback(self.writeData)



	def queryPeers(self):
		"""give shared request info to each peer"""
		i = 1
		for peer in self.peers:
			peerFactory = PeerClientFactory(self.url,i,self)
			reactor.connectTCP(peer,PEERPORT,peerFactory)
			i+=1

	def getNextChunk(self,peer):
		if len(self.chunks) <= 0:
			return None

		range = self.chunks.pop()
		if self.rangeIndex == range[0]:
			self.sendingPeer = peer.id

		self.sendBuffers.append(sendBuf(peer.id))

		return range

	def appendData(self,peerId,data):

		for buf in self.sendBuffers:
			if buf.id == peerId:
				buf.writeData(data)

	
	def waitForData(self,d=None):

		if not d:
			d = defer.Deferred()

		if len(self.sendBuffer) == 0:
			reactor.callLater(1,waitForData,d)
		else:
			d.callback()

		return d

	def writeData(self):
		buf = self.sendBuffers.pop()
		data = buf.getData()
		buf.data = ''

		if not buf.done:
			self.sendBuffers.insert(0,buf)

		self.father.transport.write(data)


	def loop(self):
		"""main loop for the pool. Check buffers for available 
		data to send and do so if available"""

		while True:

			if len(self.sendBuffers) == 0:
				
			buf = self.sendBuffers.pop()
			data = buf.getData()
			if not buf.done:
				self.sendBuffers.insert(0,buf)

			self.rangeIndex += len(data)
			self.father.transport.write(data)





class PeerHandler(Protocol):

	def __init__(self,id,uri,father):
		self.father = father
		self.uri = uri
		self.data_recvd = 0
		self.id = id
		self.verified = False

		self.data_stop = 0

	def connectionMade(self):
		self.transport.write(PPM_INIT(self.uri))
		print("connection established")
		
	def clientConnectionFailed(self):
		print("connection failed")

	def queryNext(self):
		print('querying next')
		next = self.father.getNextChunk(self.id)
		if next is None:
			return 

		self.data_recvd = 0
		self.data_stop = next[1] - next[0] + 1
		self.index = next[0]
		self.transport.write(PPM_CHUNK(next))
		print("wrote to transport")

	def dataReceived(self,data):
		print(data)
		if not self.verified:
			print("got response from peer:",data)
			self.verified = True
			self.queryNext()
			return
		if self.data_recvd < self.data_stop:
			self.father.appendData(self,data)
			self.data_recvd += len(data)
			print("{}/{}".format(self.data_recvd,self.data_stop))
		
		if self.data_recvd >= self.data_stop:
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

	def __init__(self, url, father):
		self.father = father
		self.url = url

	def startedConnecting(self,ignored):
		pass

	def buildProtocol(self,addr):
		return self.protocol(self.url, self.father)

	def clientConnectionLost(self, connector, reason):
		print 'Lost connection.  Reason:', reason

	def clientConnectionFailed(self, connector, reason):
		print 'Connection failed. Reason:', reason





if __name__ == '__main__':
	factory = http.HTTPFactory()
	factory.protocol = Proxy
	reactor.listenTCP(8000, factory)
	reactor.run()