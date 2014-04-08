#!/usr/bin/env python

import socket
import sys
import os
from time import sleep
import subprocess



IP = sys.argv[1]
PORT = 5000
BUFFER_SIZE = 1024


def handle_command(cmd):
	out = subprocess.check_output(['sh','automate.sh'] + cmd.split(" "))
	print out


if __name__ == '__main__':

	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.bind((IP, PORT))
	s.listen(1)
	try:
		while 1:
			conn, addr = s.accept()
			print 'Connection from address: ', addr
			while 1:
				message = conn.recv(BUFFER_SIZE)
				if message:
					conn.send("Accept")
					conn.close()
					handle_command(message)
				break
			sleep(5)
	except:
		s.close() #close the socket in case of an error



