try:
	import psyco
	psyco.profile()
except ImportError:
	print "Please install Psyco for optimal performance."

import urllib, time

#url = 'http://www.google.com/intl/en_ALL/images/logo.gif'
#url = 'http://www.spp.ee.kth.se/res/tools/mms/MMSposter-large.jpg'
url = 'http://localhost/'
data0 = None
times = 0

t = time.time()
while True:
	try:
		while True:
			response = urllib.urlopen(url,proxies={'http':'http://localhost:8080'})
			data1 = response.read()
			if data0 == None:
				data0 = data1
			else:
				if data0 != data1:
					print 'FAIL'
			response.close()
			times += 1
	except (KeyboardInterrupt,IOError),ex:
		l = times
		s = time.time()-t
		if l > 0:
			print 'seconds per operation: %d'%(s/l)
		if s > 0:
			print 'operations per second: %d'%(l/s)
		exit()
	except Exception:
		print 'An unhandled exception occurred. Restarting!'
