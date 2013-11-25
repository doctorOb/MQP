"""
A simple mock web client that shoots a GET request to the proxy server, 
with the host header re-purposed as the actual target of the request.
"""


from pprint import pformat
import urlparse, os
import sys

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.protocol import Protocol
from twisted.web.client import Agent
from twisted.web.http_headers import Headers


class BeginningPrinter(Protocol):
    def __init__(self, finished, file):
        self.finished = finished
        self.file = file

    def dataReceived(self, bytes):
        self.file.write(bytes)

    def connectionLost(self, reason):
        print 'Finished receiving body:', reason.getErrorMessage()
        self.finished.callback(None)
        self.file.close()



if __name__ == '__main__':
    
    if len(sys.argv) > 2:
        ip = 'http://{}:1337'.format(sys.argv[1])
        url = sys.argv[2]
        
        path = urlparse.urlparse(url).path
        ext = os.path.splitext(path)[1]
        if ext in ['.com','.net','.org']:
            ext = 'html'
    else:
        print "Usage: <Peer IP> <target file>"
        sys.exit(1)

    os.call('rm response.*')
    agent = Agent(reactor)
    d = agent.request(
        'GET',
        ip,
        Headers({'User-Agent': ['Twisted Web Client Example'],
        		'Host' : [page],
        		'Protocol' : ['http']}),
        None)

    def cbRequest(response):
        print 'Response version:', response.version
        print 'Response code:', response.code
        print 'Response phrase:', response.phrase
        print 'Response headers:'
        print pformat(list(response.headers.getAllRawHeaders()))
        finished = Deferred()
        f = open('response.{}'.format(ext), 'w')
        response.deliverBody(BeginningPrinter(finished,f))
        return finished

    d.addCallback(cbRequest)

    def cbShutdown(ignored):
        reactor.stop()

    d.addBoth(cbShutdown)

    reactor.run()


