from twisted.web import proxy, http
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers
from twisted.internet import reactor
from twisted.internet.protocol import Protocol, Factory, ClientFactory
from twisted.python import log
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.web.http import HTTPClient, Request, HTTPChannel

import urlparse
from urllib import quote as urlquote

import sys
from copy import deepcopy
import urllib2

MINIMUM_FILE_SIZE = 10485760

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

#log.startLogging(sys.stdout)

class ProxyClient(HTTPClient):
	_finished = False
	bytes_recvd = 0
	def __init__(self, command, rest, version, headers, data, father):
		self.father = father
		self.command = command
		self.rest = rest

		if "proxy-connection" in headers:
			del headers["proxy-connection"]
		headers["connection"] = "close"
		headers.pop('keep-alive', None)
		self.headers = headers
		self.data = data

	def connectionMade(self):
		self.sendCommand(self.command, self.rest)
		for header, value in self.headers.items():
			self.sendHeader(header,value)
			if header == 'Range':
				print("range request:{}".format(value))
		self.endHeaders()
		self.transport.write(self.data)

	def handleStatus(self, version, code, message):
		self.father.setResponseCode(int(code),message)

	def handleHeader(self, key, value):
		if key.lower() in ['server', 'date', 'content-type']:
			self.father.responseHeaders.setRawHeaders(key, [value])
		else:
			self.father.responseHeaders.addRawHeader(key, value)

	def handleResponsePart(self, buffer):
		self.bytes_recvd += len(buffer)
		self.father.write(buffer)

	def handleResponseEnd(self):
		print("read {} bytes total form server",self.bytes_recvd)
		if not self._finished:
			self._finished = True
			self.father.finish()
			self.transport.loseConnection()


class PeerProxyClient(HTTPClient):
	_finished = False
	bytes_recvd = 0
	def __init__(self, command, rest, version, headers, data, father):
		self.father = father
		self.command = command
		self.rest = rest

		if "proxy-connection" in headers:
			del headers["proxy-connection"]
		headers["connection"] = "close"
		headers.pop('keep-alive', None)
		self.headers = headers
		self.data = data

	def connectionMade(self):
		self.sendCommand(self.command, self.rest)
		for header, value in self.headers.items():
			self.sendHeader(header,value)
			if header == 'Range':
				print("range request:{}".format(value))
		self.endHeaders()
		self.transport.write(self.data)

	def handleStatus(self, version, code, message):
		self.father.setResponseCode(int(code),message)

	def handleHeader(self, key, value):
		if key.lower() in ['server', 'date', 'content-type']:
			self.father.responseHeaders.setRawHeaders(key, [value])
		else:
			self.father.responseHeaders.addRawHeader(key, value)

	def handleResponsePart(self, buffer):
		self.bytes_recvd += len(buffer)
		self.father.write(buffer)

	def handleResponseEnd(self):
		print("read {} bytes total form server",self.bytes_recvd)
		if not self._finished:
			self._finished = True
			self.father.finish()
			self.transport.loseConnection()

class ProxyClientFactory(ClientFactory):

	protocol = ProxyClient

	def __init__(self,command,rest,version,headers,data,father):
		self.father = father
		self.command = command
		self.rest = rest
		self.headers = headers
		self.data = data
		self.version = version

	def buildProtocol(self,addr):
		return self.protocol(self.command, self.rest, self.version,
			self.headers, self.data, self.father)


class PeerClientFactory(Factory):

	protocol = PeerReciever

	def __init__(self, command, header, version, father):
		self.father = father
		self.command = command
		self.header = header
		self.version = version

	def buildProtocol(self,addr):
		return PeerReciever()


class ProxyRequest(Request):

	protocols = {'http': ProxyClientFactory}
	ports = {'http': 80}

	def __init__(self, channel, queued, reactor=reactor):
		Request.__init__(self, channel, queued)
		self.reactor = reactor

	def process(self):
		parsed = urlparse.urlparse(self.uri)
		protocol = parsed[0]
		host = parsed[1]
		port = self.ports[protocol]
		if ':' in host:
			host, port = host.split(':')
			port = int(port)
		rest = urlparse.urlunparse(('','') + parsed[2:])
		if not rest:
			rest = rest + '/'
		class_ = self.protocols[protocol]
		headers = self.getAllHeaders().copy()
		if 'host' not in headers:
			headers['host'] = host
		self.content.seek(0, 0)
		s = self.content.read()
		fileSize = getFileSize(self.uri)

		if fileSize >= MINIMUM_FILE_SIZE / 2:
			headers['Range'] = "bytes={}-{}".format(0, fileSize/2)
			newHeaders = deepcopy(headers)
			print("using 2 streams")
			newHeaders['Range'] = "bytes={}-{}".format(fileSize/2,fileSize)
			peerClientFactory = PeerClientFactory(self.method,)
			self.reactor.connectTCP('localhost',7779,PeerClientFactory)

			
		clientFacotry = class_(self.method, rest, self.clientproto, headers, s, self)
		self.reactor.connectTCP(host,port,clientFacotry)

class Proxy(HTTPChannel):
	requestFactory = ProxyRequest

class PeerReciever(Protocol):
	def dataReceived(self,data):
		print"got data",data

class peerHelper(Protocol):
	def connectionMade(self):
		self.transport.write("hey there")

	def dataReceived(self,data):
		print(data)




if __name__ == '__main__':
	factory = http.HTTPFactory()
	factory.protocol = Proxy
	reactor.listenTCP(8000, factory)
	reactor.run()