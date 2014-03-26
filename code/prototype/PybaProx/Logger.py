import os
import sys
import inspect #for getting caller's name
import string
import time



class Logger(object):

	"""
	a utility class, acting as a singleton, which logs information from 
	different entities. By default, the caller and current hour/second are reported.

	The class is accessed semantically through either the info, warning, or logic 
	function.

	"""

	_instance = None

	#Ensure singleton behavior
	def __new__(cls, *args, **kwargs):
		if not cls._instance:
			cls._instance = super(Logger, cls).__new__(cls, *args, **kwargs)
		return cls._instance

	def __init__(self,options={}):
		self.options = {
			'silent': False,
			'out_file': "Log_info",
			'display_time': True,
			'display_caller': True
		}

		self._parse_options(options)

	def _parse_options(self,options):
		for key,val in options:
			if key in self.options:
				self.options[key] = val
			else:
				print "Logger: {} is not a valid configuration option".format(key)

	def _log(self,msg):
		if self.options['silent']:
			with open(self.options['out_file'],'a') as f:
				f.write(msg)
		else:
			print(msg)

	def _format(self,log_type,msg):
		date = ""
		stack = inspect.stack()
		caller_class = ""
		caller_method = ""


		if self.options['display_caller']:
			try:
				caller_method = "{}".format(stack[1][0].f_code.co_name)
				caller_class = stack[1][0].f_locals["self"].__class__
			except:
				pass
		if self.options['display_time']:
			date = time.strftime("%X")

		self._log("<{}>[{}.{}]@|{}|# {}".format(log_type,caller_class,caller_method,date,msg))

	def info(self,msg):
		self._format("info",msg)

	def logic(self,msg):
		self._format("logic",msg)

	def warning(self,msg):
		self._format("warning",msg)



