from twisted.internet import reactor
from twisted.internet.defer import Deferred, DeferredList
from twisted.internet.protocol import Protocol, Factory
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers
from twisted.web import proxy, http
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.internet.protocol import Protocol
import urllib2

MINIMUM_FILE_SIZE = 10485760 / 5
PEERPORT = 7779
GIGABYTE = 1073741824
MEGABYTE = 1048576
KILOBYTE = 1024
TEST_FILE = 'http://a1408.g.akamai.net/5/1408/1388/2005110403/1a1a1ad948be278cff2d96046ad90768d848b41947aa1986/sample_iPod.m4v.zip'


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

def httpRange(range):
	"""return the http header formatted string for 
	the request range given by the supplied tuple"""
	return "bytes={}-{}".format(*range)


class PersistentProxyClient():
	"""since twisted's HTTPClient class does not support persistent HTTP connections, a custom class had 
	to be created. This uses an HTTP connection pool and spawns a deferred agent for each HTTP request to 
	the target server"""

	def __init__(self,uri,father,responseWriter,id=None,callback=None):
		self.father = father
		self.uri = uri
		self.pool = HTTPConnectionPool(reactor) #the connection to be persisted
		self.agent = Agent(reactor, pool=self.pool)
		self.id = id
		self.callback = callback 
		self.responseWriter = responseWriter
		self.headersWritten = False

		if id == 0 and id != None: #start immediately
			self.getChunk(self.father.getNextChunk(self.id))

	def getChunk(self,range):
		"""issue the HTTP GET request for the range of the file specified"""
		print(range)
		self.id = range[0]
		defered = self.agent.request(
			'GET',
			self.uri,
			Headers({
				'Range' : [httpRange(range)]
				}),
			None)
		defered.addCallback(self.responseRecieved)
		return defered

	def responseRecieved(self,response):
		"""do some intermediary work with the response, then pass the body along 
		to the printer class, which writes it to the client"""
		if response.code > 206: #206 is the code returned for http range responses
			print("error with response from server")
			return None #TODO: exit gracefully

		finished = Deferred()

		print(response.code,response.version,response.phrase)

		if self.father.handleHeader and self.headersWritten == False:
			for key,val in list(response.headers.getAllRawHeaders()):
				self.father.handleHeader(key,val)
			self.headersWritten = True
			self.father.handleResponseCode(response.version,response.code,response.phrase)
		if self.callback:
			finished.addCallback(self.callback)

		recvr = self.responseWriter(self,finished) 
		response.deliverBody(recvr)
		return finished
