from PybaProx import *
from PybaProx.BaseProxy import Proxy
from PybaProx.peerDaemon import *



if __name__ == '__main__':
	#twisted specific imports
	from twisted.internet import reactor
	from twisted.web import http
	from twisted.web.server import Site


	initialize_environment('config.defaults.json')

	proxyFactory = http.HTTPFactory()
	proxyFactory.protocol = Proxy
	reactor.listenTCP(__opts.proxy_port, proxyFactory)

	ph = PeerHelper()
	root = Dispatcher(ph,__opts.own_key,__oopts.peers)
	peerFactory = Site(root)
	reactor.listenTCP(__opts.peer_port, peerFactory)
	reactor.run()