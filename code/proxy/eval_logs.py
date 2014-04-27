import math
import sys
import matplotlib.pyplot as plot
import numpy as np

INFO_DELIM = '[INFO]'
TIME_DELIM = '[TIME]'
TRIAL_DELIM = '==='

CHUNK_SIZES=[102400, 1048576, 2097152, 3145728, 5242880, 10485760, 16777216, 33554432]
FILE_SIZES=[50, 75, 100, 200, 300, 400, 500, 600, 700, 800, 900]


KB = 1024.0
MB = KB*1000.0
GB = MB*1000.0
def btoh(bytes):
	"""return a human readable form of bytes"""
	bytes = float(bytes)
	if bytes < 1000:
		return "{}b".format(round(bytes))
	elif (bytes / KB) < 1000:
		return "{}K".format(round(bytes/KB))
	elif (bytes / MB) < 1000:
		return "{}M".format(round(bytes/MB))
	else:
		return "{}G".format(round(bytes/GB))

class Measure():

	def __init__(self, initial):
		self.values = []

	def add(self,val):
		self.values.append(val)

	def average(self):
		avg = 0.0
		for val in self.values:
			avg+=val
		return avg / float(len(self.values))

	def min(self):
		return min(self.values)
	def max(self):
		return max(self.values)

#TODO: handle different input sizes better
def calculate_mbps(fsize,time):
	"""calculate the mbps of a download session for a file of fsize mb and time (in seconds)"""
	kbps = ((fsize * 1024) / time) * 8
	return float(kbps) * 0.0009765

def parse_log(fname):
	"""read in the log file, storing an array of dictionaries, each specifying {size: ,chunk: ,time: }"""
	with open(fname,'r') as f:
		trials = []
		for line in f.readlines():
			if TRIAL_DELIM in line:
				trials.append({})
			elif INFO_DELIM in line:
				stats = eval(line.split(INFO_DELIM)[-1])
				trials[-1]['size'] = int(stats['fsize'][0:-6])
				if 'G' in stats['fsize']:
					trials[-1]['size']*=1024
				trials[-1]['chunk'] = int(stats['chunk'])
			elif TIME_DELIM in line:
				trials[-1]['time'] = float(line.split(TIME_DELIM)[-1].strip('\n'))
		return trials

def group_by_chunk(stats):
	"""group a collection of stats (returned by parse_log) by the chunk size associated with each session"""
	dtimes = dict()
	for run in stats:
		bandwidth = calculate_mbps(run['size'],run['time'])
		if run['chunk'] not in dtimes:
			dtimes[run['chunk']] = Measure(bandwidth)
		else:
			dtimes[run['chunk']].add(bandwidth)
	return dtimes

def group_by_request_size(stats):
	"""group a collection of stats by file size"""
	sizes = dict()
	for run in stats:
		bandwidth = calculate_mbps(run['size'],run['time'])
		if run['size'] not in sizes:
			sizes[run['size']] = Measure(bandwidth)
		else:
			sizes[run['size']].add(bandwidth)
	return sizes

def graph_chunk_bandwidth(chunks):
	fig = plot.figure()
	ax = fig.add_subplot(111)
	N = len(chunks)
	indicies = np.arange(N)
	width = 0.5

	#the bars
	chunk_vals = [a.average() for x,a in s_gen(chunks)]
	rects1 = ax.bar(indicies,chunk_vals,width,color='purple')
	ax.set_xlim(-width,len(indicies)+width)
	ax.set_ylim(0,60)
	ax.set_ylabel('Bandwidth (mbps)')
	ax.set_xlabel('Chunk Size')
	ax.set_title('Average Realized Bandwidth, using 3 Routers, each with 20mbit throttled downlink.')
	ax.set_xticks(indicies+width)
	xTicks = ax.set_xticklabels([btoh(size) for size in sorted(chunks,key=chunks.get)])
	plot.setp(xTicks,rotation=45,fontsize=10)

	plot.show()

def graph_filesize_bandwidth(sizes):
	fig = plot.figure()
	ax = fig.add_subplot(111)
	N = len(sizes)
	indicies = np.arange(N)
	width = 0.5

	#the bars
	rects1 = ax.bar(indicies,sizes,width,color='red')
	ax.set_xlim(-width,len(indicies)+width)
	ax.set_ylim(0,50)
	ax.set_ylabel('Bandwidth (mbps)')
	ax.set_xlabel('File Size')
	ax.set_title('Average realized bandwidth using 3 Routers.')
	ax.set_xticks(indicies+width)
	xTicks = ax.set_xticklabels([btoh(size) for size in sorted(sizes,key=sizes.get)])
	plot.setp(xTicks,rotation=45,fontsize=10)

	plot.show()

def s_gen(stats):
	for key in sorted(stats,key=stats.get):
		yield key, stats[key]


if __name__ == '__main__':
	stats = parse_log(sys.argv[1])
	dtime_by_chunk = group_by_chunk(stats)
	dtime_by_size = group_by_request_size(stats)

	throttle = sys.argv[1].split('-')[1] #should read "ispMBPS:wifiMBPS"

	print "Calculating average mbps for session with throttle {}".format(throttle)
	print "====== Stats By Chunk Size ========"
	for chunk,measure in s_gen(dtime_by_chunk):
		print "{} : {}".format(chunk, measure.average())
	print "====== Stats By Request Size ======="
	for size,measure in s_gen(dtime_by_size):
		print "{} : {}".format(size,measure.average())

	graph_chunk_bandwidth(dtime_by_chunk)