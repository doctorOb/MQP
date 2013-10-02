import urllib2
from scapy.all import *

url = "http://a1408.g.akamai.net/5/1408/1388/2005110403/1a1a1ad948be278cff2d96046ad90768d848b41947aa1986/sample_iTunes.mov.zip"

def setupConnection(dest):
	"""Perform a TCP syn-syn-ack 3-way handshake with the destionation"""

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



#url = "http://download.thinkbroadband.com/10MB.zip"

def split_http_urllib():
    file_name = url.split('/')[-1]
    file_size = getFileSize(url)
    req1 = urllib2.Request(url)
    req2 = urllib2.Request(url)
    req1.add_header('Range','bytes={}-{}'.format(0,file_size/2))
    req2.add_header('Range','bytes={}-{}'.format(file_size/2,0))

    res1 = urllib2.urlopen(req1)
    res2 = urllib2.urlopen(req2)


    f = open(file_name, 'wb')
    print "Downloading: %s Bytes: %s" % (file_name, file_size)

    file_size_dl = 0
    block_sz = 8192
    fp1 = 0
    fp2 = file_size / 2
    while True:
        buffer = res1.read(block_sz)
        if not buffer:
            break

        file_size_dl += len(buffer)

        f.seek(fp1,0)
        fp1 += len(buffer)
        f.write(buffer)

        buffer = res2.read(block_sz)
        if not buffer:
        	break
        file_size_dl += len(buffer)
        f.seek(fp2,0)
        fp2 += len(buffer)
        f.write(buffer)

        status = r"%10d  [%3.2f%%]" % (file_size_dl, file_size_dl * 100. / file_size)
        status = status + chr(8)*(len(status)+1)
        print status,

    f.close()


def scapy_tcp_test_server():
    tcp_syn = IP(dst="192.168.1.1")/TCP(dport=25050, flags='S', seq=10000)
    tcp_syn_ack = send(tcp_syn)

    print tcp_syn_ack
    tcp_ack = IP(dst="192.168.1.1")/TCP(dport=25050,flags='A',seq=tcp_syn_ack.ack,
        ack=tcp_syn_ack.syn+1)
    tcp_pack1 = srp1(tcp_ack)

    i = 0
    while True:
        i = i + 1
        print i,

if __name__ == '__main__':
    scapy_tcp_test_server()
