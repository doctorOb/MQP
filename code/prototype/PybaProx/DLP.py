
"""
DLPool.py is a proxy server that runs on each client router. The server monitors requests, and employs 
bandwidth aggregation when the content-length from a given response is over a certain threshold. When this happens,
a download pool is created which coordinates a round-robin style aggregation session between committed peer routers.
"""


"""

Router A: 10.18.229.213
Router B: 10.18.233.49
Client (Traflamadorian): 10.18.175.229

"""

from twisted.web import http
from twisted.web.http_headers import Headers
from twisted.internet import reactor, defer
from twisted.internet.protocol import Protocol, Factory
from twisted.python import log
from twisted.web.http import HTTPClient, Request
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
from Logger import Logger
from ZeroKnowledge import ZeroKnowledgeConnection
from persistentClient import *
from peerHandler import *

VERIFY_SIZE = 5 #number of bytes to check in zero knowledge proof

#log.startLogging(sys.stdout)


def requestChunks(request_size,chunk_size):
	"""generator that produces the chunk assignments (saves memory space)"""
	last = 0
	for i in range(chunk_size,request_size,chunk_size):
		yield last,i
		last = i + 1
	yield last,request_size

class RequestBodyReciever(Protocol):
	"""needed to actually send the response from a server (because of the way the response object works).
	Passes any data it recieves to the Peer writer. This is an unfortunate side effect of the twisted 
	architecture. A response object cannot pass it's body onwards without the use of this mitigating class"""

	def __init__(self,pClient,defered):
		self.pClient = pClient #reference to persistent client class that holds an 
									 #open TCP connection with the peer
		self.recvd = 0
		self.defered = defered #placeholder for a deferred callback (incase one is eventually needed)
		self.log = Logger()

	def repeatCallback(self):
		try:
			range = self.pClient.father.getNextChunk(self.pClient.id)
			if range != None:
				self.pClient.getChunk(range)
			else:
				self.pClient.father.endSession(msg="No more range chunks")
		except:
			raise
			self.log.warning('error in repeat callback on dlp')

	def dataReceived(self,bytes):
		self.pClient.father.appendData(self.pClient,bytes)

	def connectionLost(self,reason):
		if self.recvd < self.pClient.chunk_size:
			#server sent back a splash page or something other then the desired content
			self.pClient.father.endSession("Mismatched response length from server")
		self.log.info("Response from target finished for chunk handler with reason: {}".format(reason))
		self.repeatCallback()



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

	def __init__(self,requestSize,proxyRequest):
		self.configs = reactor.configs
		self.neighbors = self.configs.neighbors
		self.participants = {}
		self.requestSize = requestSize 
		self.bytes_sent = 0
		self.uri = proxyRequest.uri

		#the proxy request (which maintains a TCP connection to the end client).
		self.proxyRequest = proxyRequest 
		self.sendBuffers = [] #an array of buffers currently being filled by peer clients. 
		
		#the start index of the next chunk to send. This is used as a key into the pool's
		#sending buffers. It will only be moved once the sendBuf it maps to has finished
		#receiving its expected data
		self.rangeIndex = 0 
		self.chunkSize = self.configs.chunk_size
		self.chunks = requestChunks(self.requestSize,self.chunkSize)
		self.zeroKnowledgeProver = ZeroKnowledgeConnection(self)
		self.client = PersistentProxyClient(self.uri,self,RequestBodyReciever,cid=0)
		self.participants[0] = self.client
		self.finished = False
		self.log = Logger()

		#begin downloading immediately
		if 'http://' not in self.uri:
			self.uri = 'http://' + self.uri

		self.client.getChunk(self.getNextChunk(self.client.id))
		self.log.warning(self.uri)

	def handleHeader(self, key, value):
		"""
		the content length returned from the first chunk request will be for the size of the chunk,
		but the client needs to see the length of the entire file, so the value must be forged 
		before the headers are sent back to the client
		"""
		if key.lower() == 'Content-Range':
			return #don't include
		if key.lower() in ['server', 'date', 'content-type']:
			self.proxyRequest.responseHeaders.setRawHeaders(key, [value])
		elif 'content-length' in key.lower():
			self.proxyRequest.responseHeaders.addRawHeader(key,requestSize)
		else:
			self.proxyRequest.responseHeaders.addRawHeader(key, value)

	def handleResponseCode(self, version, code, message):
		"""
		handle the response code (the one the client sees). If it is 206 (returned for 
		partial content responses) the code must be changed to 200, so the client sees it
		as it would be for a real request
		"""
		print("recieved response code:{} ({})".format(code,message))
		if int(code) == 206: #206 is returned for partial content files.
			code = 200
		self.proxyRequest.setResponseCode(int(code),message)

	def _peerBuffer(self,peer):
		"""find the peers buffer in the send buffers"""
		for buf in self.sendBuffers:
			if buf.peer is peer:
				return buf
		self.log.warn("no peer found in send buffers")
		return None

	def queryPeers(self):
		"""give shared request info to each peer"""
		id = 1
		for ip in self.neighbors:
			self.participants[id] = PeerHandler(self.neighbors[ip],id,self.uri,self)
			self.participants[id].getInit()
			self.log.info("Querying Neighbor {} with id {}".format(ip,id))
			id+=1

	def releaseChunk(self,chunk):
		"""called by a peer who wants to give up on its assigned chunk"""
		self.chunks = chain([(0,chunk)],self.chunks)

	def terminatePeer(self,handler):
		"""break it off with a peer. If they had work, push it onto the makeup queue.
		Close the connection with the peer for the rest of the session."""
		working = handler.assigned_chunk
		if working: #assign this request to another peer (or self)
			self.releaseChunk(working) #add its chunk to the start of the chunks generator
		if handler.id > 0 and handler.id in self.participants:
			del self.participants[handler.id]

	def endSession(self,msg=""):
		"""break off with every peer and do some cleanup"""
		self.log.logic(msg)
		if self.finished:
			return
		ids = self.participants.keys()
		for pid in ids:
			try:
				self.participants[pid].terminateConnection()
			except:
				pass #already removed somehow

		self.finished = True
		self.proxyRequest.finish()


	def getNextChunk(self,senderID):
		"""
		this function is called by a peerHandler class when it is ready to 
		dispatch more work to a sender.
		"""
		if self.finished:
			return None
		try:
			peer = self.participants[senderID]
		except KeyError:
			self.log.warning("Peer ({}) for chunk request does not exist in this download pool".format(senderID))
			return None

		try:
			range = self.chunks.next()
		except StopIteration:
			#no more chunks to download, so terminate
			return None

		buf = sendBuf(peer,range)
		self.sendBuffers.append(buf)

		#create a deferred object to handle the response
		defered = self.waitForData()
		defered.addCallback(self.writeData)
		defered.addErrback(deferedError)

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
			return None#no need to keep waiting
		postpone = True
		if not d:
			d = defer.Deferred()

		try:
			buf = self.sendBuffers[0]
			if len(buf.data) > 0:
				postpone = False
				d.callback(buf)
		except KeyError:
			self.log.warn('keyerror: {}'.format(self.rangeIndex))
			
		if postpone:
			reactor.callLater(.05,self.waitForData,d)

		return d

	def writeData(self,data):
		"""
		write the data at the head of the buffer to the transport
		"""
		try:
			buf = self.sendBuffers[0]
			data = buf.getData()
		except:
			self.log.warn("meant to write data, but no buffers were available")
			return

		try:
			self.proxyRequest.write(data)
			self.bytes_sent += len(data)
			self.log.info("wrote {}/{} bytes to the client".format(self.bytes_sent,self.requestSize))
		except:
			self.log.warn('error writing to client')
			raise
			sys.exit(0)

		buf.data = '' #clear it out incase their is more data to fill

		if buf.done:
			del self.sendBuffers[0] #remove the buffer, and update the index
			self.bytes_sent+=buf.size

		if self.bytes_sent >= (self.requestSize - 10): #wiggle room
			self.endSession()



