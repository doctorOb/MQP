
"""
proxyHelpers.py defines a set of common functions used by both the DLPool and peerDaemon files. Included is the protocol used by each peer when inter-communicating. 
"""

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

MINIMUM_FILE_SIZE = 1048576 * 2 #2 mb
PEERPORT = 7779
GIGABYTE = 1073741824
MEGABYTE = 1048576
KILOBYTE = 1024
TEST_FILE = 'http://a1408.g.akamai.net/5/1408/1388/2005110403/1a1a1ad948be278cff2d96046ad90768d848b41947aa1986/sample_iPod.m4v.zip'

PPM_RE = re.compile(r'[\bPPM\.\b]+(?=\r\n)')
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



class BitVector():
	"""a bit vector for storing chunk verification data"""

	def __init__(self):
		self.vector = []

	def _btod(self,binary):
		"""given an array of binary digits, convert to decimal (assume base 2)"""
		p = 0
		total = 0
		for bit in reversed(binary):
			total+=((2*int(bit))**p)
			p+=1

		return total

	def _inverse(self,binary):
		"""produce the inverse of a binary string"""
		flip = []
		for bit in binary:
			flip.insert(0,1 if bit == 0 else 0)
		return flip

	def push(self,elt):
		self.vector.insert(0,elt)

	def value(self):
		"""return the value of the bit vector"""
		return self._btod(self.vector)

	def complement(self):
		"""return the value of the complement of the bit vector"""
		print self._inverse(self.vector)
		return self._btod(self._inverse(self.vector))





class Neighbor():
	"""
	A data object that holds information about a neighboring router. Trust and reliability 
	score is kept here, as well as connection information like IP, port, ect. 

	This class can be serialized to a file so peer information can persist between sessions
	"""

	def __init__(self,ip,id):
		self.ip = ip
		self.id = id #for each session, don't store longterm
		self.public_key = None
		self.filename = '{}.info'.format(ip.replace('.','-'))
		self.alpha_trust = 0
		self.beta_trust = 0
		self.reliability = 0
		self.offeredBandwidth = 0


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
		if (data[:3]) != 'PPM':
			print("invalid protocol message recieved")
			return None

		self.type = data[4:data.index('\r\n')]
		if self.type not in ['ACCEPT','END']:
			self.parseParams()

	def parseParams(self):
		for field in PPM_RE.split(self.data[self.data.index('\r\n'):]):

			field = re.sub('\r\n','',field)
			if len(field) < 1:
				continue
			type = field[0:field.index(':')]

			payload = field[field.index(':')+1:]

			if 'PAYLOAD' in type:
				self.payload = payload
				break
			elif 'HOST' in type:
				self.uri = payload
				break
			elif 'RANGE' in type:
				self.range = payload.split(',')
				break

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
		self.index = 0
		self.callback = callback 
		self.responseWriter = responseWriter
		self.headersWritten = False
		
		if 'http://' not in self.uri:
			self.uri = 'http://' + self.uri

		print self.uri



	def getChunk(self,range):
		"""issue the HTTP GET request for the range of the file specified"""
		if not range:
			print("no range given for getChunk, exiting")
			return None

		print("getting chunk: {}".format(range))
		self.index = range[0]
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

