
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
from Crypto.Hash import MD5
from Crypto import Random

import socket, struct, fcntl
import urllib2
import re
import random
import os
from time import time as current_time

from Logger import Logger

GIGABYTE = 1073741824
MEGABYTE = 1048576
KILOBYTE = 1024
TEST_FILE = 'http://a1408.g.akamai.net/5/1408/1388/2005110403/1a1a1ad948be278cff2d96046ad90768d848b41947aa1986/sample_iPod.m4v.zip'
VERIFY_SIZE = 12

if os.name != "nt":
	def get_interface_ip(ifname):
		"""get ip for specific interface"""
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		return socket.inet_ntoa(fcntl.ioctl(
				s.fileno(),
				0x8915,  # SIOCGIFADDR
				struct.pack('256s', ifname[:15])
			)[20:24])

def get_ip():
	"""get ip address on both window and linux. 
	Taken from Stack Overflow: http://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
	"""
	ip = socket.gethostbyname(socket.gethostname())
	if ip.startswith("127.") and os.name != "nt":
		interfaces = ["eth0","eth1","eth2","wlan0","wlan1","wifi0","ath0","ath1","ppp0"]
		for ifname in interfaces:
			try:
				ip = get_interface_ip(ifname)
				break
			except IOError:
				pass
	return ip

def deferedError(failure):
	log = Logger()
	log.warning("Defered error: {}".format(failure))

class SlidingWindow():
	"""a Sliding Window class used for monitoring timeouts."""
	def __init__(self,window_size):
		self.time = current_time()
		self.window_size = window_size if window_size else 0

	def reset(self):
		self.time = current_time()

	def elapsed(self):
		return current_time() - self.time

	def timedout(self):
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


def md5hash(msg):
	return MD5.new(msg).digest()

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
		return self._btod(self._inverse(self.vector))


class sendBufOld():
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
		self.received = 0

	def writeData(self,data):
		self.data += data
		self.received += len(data)
		if self.received >= self.size:
			self.done = True

	def getData(self):
		return self.data

	def getPeer(self):
		return self.peer


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

	return int(size)

def httpRange(range):
	"""return the http header formatted string for 
	the request range given by the supplied tuple"""
	return "bytes={}-{}".format(*range)

def TIMEOUT_THRESH():
	return 10000000000 #some really long time idk

