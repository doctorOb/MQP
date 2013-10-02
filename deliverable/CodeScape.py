"""Idea: scrape source code and use line length and indentation to construct data points
	(line start and stop x), to trace out an image or something.

	Use line word and token count to determine properties such as color, width, angle"""

import string
import os
import sys
import re

class Line():

	def __init__(self,buff):
		self.buff = buff

		self.start = 

with open(sys.argv[1]) as fp:
	data = fp.readlines()
	for line in data:
		print line,


