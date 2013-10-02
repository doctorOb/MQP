import math
import string

GIGABYTE = 1073741824
MEGABYTE = 1048576
KILOBYTE = 1024

"""A proof of concept pseudo class implementation of a download splitting router. This provides a base case to go by as I tighten up the algorithm, and will eventually be ported to the actual proxy.

	The basic premise is this:

	> Query all neighboring routers for their available bandwidth.
	> Routers respond with the average bandwidth between themselves and
	  their peers (who have not yet been queried).
	> With peer bandwidth data, calculate the percentage of the 
	  file to delegate to each eligible peer.
	> Each peer then repeats the process with their chunk, further 
	  dividing the download into more subchunks until the point is reach 
	  where the link cost (router to router bandwidth) outweighs the benefit 
	  of adding another peer to the download."""

def downloadTime(fsize,bandwidth):
	"""compute the estimated download time (in seconds) of a packet given its size
	(in megabytes), and the available bandwidth in mbps"""
	return ((fsize * 8388608) / bandwidth) / 1000000 #return number of seconds

def btom(bytes):
	"""convert the given number of bytes to a megabyte"""
	return bytes / MEGABYTE

def btog(bytes):
	"""convert the given number of bytes to gigabytes"""
	return bytes / GIGABYTE

def btok(bytes):
	"""covert the given number of bytes to kilobytes"""
	return bytes / KILOBYTE

def printSize(bytes):
	"""determine which byte prefix to use when printing, and
	return a tuple of the amount and proper prefix used"""
	if bytes > GIGABYTE:
		return btog(bytes),"gb"
	elif bytes > MEGABYTE:
		return btom(bytes),"mb"
	elif bytes > KILOBYTE:
		return btok(bytes),"kb"
	else:
		return bytes,"bytes"

class Router():
	"""This is an abstract representation of a MQP modified router, focusing
	on the packet division process as a function of total or available bandwidth"""
	def __init__(self,name, bandwidth, wirelessBandwidth, peers):
		self.bandwidth = bandwidth
		self.peers = peers
		self.wirelessBandwidth = wirelessBandwidth
		self.name = name

	def getDTestimate(self,fsize):
		"""compute the estimated download time for a file in seconds"""
		return downloadTime(fsize,self.bandwidth)

	def getTransportationEstimate(self,fsize):
		"""compute the estimated intra-router transport time of the packet size,
		this depends on the 802.11 wireless speed"""
		return downloadTime(fsize,self.wirelessBandwidth)

	def getNetBandwidth(self,fsize):
		"""the average bandwidth guarantee between the router and its neighbors"""
		averageBandwidth = self.bandwidth
		for peer in self.peers:
			averageBandwidth = averageBandwidth + peer.getNetBandwidth(fsize)
		return float(averageBandwidth) / (len(self.peers) + 1)

	def dividePacket(self,start,stop):
		"""Query each neighbor for their netBandwidth, and divide the packet accordingly"""
		fsize = stop - start

		aggregateBandwidth = self.bandwidth #the total bandwidth amongst peers and self
		peerBandwidth = {} #the bandwidth offered by each peer
		peerChunk = {} #the chunk (in bytes) to delegate to each peer
		mine = fsize #the chunk left for self to download

		#get and store peer bandwidth, then update total bandwidth amount
		for peer in self.peers:
			peerBandwidth[peer.name] = peer.getNetBandwidth(fsize)
			aggregateBandwidth = aggregateBandwidth + peerBandwidth[peer.name]

		#based off of bandwidth and filesize, delegate chunks to each peer
		for peer in self.peers:
			chunkSize = round(peerBandwidth[peer.name] / aggregateBandwidth * fsize, 0)
			peerChunk[peer.name] = chunkSize
			mine = mine - chunkSize
		
		#recursive call to dividePacket for each peer, updating the range
		#offset upon each iteration.
		offset = start + mine
		for peer in self.peers:
			peer.dividePacket(offset, offset + peerChunk[peer.name])
			offset = offset + peerChunk[peer.name]

		#log for readability
		print("{} downloading packet segment {} - {} ({:.2f} {})".format(self.name,start,start + mine,*printSize(mine)))

if __name__ == '__main__':
	#file download size
	fileSize = 12 * GIGABYTE
	#define routers
	a = Router('a (2mbps)',2,54,[])
	b = Router('b (3mpbs)',3,54,[])
	c = Router('c (10mbps)',10,54,[])
	d = Router('d (6mbps)',6,54,[])
	e = Router('e (5mbps)',5,54,[])
	f = Router('f (7mbps)',7,54,[])

	#set peers
	a.peers = [b,e]
	b.peers = [c,d]
	e.peers = [f]

	a.dividePacket(0,fileSize)

