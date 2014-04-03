
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

	def __init__(self,pClient,range):
		self.pClient = pClient #reference to persistent client class that holds an 
									 #open TCP connection with the peer
		self.recvd = 0
		self.start = range[0] #placeholder for a deferred callback (incase one is eventually needed)
		self.size = range[1] - range[0]
		self.log = Logger()

	def repeatCallback(self):
		try:
			range = self.pClient.father.getNextChunk(self.pClient.id)
			if range != None:
				self.pClient.getChunk(range)
		except:
			self.log.warning('error in repeat callback on dlp')

	def dataReceived(self,bytes):
		self.log.info("resp received")
		self.recvd += len(bytes)
		self.pClient.father.appendData(self.pClient,self.start,bytes)

	def connectionLost(self,reason):
		if self.recvd < self.size:
			#server sent back a splash page or something other then the desired content
			self.pClient.father.endSession("Mismatched response length from server")
		self.log.info("Server ended transmission successfully with local pClient")
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
		#the proxy request (which maintains a TCP connection to the end client).
		self.proxyRequest = proxyRequest.father
		self.proxyClient = proxyRequest
		self.uri = self.proxyRequest.uri
		self.host = self.proxyRequest.host
		self.rest = self.proxyRequest.rest
		self.sendBuffers = [] #an array of buffers currently being filled by peer clients. 
		
		#the start index of the next chunk to send. This is used as a key into the pool's
		#sending buffers. It will only be moved once the sendBuf it maps to has finished
		#receiving its expected data
		self.rangeIndex = 0

		optimal_chunk_size = self.configs.max_chunk_size
		self.chunkSize = optimal_chunk_size if optimal_chunk_size < self.configs.max_chunk_size else self.configs.max_chunk_size
		
		self.chunks = requestChunks(self.requestSize,self.chunkSize)
		self.zeroKnowledgeProver = ZeroKnowledgeConnection(self)
		self.client = PersistentProxyClient(self.host,self.rest,self,RequestBodyReciever,cid=0)
		self.participants[0] = self.client
		self.finished = False
		self.log = Logger()

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
			self.proxyRequest.responseHeaders.setRawHeaders(key, [value])
		elif 'content-length' in key.lower():
			self.proxyRequest.responseHeaders.addRawHeader(key,requestSize)
		else:
			self.proxyRequest.responseHeaders.addRawHeader(key, value)

	def handleResponseCode(self, code):
		"""
		handle the response code (the one the client sees). If it is 206 (returned for 
		partial content responses) the code must be changed to 200, so the client sees it
		as it would be for a real request
		"""
		if int(code) == 206: #206 is returned for partial content files.
			code = 200
		self.proxyRequest.setResponseCode(int(code),"")

	def _peerBuffer(self,peer,start):
		"""find the peers buffer in the send buffers"""
		for buf in self.sendBuffers:
			if buf.peer is peer and buf.start_idx == start:
				return buf
		self.log.warning("no peer found in send buffers")
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
		if self.finished:
			return

		self.log.logic(msg)
		ids = self.participants.keys()
		for pid in ids:
			try:
				self.participants[pid].terminateConnection()
			except:
				pass #already removed somehow

		self.finished = True
		self.proxyClient.finish()


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
			chunk_range = self.chunks.next()
		except StopIteration:
			#no more chunks to download, so terminate
			self.log.info("No more chunks to allocate")
			chunk_range = None
			#consider removing the following line. In the case that the last chunk
			#is substantially large, it is difficult to predict a proper timeout 
			#interval to wait. Hard coding is clearly a poor decision.
			reactor.callLater(15,self.endSession,"Timeout session end") 


		if chunk_range:
			try:
				buf = sendBuf(peer,chunk_range)
				self.sendBuffers.append(buf)
			except:
				#invalid range tuple (weird bug)
				chunk_range = None

		#create a deferred object to handle the response
		defered = self.waitForData()

		return chunk_range

	def appendData(self,peer,startidx,data):
		"""
		called by a peerHandler when it has data to write, passes in a
		buffer index (the start of the chunk) to write at
		"""
		buf = self._peerBuffer(peer,startidx)
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
			d.addCallback(self.writeData)
			d.addErrback(deferedError)

		try:
			buf = self.sendBuffers[0]
			if len(buf) > 0 and buf.start_idx == self.rangeIndex:
				d.callback(buf)
				postpone = False
		except IndexError:
			pass #send buffers empty

		if postpone:
			reactor.callLater(.1,self.waitForData,d)

		return d

	def writeData(self,req=None):
		"""
		write the data at the head of the buffer to the transport. Must take an argument (as defered callbacks pass one in)
		"""
		try:
			buf = self.sendBuffers[0]
			data = buf.getData()
			size = len(buf)
		except:
			self.log.warning("meant to write data, but no buffers were available")
			return

		if size == 0:
			return

		try:
			self.proxyRequest.write(data)
			self.bytes_sent+=size
			buf.clear()
			self.log.info("{} / {} ({}%) sent back to client from peer {}".format(self.bytes_sent, self.requestSize, float(self.bytes_sent) / float(self.requestSize), buf.peer.id))
		except:
			self.log.warning('error writing to client')
			raise
			sys.exit(0)

		self.waitForData()

		if buf.done:
			self.rangeIndex = buf.stop_idx + 1
			del self.sendBuffers[0] #remove the buffer, and update the index

		if self.bytes_sent >= self.requestSize - 1: #wiggle room
			self.endSession(msg="All data for request has been written to client")



