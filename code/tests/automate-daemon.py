#!/usr/bin/env python

import socket
import sys
import os
from time import sleep


if __name__ == '__main__':
	IP = sys.argv[1]
	PORT = 5000
	BUFFER_SIZE = 1024

	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.bind((IP, PORT))
	s.listen(1)
	active_pid = None
	while 1:
		conn, addr = s.accept()
		print 'Connection from address: ', addr
		while 1:
			message = conn.recv(BUFFER_SIZE)
			if message:
				print "received message: ", message
				conn.send("Accept")
			break
		conn.close()
		sleep(5)



