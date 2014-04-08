#!/usr/bin/env python

import socket
import sys
import os
from time import sleep
import subprocess



IP = sys.argv[1]
PORT = 5000
BUFFER_SIZE = 1024

def parse_command(message):
	return message

def handle_command(cmd):
	out = subprocess.check_output(['sh','worker.sh',cmd])
	print out


if __name__ == '__main__':

	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.bind((IP, PORT))
	s.listen(1)
	while 1:
		conn, addr = s.accept()
		print 'Connection from address: ', addr
		while 1:
			message = conn.recv(BUFFER_SIZE)
			if message:
				args = parse_command(message)
				conn.send("Accept")
				conn.close()
				handle_command(args)
			break
		sleep(5)



