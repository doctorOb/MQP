
"""
CANDIDATE FOR CLEANING

proxyHelpers.py defines a set of common functions and objects used by most classes. All global constants are defined here.
"""

from twisted.internet import reactor
from twisted.internet.defer import Deferred, DeferredList
from twisted.internet.protocol import Protocol, Factory
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers
from twisted.web import proxy, http
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.internet.protocol import Protocol

from Crypto.PublicKey import RSA
from Crypto import Random

import socket, struct, fcntl
import urllib2
import re
import os
import time


GIGABYTE = 1073741824
MEGABYTE = 1048576
KILOBYTE = 1024
TEST_FILE = 'http://a1408.g.akamai.net/5/1408/1388/2005110403/1a1a1ad948be278cff2d96046ad90768d848b41947aa1986/sample_iPod.m4v.zip'

class SlidingWindow():
	"""a Sliding Window class used for monitoring timeouts."""
	def __init__(self,window_size):
		self.time = time.now()
		self.window_size = window_size if window_size else 0

	def reset():
		self.time = time.now()

	def elapsed():
		return time.now() - self.time

	def timedout():
		if self.elapsed() > self.window_size:
			return True
		else:
			return False


def read_key(fname):
	"""read in the key objects from the stored dictionary, return a dict"""
	with open(fname,'r') as f:
		ret = ast.literal_eval(f.read())

	for key,val in ret: #turn them into RSA key objects
		ret[key] = RSA.importKey(val)
	return ret





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


class Neighbor():
	"""
	A data object that holds information about a neighboring router. Trust and reliability 
	score is kept here, as well as connection information like IP, port, ect. 

	This class can be serialized to a file so peer information can persist between sessions
	"""

	def __init__(self,ip,id=None):
		self.ip = ip
		self.id = id #for each session, don't store longterm
		self.key = None
		self.filename = '{}.info'.format(ip.replace('.','-'))
		self.alpha_trust = 0
		self.beta_trust = 0
		self.reliability = 0
		self.offeredBandwidth = 0




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
	 		print("error with response from server({})".format(response.code))

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

