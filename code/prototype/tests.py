import sys

sys.path.append('proxyHelpers.py')
from proxyHelpers import *


if __name__ == '__main__':
	req = peerProtocolMessage(PPM_DATA('hello, world'))
	print(req.type,req.range,req.payload)