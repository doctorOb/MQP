#!/usr/bin/env python
# -*- coding: utf-8 -*-
 
"""
Microproxy
This code is based on code based on microproxy.py written by ubershmekel in 2006.
 
Microproxy is the simplest possible http proxy. It simply relays all bytes from the client to the server at a socket send and recv level. The way it recognises the remote server to connect to is by a simple regex, which extracts the URL of the origin server from the byte stream. (This probably doesn't work in all cases).
 
"""
 
import re, time, sys
import socket
import threading
 
 
PORT = 8080
regex = re.compile(r'http://(.*?)/', re.IGNORECASE)
 
class ConnectionThread(threading.Thread):
	def __init__(self, (conn,addr)):
		self.conn = conn
		self.addr = addr
		threading.Thread.__init__(self)
   
	def run(self):
 
		data = self.conn.recv(1024*1024)
		host = regex.search(data).groups()[0]
	   
		request = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		#request.settimeout(6)
		request.connect((host,80))
		request.send(data)
 
		reply = ''
 
		while 1:
			temp = request.recv(1024)
 
			if ('' == temp):
				break
			   
			self.conn.send(temp)
		self.conn.close()
 
class ProxyThread(threading.Thread):
	def __init__(self, port):
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.sock.bind(('localhost', port))
		threading.Thread.__init__(self)
   
	def run(self):
		self.sock.listen(10)
		while 1:
			temp = ConnectionThread(self.sock.accept())
			temp.daemon = True
			temp.start()
 
if __name__ == "__main__":
	proxy = ProxyThread(PORT)
	proxy.daemon = True
	proxy.start()
	print "Started a proxy on port", PORT