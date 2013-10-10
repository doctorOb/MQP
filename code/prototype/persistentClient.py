from twisted.internet import reactor
from twisted.internet.defer import Deferred, DeferredList
from twisted.internet.protocol import Protocol, Factory
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers
from twisted.web import proxy, http
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.internet.protocol import Protocol, Factory, ClientFactory, ClientCreator
from twisted.python import log
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.web.http import HTTPClient, Request, HTTPChannel


import urlparse
from urllib import quote as urlquote

import sys
import random
from copy import deepcopy
import urllib2

sys.path.append('proxyHelpers.py')
from proxyHelpers import *


class RequestBodyReciever(Protocol):
	"""needed to actually send the response from a server (because of the way the response object works).
	Passes any data it recieves to the Peer writer. This is an unfortunate side effect of the twisted 
	architecture. A response object cannot pass it's body onwards without the use of this mitigating class"""

	def __init__(self,peerHelper,defered):
		self.peerHelper = peerHelper #reference to peerHelper class that holds an 
									 #open TCP connection with the peer
		self.recvd = 0
		self.defered = defered #placeholder for a deferred callback (incase one is eventually needed)

	def dataReceived(self,bytes):
		self.recvd += len(bytes)
		self.peerHelper.father.transport.write(bytes)


	def connectionLost(self,reason):
		self.defered.callback(None)


class peerProtocolMessage():
	"""class for casting data sent from a peer
	   message is of form
	   PPM/{type}\r\n
	   payload
	"""

	def __init__(self,data):
		self.data = data

		if (data[:3]) != 'PPM':
			print("invalid protocol message recieved")
			return False

		data_start = data.index('\n') - 1
		self.type = data[4:data.index('\r')] #the type of the message

		data = data.replace('\n','').replace('\r','')
		self.payload = data[data_start:].split(',') #the message

		if self.type == 'INIT':
			self.uri = self.getUri()
			self.host = self.getHost()
		if self.type == 'CHUNK':
			self.range = self.getRange()
			self.chunkSize = self.getChunkSize()

	def getUri(self):
		return self.payload[0]

	def getHost(self):
		return urlparse.urlparse(self.payload[0])[1]

	def getRange(self):
		return self.payload[0], self.payload[1]

	def getChunkSize(self):
		return int(self.payload[1]) - int(self.payload[0]) 
		

class peerHelper(Protocol):
	"""this class manages the connection between the feeding client and the server. This acts 
	as a control layer that receiving data requests from the client and handing them to HTTP deferred
	that talk to the actual server. The deferreds will write their data back to the client through a reference 
	to this class's transport object"""

	def __init__(self):
		self.pool = pool = HTTPConnectionPool(reactor)
		self.agent = agent = Agent(reactor, pool=pool)
		self.uri = None
		self.PeerClientFactory = None
		self.headers = {}
		self.rest = None
		self.todo = []
		self.client = None



	def handleHeader(self, key, value):
		pass

	def handleResponseCode(self, version, code, message):
		pass


	def connectionMade(self):
		print('recieved connection')

	def dataReceived(self,data):
		message = peerProtocolMessage(data)
		self.handleMessage(message)

	def handleMessage(self,message):
		print('got message',message.data)

		if message == None:
			return
		if message.type == 'END':
			self.connectionLost()
			return
		if message.type == 'INIT':
			self.transport.write('ACCEPT')
			self.uri = message.uri
			parsed = urlparse.urlparse(self.uri)
			self.headers['host'] = parsed[1]
			self.rest = urlparse.urlunparse(('','') + parsed[2:])
			self.client = PersistentProxyClient(self.uri,self,RequestBodyReciever)
			return
		if message.type == 'CHUNK' and message.range:
			self.res_len = message.chunkSize
			self.headers['Range'] = httpRange(message.range)

			print('uri:{} range: {}'.format(self.uri,self.headers['Range']))
			self.client.getChunk(message.range)





if __name__ == '__main__':
	helper = Factory()
	helper.protocol = peerHelper
	reactor.listenTCP(7779, helper)
	reactor.run()