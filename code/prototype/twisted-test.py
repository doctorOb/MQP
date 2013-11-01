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
import urllib2

sys.path.append('proxyHelpers.py')
from proxyHelpers import *

MINIMUM_FILE_SIZE = 10485760 / 5

PEERPORT = 7779
CHUNK_SIZE = MEGABYTE
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
			print("using 2 streams")
			pool = DownloadPool(int(value),self.father)
			pool.queryPeers()
			self._finidhed = True
			self.transport.loseConnection()

		if key.lower() in ['server', 'date', 'content-type']:
			self.father.responseHeaders.setRawHeaders(key, [value])
		else:
			self.father.responseHeaders.addRawHeader(key, value)

	def handleResponsePart(self, buffer):
		self.bytes_recvd += len(buffer)
		self.father.write(buffer)

	def handleResponseEnd(self):
		print("read {} bytes total from server".format(self.bytes_recvd))
		if not self._finished:
			self._finished = True
			self.father.notifyFinish()
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

class RequestBodyReciever(Protocol):
	"""
	needed to actually send the response from a server (because of the way the response object works).
	Passes any data it recieves to the Peer writer. This is an unfortunate side effect of the twisted 
	architecture. A response object cannot pass it's body onwards without the use of this mitigating class
	"""

	def __init__(self,client,defered):
		self.client = client #reference to client class that holds an 
									 #open TCP connection with the peer
		self.recvd = 0
		self.defered = defered #placeholder for a deferred callback (incase one is eventually needed)

	def dataReceived(self,bytes):
		self.recvd += len(bytes)
		self.client.father.appendData(self.client.id,bytes)

	def connectionLost(self,reason):
		range = self.client.father.getNextChunk(self.client.id)
		if range != None:
			self.client.getChunk(range)
		else:
			print("finished getting data for pool")		

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
		self.port = self.ports[self.protocol]
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
		clientFacotry = class_(self.method, self.rest, self.clientproto, headers, s, self)
		self.reactor.connectTCP(self.host,self.port,clientFacotry)

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
		self.verified = None if peer > 0 else True #trust yourself
		self.received = 0

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
	range = client.father.getNextChunk(self.id)
	print("next for me:{}".format(range))
	if range != None:
		client.getChunk(range)
	else:
		print("finished getting data for pool")
		client.father.finish()

def requestChunks(request_size,chunk_size):
	"""generator that produces the chunk assignments (saves memory space)"""
	last = 0
	for i in range(chunk_size,request_size,chunk_size):
		yield last,i
		last = i + 1


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
		self.uri = father.uri

		#the proxy request (which maintains a TCP connection to the end client).
		self.father = father 
		self.sendBuffers = {} #a dictionary of buffers currently being filled by peer clients. 
		
		#the start index of the next chunk to send. This is used as a key into the pool's
		#sending buffers. It will only be moved once the sendBuf it maps to has finished
		#receiving its expected data
		self.rangeIndex = 0 
		self.makeup_chunks = []
		self.chunkSize = CHUNK_SIZE
		self.chunks = requestChunks(self.requestSize,self.chunkSize)
		self.zeroKnowledgeProver = ZeroKnowledgeConnection(self)
		self.client = PersistentProxyClient(self.uri,self,RequestBodyReciever,0,repeatCallback)

		print(self.zeroKnowledgeProver)

	def handleHeader(self, key, value):
		"""
		the content length returned from the first chunk request will be for the size of the chunk,
		but the client needs to see the length of the entire file, so the value must be forged 
		before the headers are sent back to the client
		"""
		if key.lower() in ['server', 'date', 'content-type']:
			self.father.responseHeaders.setRawHeaders(key, [value])
		elif 'Content-Length' in key:
			self.father.responseHeaders.addRawHeader(key,requestSize)
		else:
			self.father.responseHeaders.addRawHeader(key, value)

	def handleResponseCode(self, version, code, message):
		"""
		handle the response code (the one the client sees). If it is 206 (returned for 
		partial content responses) the code must be changed to 200, so the client sees it
		as it would be for a real request
		"""
		if int(code) == 206: #206 is returned for partial content files.
			code = 200
		self.father.setResponseCode(int(code),message)

	def queryPeers(self):
		"""give shared request info to each peer"""
		id = 1
		for peer_ip in self.peerIPs:
			peerFactory = PeerClientFactory(peer_ip,self.uri,id,self)
			reactor.connectTCP(peer_ip,PEERPORT,peerFactory)
			id+=1

	def terminatePeer(self,peer):
		"""break it off with a peer. If they had work, push it onto the makeup queue.
		Close the connection with the peer for the rest of the session."""
		working = self.sendBuffers[peer.id]
		if working: #assign this request to another peer (or self)
			self.makeup_chunks.insert(0,working.range)
			del self.sendBuffers[peer.id]

		self.peers[peer.id].terminateConnection()


	def getNextChunk(self,sender):
		"""
		this function is called by a peerHandler class when it is ready to 
		dispatch more work to a sender.
		"""

		important = self.makeup_chunks.pop()

		try:
			peer = self.peers[sender]
		except KeyError:
			print("Peer for chunk request does not exist in this download pool")
			return None

		try:
			if important:#if there is a chunk that failed, it must be recovered
				range = important
			else:
				range = self.chunks.next()
		except StopIteration:
			#no more chunks to download, so terminate
			return None


		self.sendBuffers[range[0]] = sendBuf(peer,range)

		if sender > 0:
			#if the sender is a peer, verify the validity of their data
			self.zeroKnowledgeProver.getVerifyChunk(self.sendBuffers[range[0]])
		#create a deferred object to handle the response
		defered = self.waitForData()
		defered.addCallback(self.writeData)

		return range

	def appendData(self,peerIndex,data):
		"""
		called by a peerHandler when it has data to write, passes in a
		buffer index (the start of the chunk) to write at
		"""
		buf = self.sendBuffers[peerIndex]
		buf.writeData(data)

	
	def waitForData(self,d=None):
		"""
		the heart of the callback chain. This will either trigger it's callback
		(writeData), or schedule its self to be called later (to prevent blocking)
		"""
		postpone = False
		peer = None
		if not d:
			d = defer.Deferred()
		try:
			buf = self.sendBuffers[self.rangeIndex]
			peer = buf.peer
			if peer is not self.client:
				self.peers[peer.id].resetTimeout()
			if buf.verified != None:
				d.callback(buf)
			else:
				postpone = True
		except KeyError:
			postpone = True

		if postpone:
			if peer and not peer.updateTimeout(): #timeout occured, drop the peer
				self.terminatePeer(peer)
			reactor.callLater(.01,self.waitForData,d)

		return d

	def writeData(self,data):
		"""
		write the data at the head of the buffer to the transport
		"""
		buf = self.sendBuffers[self.rangeIndex]

		if buf.verified == False:
			print("peer sent back faulty data")
			self.terminatePeer(self.peers[buf.id])
		self.father.transport.write(buf.getData())
		buf.data = '' #clear it out incase their is more data to fill

		if buf.done:
			del self.sendBuffers[self.rangeIndex] #remove the buffer, and update the index
			self.rangeIndex+=buf.size
			print("index:",self.rangeIndex)






