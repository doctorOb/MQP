
"""
DLPool.py is a proxy server that runs on each client router. The server monitors requests, and employs 
bandwidth aggregation when the content-length from a given response is over a certain threshold. When this happens,
a download pool is created which coordinates a round-robin style aggregation session between committed peer routers.
"""

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

sys.path.append('proxyHelpers.py')
from proxyHelpers import *

MINIMUM_FILE_SIZE = KILOBYTE

PEERPORT = 8080
CHUNK_SIZE = KILOBYTE
VERIFY_SIZE = 5 #number of bytes to check in zero knowledge proof


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
		self.stop = False

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
		"""
		Pass the headers to the father request object (which writes to the client)
		If the content-length is larger then the minimum file size, stop the request
		and start over with a download pool
		"""
		if key == 'Content-Length' and int(value) > MINIMUM_FILE_SIZE:
			print('using two streams')
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

	def parseHostInfo(self):
		"""parse the protocol, url, and extension out of the 
		uri provided in the request"""
		parsed = urlparse.urlparse(self.uri)
		self.protocol = parsed[0]
		self.host = parsed[1]
		try:
			self.port = self.ports[self.protocol]
		except KeyError:
			print"no protocol provided, assuming http"
			self.protocol = 'http'

		if self.uri == '/':
			#from my python script, so use the host header
			headers = self.getAllHeaders().copy()
			self.host = headers['host']
			self.port = 80
			self.rest = '/'
			print 'connecting to host:',self.host
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


class ZeroKnowledgeVerifier(Protocol):
	"""
	Recieves the small portion of data from the server used to verify a peer's response.
	"""

	def __init__(self,recvBuf):
		self.recvBuf = recvBuf
		self.recvd = ''

	def dataReceived(self,bytes):
		self.recvd += bytes

	def connectionLost(self,reason):
		self.recvBuf.verify(self.recvd)

class ZeroKnowledgeConnection():

	def __init__(self,downloadPool):
		self.downloadPool = downloadPool
		self.uri = downloadPool.uri
		self.httpPool = HTTPConnectionPool(reactor) #the connection to be persisted
		self.agent = Agent(reactor, pool=self.httpPool)


	def getVerifyChunk(self,recvBuf):
		"""Issue an HTTP GET request for the small chunk of 
		data needed for verifying a peer response. The 
		peer's data buffer is provided, as the confirmation
		logic happens there"""
		defered = self.agent.request(
			'GET',
			self.uri,
			Headers({
				'Range' : [httpRange(recvBuf.verifyRange)]
				}),
			None)
		defered.addCallback(self.responseRecieved,recvBuf)
		return defered

	def responseRecieved(self,response,recvBuf):
		if response.code > 206: #206 is the code returned for http range responses
			print("error with veri from server")
			return None #TODO: exit gracefully

		finished = Deferred()
		recvr = ZeroKnowledgeVerifier(recvBuf)
		response.deliverBody(recvr)
		return finished


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
		self.client.father.appendData(self.client,bytes)

	def connectionLost(self,reason):
		if self.doCallback:
			repeatCallback(self.client)
		else:
			print "connection terminated ({})".format(reason)

class Proxy(HTTPChannel):
	requestFactory = ProxyRequest


class sendBuf():
	"""
	a smarter buffer used to hold data (and meta-data describing the data), 
	that comes through from a peer helper
	"""

	def __init__(self,peer,range):
		self.peer = peer
		self.data = ''
		self.range = range
		self.size = range[1] - range[0]
		self.done = False
		self.verified = False if peer.id > 0 else True #trust yourself
		self.received = 0
		self.verifyIdx = 0
		self.verifyRange = None

		if not self.verified:
			self.verifyIdx = random.randint(range[0],range[1] - VERIFY_SIZE)
			self.verifyRange = self.verifyIdx, self.verifyIdx + VERIFY_SIZE

	def writeData(self,data):
		self.data += data
		self.received += len(data)
		if self.received >= self.size:
			self.done = True

	def getData(self):
		return self.data

	def getPeer(self):
		return self.peer

	def verify(self,verifyData):
		self.verified = True if self.verified else self.data[self.verifyRange[0]:self.verifyRange[1]] == verifyData


