"""
A simple mock web client that shoots a GET request to the proxy server, 
with the host header re-purposed as the actual target of the request.
"""


from pprint import pformat

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.protocol import Protocol
from twisted.web.client import Agent
from twisted.web.http_headers import Headers

class BeginningPrinter(Protocol):
    def __init__(self, finished):
        self.finished = finished

    def dataReceived(self, bytes):
        with open('response.png','a') as f:
            f.write(bytes)

    def connectionLost(self, reason):
        print 'Finished receiving body:', reason.getErrorMessage()
        self.finished.callback(None)


vid = 'a1408.g.akamai.net/5/1408/1388/2005110403/1a1a1ad948be278cff2d96046ad90768d848b41947aa1986/sample_iPod.m4v.zip'
page = 'www.concordma.com'
img = 'i.imgur.com/Crfr2.png'
ip = 'http://127.0.0.1:1337'

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
    response.deliverBody(BeginningPrinter(finished))
    return finished
d.addCallback(cbRequest)

def cbShutdown(ignored):
    reactor.stop()
d.addBoth(cbShutdown)

reactor.run()


