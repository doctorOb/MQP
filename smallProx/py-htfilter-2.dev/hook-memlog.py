"""
 * htfilter v.2.dev
 *  Author: Jiang Yio
 *          <http://www.inportb.com/>
 *    Date: August 22, 2008
 * License: Creative Commons Attribution-Share Alike 3.0 License
 *          <http://creativecommons.org/licenses/by-sa/3.0/>
"""

def main():
	class Hook:
		def __init__(self,config,events):
			print '__init__'
			self.events = events
			self.events['txhead'] += self.toTerminal
			self.events['txbody'] += self.toTerminal
			self.events['rxhead'] += self.toTerminal
			self.events['rxbody'] += self.toTerminal
		def toTerminal(self,*args,**kargs):
			print args,kargs
		def destruct(self):
			print 'destruct'
			try:
				self.events['txhead'] -= self.toTerminal
				self.events['txbody'] -= self.toTerminal
				self.events['rxhead'] -= self.toTerminal
				self.events['rxbody'] -= self.toTerminal
			except:
				pass
	def HookFactory(config,events,request):
		# return None if ignoring
		return Hook(config,events)
	return HookFactory
