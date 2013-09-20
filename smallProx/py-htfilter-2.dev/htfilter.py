#!/usr/bin/python
"""
 * htfilter v.2.dev
 *  Author: Jiang Yio
 *          <http://www.inportb.com/>
 *    Date: August 22, 2008
 * License: Creative Commons Attribution-Share Alike 3.0 License
 *          <http://creativecommons.org/licenses/by-sa/3.0/>
"""

try:
	import psyco
	psyco.profile()
except ImportError:
	print "Please install Psyco for optimal performance."

import asyncore, asynchat, socket, string
import sys, imp, cgi, os, optparse, tempfile
from urlparse import urlparse, urlunparse
from collections import deque
import __builtin__
from event import Event
try:
	from cStringIO import StringIO
except:
	from StringIO import StringIO

def popall(self):
	# preallocate list
	r = len(self)*[None]
	for i in xrange(len(r)):
		r[i] = self.popleft()
	return r

def headfilter(headers,filter):
	removekeys = {}
	ret = {}
	for item in filter:
		ret[item] = {}
	for (key,val) in headers.items():
		for item in filter:
			if key[:len(item)] == item:
				ret[item][key[len(item):]] = val
				removekeys[key] = True
	for key in removekeys:
		del headers[key]
	return ret

class HookException(Exception,object):
	pass

class HeadParser(dict):
#	def __del__(self):
#		HeadParser.ct -= 1
#		print '>>> HeadParser',HeadParser.ct
	def __init__(self,infile=None,other=None,*args):
		try:
			HeadParser.ct += 1
		except:
			HeadParser.ct = 1
		if infile:
			lines = infile.readlines()
			for line in lines:
				try:
					k,v=line.split(':',1)
					dict.__setitem__(self,k.lower(),v.strip())
				except:
					pass
		if other:
			# Doesn't do keyword args
			if isinstance(other,dict):
				for k,v in other.items():
					dict.__setitem__(self,k.lower(),v)
			else:
				for k,v in other:
					dict.__setitem__(self,k.lower(),v)
	def __getitem__(self,key):
		return dict.__getitem__(self,key.lower())
	def __setitem__(self,key,value):
		dict.__setitem__(self,key.lower(),value)
	def __contains__(self,key):
		return dict.__contains__(self,key.lower())
	def has_key(self,key):
		return dict.has_key(self,key.lower())
	def get(self,key,default=None):
		return dict.get(self,key.lower(),default)
	def setdefault(self,key,default=None):
		return dict.setdefault(self,key.lower(),default)
	def update(self,other):
		for k,v in other.items():
			dict.__setitem__(self,k.lower(),v)
	def fromkeys(self,iterable,value=None):
		d = HeadParser()
		for k in iterable:
			dict.__setitem__(d,k.lower(),value)
		return d
	def pop(self,key,default=None):
		return dict.pop(self,key.lower(),default)
	# HTTP header definitions
	def getheader(self,key,default=None):
		return self.get(key,default)
	def get_headers(self):
		return self.keys()
	def stringify(self):
		l = []
		for (key,val) in self.items():
			l.append('%s: %s'%(key,val))
		return '\r\n'.join(l)
	headers = property(get_headers)

class ProxyDispatcher(asyncore.dispatcher):
	def __init__(self,configuration,ip,port):
		asyncore.dispatcher.__init__(self)
		self.create_socket(socket.AF_INET,socket.SOCK_STREAM)
		self.set_reuse_addr()
		self.bind((ip,port))
		self.listen(5)
		self.ct = 0
		self.configuration = configuration
		baseconf = configuration()
		self.hooks = []
		for fn in baseconf['hooks']:
			sym = loadsymbol(fn,'main')
			if sym != None:
				self.hooks.append(sym())
	def handle_accept(self):
		try:
			conn,addr = self.accept()
		except socket.error:
			self.log_info('warning: server accept() threw an exception','warning')
			return
		except TypeError:
			self.log_info('warning: server accept() threw EWOULDBLOCK','warning')
			return
#		print '#',self.ct
		ProxyServer(self,conn,addr)
		self.ct += 1
	def getHooks(self,config,request,events):
		o = []
		for hook in self.hooks:
			h = hook(config,events,request)
			if h != None:
				o.append(h)
		return o
	def delHooks(self,hooks):
		for hook in hooks:
			hook.destruct()

class ProxyServer(asynchat.async_chat):
#	def __del__(self):
#		ProxyServer.ct -= 1
#		print '>>> ProxyServer',ProxyServer.ct
	def __init__(self,proxy,conn,addr):
