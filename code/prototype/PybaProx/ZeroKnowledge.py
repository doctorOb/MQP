from twisted.internet import defer, reactor
from twisted.internet.protocol import Protocol
from twisted.web.http import HTTPClient, Request, HTTPChannel
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.task import deferLater
from twisted.web import proxy, http
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers

from Logger import Logger




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
		self.log = Logger()


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