class PeerHandler(Protocol):
	"""
	Handles a persistent TCP connection between the proxy and a peer proxy. The flow it facilitates is 
	as follows:

		init: send the peer a protocol INIT message asking for help with a file from the given uri
		confirm: if the peer replies 'ACCEPT', then consider them contracted for the session
		request and receive: repeat
			send CHUNK request for the next range given by the pool
			receive data from peer, and pass it to the pool
	"""

	def __init__(self,IP,id,uri,father):
		self.father = father
		self.uri = uri
		self.ip = IP
		self.data_recvd = 0
		self.id = id
		self.index = 0
		self.recvd = 0
		self.data_stop = 0
		self.verified = False
		self.trust_level = 0
		self.father.peers[self.id] = self
		self.resetTimeout()

	def connectionMade(self):
		self.transport.write(PPM_INIT(self.uri))
		print("connection established")
		
	def clientConnectionFailed(self):
		print("connection failed")

	def queryNext(self):
		"""ask the DownloadPool what range to get next, and send the request to the peer"""
		next = self.father.getNextChunk(self.id)
		print('next for peer:',next)
		if next == None:
			return 

		self.index = next[0]
		self.data_stop += (next[1] - next[0])
		self.transport.write(PPM_CHUNK(next))
		self.resetTimeout()
		print("wrote to transport")

	def handlePeerMessage(self,message):
		
		message = peerProtocolMessage(message)

		if message.type == 'DATA':
			self.recvd += len(message.payload)
			if self.recvd < self.data_stop:
				self.father.appendData(self.index,message.payload)
			
			if self.recvd >= self.data_stop:
				print("alignment correct")
				self.queryNext()

	def dataReceived(self,data):
		"""handle a message from a peer. It may be a PPM status message, or
		request data that should be piped to the download pool's buffers"""

		if 'PPM' in data[0:5]:
			self.handlePeerMessage(data)
		else:
			print("unrecognized response from peer")

	def checkTimeout(self):
		"""updates the timeout timer for the particular peer. If a peer takes to long to respond
		to a chunk request, they will be dropped for the remainder of the session.
		Return True if the peer is still being waited on, and false if it has been dropped"""
		return (time.time() - self.timeStart) > TIMEOUT_THRESH()
		

	def resetTimeout(self):
		"""re initialize the timeout timer"""
		self.timeStart = time.time()

	def terminateConnection(self):
		self.transport.write(PPM_END())
		self.transport.loseConnection()





class PeerClientFactory(Factory):

	protocol = PeerHandler

	def __init__(self, IP, url, id,father):
		self.father = father
		self.ip = ip
		self.url = url
		self.id = id

	def startedConnecting(self,ignored):
		pass

	def buildProtocol(self,addr):
		return self.protocol(self.ip,self.id, self.url,self.father)

	def clientConnectionLost(self, connector, reason):
		print 'Lost connection.  Reason:', reason

	def clientConnectionFailed(self, connector, reason):
		print 'Connection failed. Reason:', reason





if __name__ == '__main__':
	factory = http.HTTPFactory()
	factory.protocol = Proxy
	reactor.listenTCP(8000, factory)
	reactor.run()