#		try:
#			ProxyServer.ct += 1
#		except:
#			ProxyServer.ct = 1
		asynchat.async_chat.__init__(self,conn)
		self.client_address = addr
		self.proxy = proxy
		self.inhead = deque()
		self.inbody = None
		self.degenerate = False
		self.set_terminator('\r\n')
		self.found_terminator = self.callback
		self.events = {'exception':Event(),'txhead':Event(),'txbody':Event(),'rxhead':Event(),'rxbody':Event()}
		self.config = proxy.configuration()
		self.process = self.processor()
		self.isreadable = True
		self.iswritable = False
		self.collectHead()
	def callback(self):
		try:
			self.process.next()
		except StopIteration:
			pass
	def exception(self,ex):
		raise ex
	def processor(self):
		request = {'preamble':None,'headers':None,'body':None,'query':None}
		self.events['exception'] += self.exception
		# process preamble
		preamble = '\r\n'.join(popall(self.inhead)).split(None,2)
		if len(preamble) < 2:
			raise 'InvalidRequestPreamble'
		elif len(preamble) == 2:
			self.degenerate = True
			request['preamble'] = {'command':preamble[0],'url':urlparse(preamble[1]),'version':'HTTP/0.9'}
			request['headers'] = HeadParser()
		else:
			request['preamble'] = {'command':preamble[0],'url':urlparse(preamble[1]),'version':preamble[2]}
			# process headers
			while True:
				ihlen = len(self.inhead)
				yield None
				if len(self.inhead) == ihlen:
					break
			fdata = StringIO('\r\n'.join(popall(self.inhead)))
			# display data here
			request['headers'] = HeadParser(fdata)
			fdata.close()
		self.inhead.clear()
		if request['preamble']['url'].query:
			request['query'] = cgi.parse_qs(request['preamble']['url'].query,keep_blank_values=1)
		# set up hooks
		self.hooks = self.proxy.getHooks(self.config,request,self.events.copy())
		# EVENT
		self.events['txhead'](self.config,request)
		hdr = headfilter(request['headers'],['proxy-'])
		try:
			del request['headers']['accept-encoding']
		except:
			pass
		try:
			del request['headers']['keep-alive']
		except:
			pass
		request['headers']['connection'] = 'close'
		self.collectBody()
		try:
			length = int(request['headers'].getheader('content-length','0'))
			if length > 0:
				self.set_terminator(length)
				yield None	# come back when there's enough data
			self.inbody.seek(0)
			request['body'] = self.inbody.getvalue()
		except:
			pass;
		# EVENT
		self.events['txbody'](self.config,request)
		# send headers and data to server
		self.isreadable = False
		self.iswritable = True
		ProxyClient(self,request)
	def collectHead(self):
		self.inhead.clear()
		self.collect_incoming_data = self.collect_incoming_data_head
	def collectBody(self):
		try:
			self.inbody.close()
		except:
			pass
		self.inbody = StringIO()
		self.collect_incoming_data = self.collect_incoming_data_body
	def dereference(self):
		self.events['exception'] -= self.exception
		self.found_terminator = None
		self.collect_incoming_data = None
		self.handle_error = None
		self.proxy = None
	def collect_incoming_data_head(self,data):
		self.inhead.append(data)
	def collect_incoming_data_body(self,data):
		self.inbody.write(data)
	def handle_close(self):
		if not self.proxy:
			return
		self.handle_error = self.discard_buffers
		while self.producer_fifo or self.ac_out_buffer:
			self.initiate_send()
		self.iswritable = False
		self.proxy.delHooks(self.hooks)
		self.close()
		# break circular references
		self.dereference()

class ProxyClient(asynchat.async_chat):
#	def __del__(self):
#		ProxyClient.ct -= 1
#		print '>>> ProxyClient',ProxyClient.ct
	def __init__(self,server,request):
		try:
			ProxyClient.ct += 1
		except:
			ProxyClient.ct = 1
		asynchat.async_chat.__init__(self)
		self.server = server
		self.request = request
		self.chain = None
		try:
			if 'chain' in self.server.config:
				self.chain = (str(self.server.config['chain'][0]),int(self.server.config['chain'][1]))
		except:
			print 'error while proxy-chaining'
		self.degenerate = server.degenerate
		self.response = {'preamble':None,'headers':None,'body':None}
		self.create_socket(socket.AF_INET,socket.SOCK_STREAM)
		if self.chain == None:
			url = request['preamble']['url']
			try:
				port = int(url.port)
			except:
				port = 80
			self.connect((url.hostname,port))
		else:
			self.connect(self.chain)
		self.inhead = deque()
		self.inbody = None
		self.buffer = 0
		self.isreadable = False
		self.iswritable = True
		self.collectHead()
	def handlePreamble(self):
		preamble = ''.join(popall(self.inhead)).split(None,2)
		self.inhead.clear()
		if len(preamble) < 3:
			raise 'InvalidResponsePreamble'
		self.response['preamble'] = {'version':preamble[0],'code':int(preamble[1]),'reason':preamble[2]}
		self.found_terminator = self.handleHeaders
		self.set_terminator('\r\n\r\n')
	def handleHeaders(self):
		fdata = StringIO(''.join(popall(self.inhead)))
		self.inhead.clear()
		self.response['headers'] = HeadParser(fdata)
		fdata.close()
		self.sendHeaders()
		self.set_terminator(None)
