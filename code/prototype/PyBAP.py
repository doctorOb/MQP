"""
	Main method for the HTTP Bandwidth aggregating proxy. When imported, exposes global variables.
	Running this file will invoke the proxy behavior on the machine. A config.defaults.json file is expected 
	to be provided. This needs to include a mapping of neighbor IP -> public key.
"""

from RecordKeeper import RecordKeeper
from sys import exit
from proxyHelpers import Neighbor
from KeyPair import PKeyPair

import string
import os
import sys
import socket, struct, fcntl


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



def init_peers(peer_ips,my_ip):
	"""create a dict of ip -> neighbor classes, where the neighbors key is assumed
	to exist within a [neighbor_ip].key file in the running directory."""
	ret = dict()
	for ip in peer_ips:
		if ip in my_ip:
			continue

		print "Configuring Neighbor object for IP: {}".format(ip)
		nbr = Neighbor(ip)
		nbr.key = PKeyPair(ip)
		ret[ip] = nbr
	return ret

global GLOBS_SET
global __opts
class Glob():
	pass


try:
	if GLOBS_SET is None:
		__opts = GLob()
		print "initializing global variables"
		configs = RecordKeeper('config.defaults')
		#initialize globals
		__opts.my_ip = get_ip()
		__opts.peer_port = int(configs['PEER_PORT'])
		__opts.proxy_port = int(configs['PROXY_PORT'])
		__opts.minimum_file_size = int(configs['MINIMUM_FILE_SIZE'])
		__opts.peers = init_peers(configs['PEERS'],MY_IP)
		__opts.chunk_size = int(configs['CHUNK_SIZE'])
		__opts.own_key = PKeyPair(ip=__opts.my_ip)
		GLOBS_SET = True
	else:
		pass
except:
	print "Unexpected error:", sys.exc_info()[0]
	raise
	print("Error initializing proxy from config file. Make sure config.defaults.json supplies the necessary information!\n")
	exit(0)



if __name__ == '__main__':
	#twisted specific imports
	from twisted.internet import reactor
	from twisted.web import http
	from twisted.web.server import Site

	#project specific imports
	from DLP import DownloadPool
	from BaseProxy import Proxy
	from peerDaemon import PeerHelper, Dispatcher

	#Auto configure neighbor IP -> pub_key mapping from a supplied file.


	print "Starting HTTP Proxy"
	proxyFactory = http.HTTPFactory()
	proxyFactory.protocol = Proxy
	reactor.listenTCP(__opts.proxy_port, proxyFactory)

	ph = PeerHelper()
	root = Dispatcher(ph,__opts.own_key,__oopts.peers)
	peerFactory = Site(root)
	reactor.listenTCP(__opts.peer_port, peerFactory)
	reactor.run()