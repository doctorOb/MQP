from twisted.internet import reactor
from twisted.internet.defer import Deferred, DeferredList
from twisted.internet.protocol import Protocol, Factory
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers
from twisted.web import proxy, http
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.internet.protocol import Protocol
import urllib2
import re

MINIMUM_FILE_SIZE = 10485760 / 5
PEERPORT = 7779
GIGABYTE = 1073741824
MEGABYTE = 1048576
KILOBYTE = 1024
TEST_FILE = 'http://a1408.g.akamai.net/5/1408/1388/2005110403/1a1a1ad948be278cff2d96046ad90768d848b41947aa1986/sample_iPod.m4v.zip'

PPM_RE = re.compile('[PPM\.(?=\r\n)]+')
def PPM_INIT(url):
	return "PPM.INIT\r\nPPM.HOST:{}\r\n".format(url)

def PPM_CHUNK(range):
	"""send ppm range chunk from the supplied tuple"""
	return "PPM.CHUNK\r\nPPM.RANGE:{},{}\r\n".format(*range)

def PPM_END():
	return "PPM.END\r\n"

def PPM_ACCEPT():
	return "PPM.ACCEPT\r\n"

def PPM_DATA(data):
	return "PPM.DATA\r\nPPM.PAYLOAD:{}".format(data)

class peerProtocolMessage():
	"""
	class for casting data sent from a peer
	message is of form
	PPM/{type}\r\n
	payload
	"""

	def __init__(self,data):
		self.data = data
		self.uri = None
		self.range = None
		self.payload = None
		print(data)
		if (data[:3]) != 'PPM':
			print("invalid protocol message recieved")
			return None

		self.type = data[4:data.index('\r\n')]
		for field in PPM_RE.split(data[data.index('\r\n'):]):
			if len(field) < 1:
				continue
			type = field[0:field.index(':')]
			payload = field[field.index(':')+1:]
			print(type,payload)

			if type in 'PAYLOAD':
				self.payload = payload
			elif type in 'HOST':
				self.uri = payload
			elif type in 'RANGE':
				self.range = payload.split(',')

	def getUri(self):
		return self.payload[0]

	def getHost(self):
		return urlparse.urlparse(self.uri) if self.uri else None

	def getRange(self):
		return self.range[0],self.range[1] if self.range else None

	def getChunkSize(self):
		return int(self.range[1]) - int(self.range[0]) if self.range else None

	def getPayload(self):
		return self.payload if self.payload else None



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

def TIMEOUT_THRESH():
	return 10000000000 #some really long time idk


class PersistentProxyClient():
	"""
	since twisted's HTTPClient class does not support persistent HTTP connections, a custom class had 
	to be created. This uses an HTTP connection pool and spawns a deferred agent for each HTTP request to 
	the target server
	"""

	def __init__(self,uri,father,responseWriter,cid=None,callback=None):
		self.father = father
		self.uri = uri
		self.pool = HTTPConnectionPool(reactor) #the connection to be persisted
		self.agent = Agent(reactor, pool=self.pool)
		self.id = cid
		self.callback = callback 
		self.responseWriter = responseWriter
		self.headersWritten = False

		if self.id == 0 and self.id != None: #start immediately
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

		if response.code > 206: #206 is the code returned for http range responses
	 		print("error with response from server")

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

