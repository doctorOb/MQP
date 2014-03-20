"""
	Main method for the HTTP Bandwidth aggregating proxy. When imported, exposes global variables.
	Running this file will invoke the proxy behavior on the machine. A config.defaults.json file is expected 
	to be provided. This needs to include a mapping of neighbor IP -> public key.
"""

from RecordKeeper import RecordKeeper
from sys import exit
from proxyHelpers import Neighbor
from KeyPair import PKeyPair




def init_peers(peer_ips):
	"""create a dict of ip -> neighbor classes, where the neighbors key is assumed
	to exist within a [neighbor_ip].key file in the running directory."""
	ret = dict()
	for ip in peer_ips:
		nbr = Neighbor(ip)
		nbr.key = PKeyPair(ip)
		ret[ip] = nbr
	return ret

try:
	configs = RecordKeeper('config.defaults')
	#initialize globals
	PEER_PORT = int(configs['PEER_PORT'])
	PROXY_PORT = int(configs['PROXY_PORT'])
	MINIMUM_FILE_SIZE = int(configs['MINIMUM_FILE_SIZE'])
	PEERS = init_peers(configs['PEERS'])
	CHUNK_SIZE = int(configs['CHUNK_SIZE'])
except:
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
	from proxyHelpers import get_ip

	#Auto configure neighbor IP -> pub_key mapping from a supplied file.


	proxyFactory = http.HTTPFactory()
	proxyFactory.protocol = Proxy
	reactor.listenTCP(PROXY_PORT, proxyFactory)
	reactor.run()

	myIP = get_ip()
	if '127.0.0.1' in myIP:
		#local testing
		pass

	
	own_key = PKeyPair(ip=myIP)
	ph = PeerHelper()
	root = Dispatcher(ph,own_key,PEERS)
	peerFactory = Site(root)
	reactor.listenTCP(PEER_PORT, peerFactory)
	reactor.run()