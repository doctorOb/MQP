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


class PeerProxyClient(HTTPClient):
	_finished = False
	bytes_recvd = 0
	def __init__(self, command, rest, headers, father):
		self.father = father
		self.command = command
		self.rest = rest


		if "proxy-connection" in headers:
			del headers["proxy-connection"]
		headers["connection"] = "close"
		headers.pop('keep-alive', None)

		father.addReference(self)
		
		self.headers = headers


	def connectionMade(self):
		self.sendCommand(self.command, self.rest)
		for header, value in self.headers.items():
			self.sendHeader(header,value)
			if header == 'Range':
				print("range request:{}".format(value))
		self.endHeaders()

	def handleStatus(self, version, code, message):
		if int(code) == 200 or int(code) == 206:
			pass
		else:
			print('recieved error code:',code)
			self.father.transport.loseConnection()

	def handleHeader(self, key, value):
		pass

	def handleResponsePart(self, buffer):
		self.bytes_recvd += len(buffer)
		self.father.transport.write(buffer)

	def handleResponseEnd(self):
		print('data ended')
		next = self.father.nextChunk()
		if next != None:
			self.headers['Range'] = 'bytes={}-{}'.format(next)
			self.endHeaders()
		else:
			print("nothing to do right now")
		#loop and make a new connection
		# if not self._finished:
		# 	self._finished = True
		# 	self.father.finish()
		# 	self.transport.loseConnection()

		
class PeerProxyClientFactory(ClientFactory):

	protocol = PeerProxyClient

	def __init__(self,command,rest,headers,father):
		self.father = father
		self.command = command
		self.rest = rest
		self.headers = headers

	def buildProtocol(self,addr):
		return self.protocol(self.command, self.rest, self.headers,self.father)


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

		print(self.data)
		self.uri = self.getUri()
		self.host = self.getHost()
		self.range = self.getRange()
		self.chunkSize = self.getChunkSize()

	def getUri(self):
		if self.type != 'INIT':
			return None
		return self.payload[0]

	def getHost(self):
		if self.type != 'INIT':
			return None
		return urlparse.urlparse(self.payload[0])[1]

	def getRange(self):
		if self.type != 'CHUNK':
			return None
		return self.payload[0], self.payload[1]

	def getChunkSize(self):
		if self.type != 'CHUNK':
			return None
		return int(self.payload[1]) - int(self.payload[0]) 

class PeerReciever(Protocol):
	def __init__(self,father):
		self.father = father
		
	def dataReceived(self,data):
		self.father.transport.write(data)
		

class peerHelper(Protocol):

	def __init__(self):
		self.pool = pool = HTTPConnectionPool(reactor)
		self.agent = agent = Agent(reactor, pool=pool)
		self.uri = None
		self.PeerClientFactory = None
		self.headers = {}
		self.rest = None
		self.todo = []
		self.httpClient = None



	def connectionMade(self):
		print('recieved connection')

	def dataReceived(self,data):
		message = peerProtocolMessage(data)
		self.handleMessage(message)

	def addReference(self,client):
		self.httpClient = client
	def nextChunk(self):
		if len(self.todo) > 0:
			return self.todo.reverse().pop()
		else:
			return None

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
			return
		if message.type == 'CHUNK':
			self.res_len = message.chunkSize;
			self.headers['Range'] = 'bytes={}-{}'.format(*message.range)

			print('uri:',self.uri)
			if self.PeerClientFactory == None:
				self.PeerClientFactory = PeerProxyClientFactory('GET',self.rest,self.headers,self)
				print('host:',self.headers['host'])
				reactor.connectTCP(self.headers['host'],80,self.PeerClientFactory)
			else:
				self.todo.append(message.chunkSize)
				self.httpClient.handleResponseEnd()





if __name__ == '__main__':
	helper = Factory()
	helper.protocol = peerHelper
	reactor.listenTCP(7779, helper)
	reactor.run()