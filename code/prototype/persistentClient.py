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



def httpRange(range):
	"""return the http header formatted string for 
	the request range given by the supplied tuple"""
	return "bytes={}-{}".format(*range)


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
		print('got data')
		self.recvd += len(bytes)
		self.peerHelper.transport.write(bytes)

	def connectionLost(self,reason):
		print("finished recieving body:",reason.getErrorMessage())#sometimes this isn't actually an error
		self.defered.callback(None)

class PersistentProxyClient():
	"""since twisted's HTTPClient class does not support persistent HTTP connections, a custom class had 
	to be created. This uses an HTTP connection pool and spawns a deferred agent for each HTTP request to 
	the target server"""
	def __init__(self,uri,father):
		self.father = father
		self.uri = uri
		self.pool = HTTPConnectionPool(reactor) #the connection to be persisted
		self.agent = Agent(reactor, pool=self.pool)

	def getChunk(self,range):
		"""issue the HTTP GET request for the range of the file specified"""
		print(range)
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
		print response.code
		recvr = RequestBodyReciever(self.father,finished)
		response.deliverBody(recvr)
		return finished



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



	def connectionMade(self):
		print('recieved connection')

	def dataReceived(self,data):
		message = peerProtocolMessage(data)
		self.handleMessage(message)

	def handleMessage(self,message):
		print('got message')
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
			self.client = PersistentProxyClient(self.uri,self)
			return
		if message.type == 'CHUNK' and message.range:
			self.res_len = message.chunkSize
			self.headers['Range'] = 'bytes={}-{}'.format(*message.range)

			print('uri:',self.uri)
			self.client.getChunk(message.range)





if __name__ == '__main__':
	helper = Factory()
	helper.protocol = peerHelper
	reactor.listenTCP(7779, helper)
	reactor.run()