"""
	Main method for the HTTP Bandwidth aggregating proxy. When imported, exposes global variables.
	Running this file will invoke the proxy behavior on the machine. A config.defaults.json file is expected 
	to be provided. This needs to include a mapping of neighbor IP -> public key.
"""
from PybaProx.peerDaemon import PeerHelper, Dispatcher
from PybaProx.BaseProxy import Proxy
from PybaProx.dependencies.config import Config
from PybaProx.proxyHelpers import get_ip, Neighbor
from PybaProx.KeyPair import PKeyPair

from twisted.internet import reactor
from twisted.web import http
from twisted.web.server import Site

import argparse
import os
import signal
import sys

def cleanup(signal,frame):
	"""handle an interrupt signal, make sure sockets are closed properly and exit"""
	print "Caught sigint"
	reactor.stop()
	sys.exit(0)

class BAListener():
	"""A wrapper that couples the logic for instantiating the Peer listener."""
	def __init__(self,reactor=reactor):
		self.configs = reactor.configs
		self.reactor = reactor
		self._setup()

	def _setup(self):
		ph = PeerHelper()
		root = Dispatcher(ph)
		peerFactory = Site(root)
		self.reactor.listenTCP(self.configs.peer_port, peerFactory)

class BAProxy():
	"""A wrapper that groups the logic for instantiating a base proxy."""
	def __init__(self,reactor=reactor):
		self.configs = reactor.configs
		self.reactor = reactor
		self._setup()

	def _setup(self):
		proxyFactory = http.HTTPFactory()
		proxyFactory.protocol = Proxy
		self.reactor.listenTCP(self.configs.proxy_port, proxyFactory)

class ProjConfigs():

	def __init__(self,path,interface):
		self.path = path
		self.cfg = None
		if not self._load():
			return False #don't instantiate
		self.neighbors = dict()
		try:
			self.ip = get_ip(interface)
		except IOError:
			print "Not a valid interface:{}".format(interface)
			sys.exit(1)
		self.key = PKeyPair(self.ip,fname="keys/{}.key".format(self.ip))
		self.peer_port = self.cfg.peer_port
		self.proxy_port = self.cfg.proxy_port
		self.minimum_file_size = self.cfg.minimum_file_size
		self.max_chunk_size = self.cfg.max_chunk_size

		self._init_peers()


	def _load(self):
		try:
			f = file(self.path)
			self.cfg = Config(f)
			return True
		except:
			print "Failed to parse config file"
			return False

	def _init_peers(self):
		for ip in self.cfg.peers:
			if ip in self.ip:
				continue
			print "Configuring Neighbor object for IP: {}".format(ip)
			nbr = Neighbor(ip)
			nbr.key = PKeyPair(ip,fname="keys/{}.key".format(ip))
			self.neighbors[ip] = nbr




if __name__ == '__main__':
	#twisted specific imports

	parser = argparse.ArgumentParser(description='Run a bandwidth aggregation proxy')
	parser.add_argument("-c", "--chunk",type=int, help="Override the default chunk size with a specified value (in bytes)")
	parser.add_argument("-f", "--file",type=str, help="Path to config file")
	parser.add_argument("-i", "--interface",type=str, help="Interface to listen on")
	args = parser.parse_args()
	print args

	cfg_path = os.path.abspath(args.file) if args.file else 'module.cfg'
	interface = args.interface if args.interface else 'eth1'
	reactor.configs = ProjConfigs(path=cfg_path,interface=interface) #borrow the reactors global state to hold the configs
	if args.chunk:
		reactor.configs.max_chunk_size = args.chunk
		print "Using chunk size {}".format(args.chunk)

	bal = BAListener()
	bap = BAProxy()

	signal.signal(signal.SIGINT,cleanup)
	signal.signal(signal.SIGTERM,cleanup)
	reactor.run() #start the server


