"""
 * htfilter v.2.dev
 *  Author: Jiang Yio
 *          <http://www.inportb.com/>
 *    Date: August 22, 2008
 * License: Creative Commons Attribution-Share Alike 3.0 License
 *          <http://creativecommons.org/licenses/by-sa/3.0/>
"""

import re
from urlparse import urlparse

def main():
	regex_microsoft = re.compile('[a-zA-Z0-9\-\_]*\.?microsoft\.com$')
	regex_imageshack = re.compile('[a-zA-Z0-9\-\_]*\.?imageshack\.us$')
	regex_110mb = re.compile('[a-zA-Z0-9\-\_]*\.?110mb\.com$')
	list_images = ['.jpg','.png','.gif']
	class Hook:
		def __init__(self,config,events):
			self.events = events
			self.events['txhead'] += self.txHead
			self.events['rxhead'] += self.rxHead
		def txHead(self,config,request):
			url = request['preamble']['url']
			if regex_microsoft.match(url.hostname) != None:
				print request['preamble']['url']
				self.events['exception']('access denied: microsoft.com')
			elif url.path[-4:].lower() in list_images:
				request['preamble']['url'] = urlparse('http://img183.imageshack.us/img183/7614/pwnedmd7.jpg')
		def rxHead(self,config,request,response):
			if response['headers'].getheader('content-type','') == 'application/x-shockwave-flash':
				print request['preamble']['url']
				self.events['exception']('access denied: Flash content')
			else:
				config['buffer'] = 1
		def destruct(self):
			try:
				self.events['txhead'] -= self.txHead
			except:
				pass
	def HookFactory(config,events,request):
		if regex_imageshack.match(request['preamble']['url'].hostname) != None:
			print 'skipping checks: imageshack.us'
			return None
		if regex_110mb.match(request['preamble']['url'].hostname) != None:
			print 'skipping checks: 110mb.com'
			return None
		return Hook(config,events)
	return HookFactory
