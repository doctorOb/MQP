#!/usr/bin/env python

import socket
import sys
import os
from time import sleep

SERVER_IP="10.18.234.114"
ROUTERS=['10.18.175.187','10.18.211.123']

SERVER_ROOT="http://{}".format(SERVER_IP)

CHUNK_SIZES=[1024, 10240, 102400, 1048576, 2097152, 3145728, 5242880, 10485760, 16777216, 33554432]

MB_DOWNLOADS=[50, 75, 100, 200, 300, 400, 500, 600, 700, 800, 900] #add M.test
GB_DOWNLOADS=[1, 2, 4, 5, 10]; #add G.test



IP=sys.argv[1]
PORT=5000
BUFFER_SIZE=1024

def send_message(ip,message):
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.connect((ip,PORT))
	s.send(message)
	data = s.recv(BUFFER_SIZE)
	s.close()
	return data

if __name__ == '__main__':
	for rip in ROUTERS:
		print send_message(rip,"hello, world")