def repeatCallback(client):
	range = client.father.getNextChunk(client.id)
	if range != None:
		client.getChunk(range)
	else:
		print("no new data to retrieve")

def requestChunks(request_size,chunk_size):
	"""generator that produces the chunk assignments (saves memory space)"""
	last = 0
	for i in range(chunk_size,request_size,chunk_size):
		yield last,i
		last = i + 1
	yield last,request_size


class PeerHandler():
	"""maintains a Persistent TCP connection with the supplied neighbor. Talks to the neighbor over the new
	ppm API via HTTP deferreds. This class is meant to be instantiated for each session."""

	def __init__(self,neighbor,id,target,father):
		self.pool = HTTPConnectionPool(reactor) #the connection to be persisted
		self.agent = Agent(reactor, pool=self.pool)
		self.responseWriter = RequestBodyReciever
		self.peer_ip = neighbor.ip
		self.target = target
		self.father = father
		self.id = id
		self.neighbor = neighbor
		self.index = 0
		self.recvd = 0
		self.data_stop = 0
		self.verified = False
		self.trust_level = 0
		#self.pool.peers[self.id] = self

	def _url(self,path):
		return 'http://{}:{}/{}'.format(self.peer_ip,PEERPORT,path)

	def _baseHeaders(self):
		"""return a dictionary of the base headers needed in a peer request"""
		headers = Headers()
		headers.addRawHeader('target',self.target)
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
		return defered

	def getInit(self):
		"""Hit a peer with an init request for a session at the supplied url"""
		headers = self._baseHeaders()
		headers.addRawHeader('signature','placeholder')

		return self._doRequest(self._url('init'),headers)


	def getChunk(self,range):
		"""Hit a peer with a /chunk request for the range specified"""
		headers = self._baseHeaders()
		headers.addRawHeader('Range',httpRange(range))

		return self._doRequest(self._url('chunk'),headers)

	def terminateConnection(self):
		"""
			called when the handler wishes to end its session,
			usually by the wish of the peer. This involves removing 
			the instance from the father instance's records.
		"""
		#add makeup chunk to 
		del self.father.peers[self.id]

	def responseRecieved(self,response):
		"""
			Hook in here before setting up the response body reader. 
			Look at headers to determine if the signature is valid,
			what the peer is sending back, ect.
		"""

		if response.code == 400: #peer wises to terminate it's involvement
			#add makeup chunk to father's buffers
			self.terminateConnection()
			return 

	 	headers = self._responseHeaders(response)

	 	finished = Deferred()
	 	recvr = self.responseWriter(self,finished,doCallback=True) 
		response.deliverBody(recvr)

		return finished



