"""
 * htfilter v.2.dev
 *  Author: Jiang Yio
 *          <http://www.inportb.com/>
 *    Date: August 22, 2008
 * License: Creative Commons Attribution-Share Alike 3.0 License
 *          <http://creativecommons.org/licenses/by-sa/3.0/>
"""

import re, shutil, os, htmlentitydefs, urllib2;
from urlparse import urlparse, urlunparse

def main():
	def unescape(text):
		# from http://effbot.org/zone/re-sub.htm#unescape-html
		def fixup(m):
			text = m.group(0)
			if text[:2] == "&#":
				# character reference
				try:
					if text[:3] == "&#x":
						return unichr(int(text[3:-1], 16))
					else:
						return unichr(int(text[2:-1]))
				except ValueError:
					pass
			else:
				# named entity
				try:
					text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
				except KeyError:
					pass
			return text # leave as is
		return re.sub("&#?\w+;", fixup, text)
	def fixFileName(fn):
		return re.sub(r'[\/\\\?\%\*\:\|\"\<\>]','.',fn)
	idmaptitle = {}
	mp4mapid = {}
	regex_youtube = re.compile('\w*\.?youtube\.com$')
	regex_title = re.compile('.*\<title\>YouTube \- ([^\<]*)\<\/title\>',re.DOTALL)
	class Hook:
		def __init__(self,config,events):
			self.events = events
			self.events['txhead'] += self.txHead
			self.videoid = None
		def txHead(self,config,request):
			url = request['preamble']['url']
			if regex_youtube.match(url.hostname) != None:
				# map video titles
				if (url.path == '/watch') and ('v' in request['query']):
					if not request['query']['v'][0] in idmaptitle:
						self.videoid = request['query']['v'][0]
						self.events['rxbody'] += self.rxBody
						if config['buffer'] < 1:
							config['buffer'] = 1
					return
				# rewrite videos to MP4
				if (url.path == '/get_video') and ('video_id' in request['query']):
					if request['query'].get('fmt',[0])[0] != 18:
						self.videoid = request['query']['video_id'][0]
						t = list(url)
						t[4] += '&fmt=18'
						request['preamble']['url'] = urlparse(urlunparse(t))
						self.events['rxhead'] += self.rxHead
						print 'YouTube %s: redirecting FLV to MP4.'%self.videoid
					return
			# detect MP4 re.compile('\/videoplayback\?id\=.*\&itag\=\d+\&begin\=0\&.*\&sver\=\d+')
			if (url.path == '/videoplayback') and ('id' in request['query']) and (urlunparse(url) in mp4mapid):
				self.videoid = mp4mapid[urlunparse(url)]
				print 'YouTube %s: enabling MP4 response buffer.'%self.videoid
				self.events['rxbody'] += self.rxBody
				if config['buffer'] < 1:
					config['buffer'] = 1
		def rxHead(self,config,request,response):
			code = response['preamble']['code']
			if self.videoid and (code >= 300) and (code < 400) and ('location' in response['headers']):
				mp4mapid[response['headers']['location']] = self.videoid
				print 'YouTube %s: mapped to MP4 stream.'%(self.videoid);
		def rxBody(self,config,request,response):
			if self.videoid:
				url = request['preamble']['url']
				if url.path == '/watch':
					response['body'].seek(0)
					m = regex_title.match(response['body'].read());
					if m != None:
						idmaptitle[self.videoid] = unescape(m.group(1).strip());
						print 'YouTube %s: mapped to title %s.'%(self.videoid,idmaptitle[self.videoid]);
				else:
					if not self.videoid in idmaptitle:
						opener = urllib2.build_opener(urllib2.ProxyHandler({}))	# no proxy
						sock = opener.open('http://www.youtube.com/watch?v=%s'%self.videoid)
						src = sock.read()
						sock.close()
						m = self.regex_title.match(src)
						if m != None:
							idmaptitle[self.videoid] = unescape(m.group(1).strip());
							print 'YouTube %s: mapped to title %s.'%(self.videoid,idmaptitle[self.videoid]);
					try:
						dst = config['cache']['youtube']
					except:
						dst = 'cache'
					if not os.path.isdir(dst):
						print '*** %s is not a directory'%dst
						return
					dst += os.sep+fixFileName(idmaptitle[self.videoid]+' - '+self.videoid+' - YouTube')+'.mp4'
					f = open(dst,'w+')
					response['body'].seek(0)
					chunk = int(config['chunk'])
					while True:
						data = response['body'].read(chunk)
						if data == '':
							break
						f.write(data)
					f.close()
					print 'YouTube %s: wrote %d bytes to %s'%(self.videoid,response['body'].tell(),dst);
		def destruct(self):
			pass
	def HookFactory(config,events,request):
		# return None if ignoring
		return Hook(config,events)
	return HookFactory
