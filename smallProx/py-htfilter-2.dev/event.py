# from http://www.valuedlessons.com/2008/04/events-in-python.html
class Event:
	def __init__(self):
		self.handlers = set();
	def bind(self,handler):
		self.handlers.add(handler);
		return self;
	def unbind(self,handler):
		try:
			self.handlers.remove(handler);
		except:
			raise ValueError('Cannot unbind unbound handler.');
		return self;
	def fire(self,*args,**kargs):
		for handler in self.handlers:
			handler(*args,**kargs);
	def count(self):
		return len(self.handlers);
	__iadd__ = bind;
	__isub__ = unbind;
	__call__ = fire;
	__len__  = count;