class DownloadPool():
	"""
	This is a manager object that delegates (maps) each chunk to a given peer handler class.
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
	its self to be called in a short time.
	"""

	def __init__(self,requestSize,father):
		self.peerIPs = ['127.0.0.1'] #must be known ahead of time (perhaps read in from a config)
		self.peers = {}
		self.requestSize = requestSize 
		self.bytes_sent = 0
		self.uri = father.uri

		#the proxy request (which maintains a TCP connection to the end client).
		self.father = father 
		self.sendBuffers = [] #an array of buffers currently being filled by peer clients. 
		
		#the start index of the next chunk to send. This is used as a key into the pool's
		#sending buffers. It will only be moved once the sendBuf it maps to has finished
		#receiving its expected data
		self.rangeIndex = 0 
		self.makeup_chunks = []
		self.chunkSize = CHUNK_SIZE
		self.chunks = requestChunks(self.requestSize,self.chunkSize)
		self.zeroKnowledgeProver = ZeroKnowledgeConnection(self)
		self.client = PersistentProxyClient(self.uri,self,RequestBodyReciever,0,repeatCallback)
		self.peers[0] = self.client
		self.finished = False

		#begin downloading immediately
		if 'http://' not in self.uri:
			self.uri = 'http://' + self.uri
		self.client.getChunk(self.getNextChunk(self.client.id))

	def handleHeader(self, key, value):
		"""
		the content length returned from the first chunk request will be for the size of the chunk,
		but the client needs to see the length of the entire file, so the value must be forged 
		before the headers are sent back to the client
		"""
		if key.lower() == 'Content-Range':
			return #don't include
		if key.lower() in ['server', 'date', 'content-type']:
			self.father.responseHeaders.setRawHeaders(key, [value])
		elif 'content-length' in key.lower():
			self.father.responseHeaders.addRawHeader(key,requestSize)
		else:
			self.father.responseHeaders.addRawHeader(key, value)

	def handleResponseCode(self, version, code, message):
		"""
		handle the response code (the one the client sees). If it is 206 (returned for 
		partial content responses) the code must be changed to 200, so the client sees it
		as it would be for a real request
		"""
		print("recieved response code:{} ({})".format(code,message))
		if int(code) == 206: #206 is returned for partial content files.
			code = 200
		self.father.setResponseCode(int(code),message)

	def _peerBuffer(self,peer):
		"""find the peers buffer in the send buffers"""
		for buf in self.sendBuffers:
			if buf.peer is peer:
				return buf
		print("no peer found in send buffers")
		return None

	def queryPeers(self):
		"""give shared request info to each peer"""
		id = 1
		for peer_ip in self.peerIPs:
			peer = Neighbor(peer_ip)
			self.peers[id] = PeerHandler(peer,id,self.uri,self)
			self.peers[id].getInit()
			id+=1


		"""break it off with a peer. If they had work, push it onto the makeup queue.
		Close the connection with the peer for the rest of the session."""
		working = self._peerBuffer(peer)
		if working: #assign this request to another peer (or self)
			self.makeup_chunks.insert(0,working.range)
			del working
		if peer.id > 0:
			self.peers[peer.id].terminateConnection()
		del self.peers[peer.id]

	def endSession(self):
		"""break off with every peer and do some cleanup"""
		del self.peers[0] #remove the proxyclient on this router
		for pid in self.peers:
			if pid > 0:
				self.peers[pid].terminateConnection()
		self.finished = True
		self.father.finish()


	def getNextChunk(self,sender):
		"""
		this function is called by a peerHandler class when it is ready to 
		dispatch more work to a sender.
		"""
		try:
			peer = self.peers[sender]
		except KeyError:
			print("Peer ({}) for chunk request does not exist in this download pool".format(sender))
			return None

		try:
			if len(self.makeup_chunks) > 0:#if there is a chunk that failed, it must be recovered
				range = self.makeup_chunks.pop()
			else:
				range = self.chunks.next()
		except StopIteration:
			#no more chunks to download, so terminate
			return None

		buf = sendBuf(peer,range)
		self.sendBuffers.append(buf)

		#create a deferred object to handle the response
		defered = self.waitForData()
		defered.addCallback(self.writeData)

		return range

	def appendData(self,peer,data):
		"""
		called by a peerHandler when it has data to write, passes in a
		buffer index (the start of the chunk) to write at
		"""
		buf = self._peerBuffer(peer)
		buf.writeData(data)

	
	def waitForData(self,d=None):
		"""
		the heart of the callback chain. This will either trigger it's callback
		(writeData), or schedule its self to be called later (to prevent blocking)
		"""
		if self.finished:
			return #no need to keep waiting
		postpone = True
		if not d:
			d = defer.Deferred()

		try:
			buf = self.sendBuffers[0]
			if len(buf.data) > 0:
				postpone = False
				d.callback(buf)
		except KeyError:
			print('keyerror',self.rangeIndex)
			
		if postpone:
			reactor.callLater(.01,self.waitForData,d)

		return d

	def writeData(self,data):
		"""
		write the data at the head of the buffer to the transport
		"""
		try:
			buf = self.sendBuffers[0]
			data = buf.getData()
		except:
			print("meant to write data, but no buffers were available")

		print('writing {} bytes to client'.format(len(data)))
		self.father.write(data)
		buf.data = '' #clear it out incase their is more data to fill

		if buf.done:
			del self.sendBuffers[0] #remove the buffer, and update the index
			self.bytes_sent+=buf.size

		if self.bytes_sent >= self.requestSize:
			self.endSession()


if __name__ == '__main__':
	factory = http.HTTPFactory()
	factory.protocol = Proxy
	reactor.listenTCP(1337, factory)
	reactor.run()