#		length = int(self.response['headers'].getheader('content-length','-1'))
#		if length > 0:
#			self.set_terminator(length)
#		elif length < 0:
#			self.set_terminator(None)
#		else:
#			self.close_when_done()
	def sendHeaders(self):
		try:
			self.server.events['rxhead'](self.server.config,self.request,self.response)
		except Exception,ex:
			self.handle_close()
			raise ex
		if not self.degenerate:
			self.server.push('%s %d %s\r\n%s\r\n\r\n'%(self.response['preamble']['version'],self.response['preamble']['code'],self.response['preamble']['reason'],self.response['headers'].stringify()))
		self.buffer = self.server.config.get('buffer',0)
		self.collectBody()
	def sendBody(self):
		if self.inbody:
			self.response['body'] = self.inbody
			self.inbody = None
		try:
			self.server.events['rxbody'](self.server.config,self.request,self.response)
		except Exception,ex:
			if self.buffer == 2:
				self.handle_close()
				raise ex
		if self.buffer == 2:
			self.response['body'].seek(0)
			readsize = int(self.server.config.get('chunk',1048576))
			while True:
				data = self.response['body'].read(readsize)
				if data == '':
					break
				self.server.push(data)
			del data
		self.response['body'] = None
	def dereference(self):
		self.collect_incoming_data = None
		self.found_terminator = None
		self.server = None
	def handle_connect(self):
		self.isreadable = True
		if self.chain == None:
			path = urlunparse(('','')+self.request['preamble']['url'][2:])
		else:
			path = urlunparse(self.request['preamble']['url'])
		if self.degenerate:
			self.push('%s %s\r\n'%(self.request['preamble']['command'],path))
			if self.request['body'] != None:
				self.push(self.request['body'])
			self.response['preamble'] = {'version':'HTTP/0.9','code':200,'reason':'OK'}
			self.response['headers'] = HeadParser()
			self.sendHeaders()
			self.set_terminator(None)
		else:
			self.found_terminator = self.handlePreamble
			self.set_terminator('\r\n')
			self.push('%s %s %s\r\n%s\r\n\r\n'%(self.request['preamble']['command'],path,self.request['preamble']['version'],self.request['headers'].stringify()))
			if self.request['body'] != None:
				self.push(self.request['body'])
	def collectHead(self):
		self.inhead.clear()
		self.collect_incoming_data = self.collect_incoming_data_head
	def collectBody(self):
		try:
			self.inbody.close()
		except:
			pass
		if self.buffer == 1:
			self.inbody = tempfile.TemporaryFile()
			self.collect_incoming_data = self.collect_incoming_data_body_pass
		elif self.buffer == 2:
			self.inbody = tempfile.TemporaryFile()
			self.collect_incoming_data = self.collect_incoming_data_body_hold
		else:
			self.buffer = 0
			self.inbody = None
			self.collect_incoming_data = self.collect_incoming_data_body
		self.iswritable = False
	def collect_incoming_data_head(self,data):
		self.inhead.append(data)
	def collect_incoming_data_body(self,data):
		self.server.push(data)
	def collect_incoming_data_body_pass(self,data):
		self.server.push(data)
		self.inbody.write(data)
	def collect_incoming_data_body_hold(self,data):
		self.inbody.write(data)
	def handle_close(self):
		if not self.server:
			return
		self.isreadable = False
		self.sendBody()
		self.server.handle_close()
		self.close()
		# break circular references
		self.dereference()

def loadsymbol(filepath,symbol):
	obj = None;
	modname,extension = os.path.splitext(os.path.split(filepath)[-1]);
	if extension.lower() == '.py':
		pymod = imp.load_source(modname,filepath);
	elif extension.lower() == '.pyc':
		pymod = imp.load_compiled(modname,filepath);
	else:
		return None;
	if symbol in dir(pymod):
		return eval('pymod.'+symbol);
	return None;

if __name__ == '__main__':
	usage = "usage: %prog [-p<port>] [-c<config.py>]"
	parser = optparse.OptionParser(usage)
	parser.add_option('-p','--port',dest='port',type='int',help='Port to listen on (default 8080)',default=8080,action='store')
	parser.add_option('-c','--conf',dest='conf',type='str',help='COnfiguration file (default config.py)',default='config.py',action='store')
	options,args = parser.parse_args()
	configuration = loadsymbol(options.conf,'configuration')
	proxy = ProxyDispatcher(configuration,'',options.port)
	asyncore.loop()
