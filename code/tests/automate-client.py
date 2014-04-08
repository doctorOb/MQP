#!/usr/bin/env python

import socket
import sys
import os
from time import sleep

SERVER_IP="10.18.234.114"
ROUTERS=['10.18.175.187','10.18.211.123']

SERVER_ROOT="http://{}".format(SERVER_IP)

MEGABYTE = 102400

#			  1kb  10kb    100kb    1mb      2mb      3mb      5mb      10mb     16mb      32mb
CHUNK_SIZES=[1024, 10240, 102400, 1048576, 2097152, 3145728, 5242880, 10485760, 16777216, 33554432]

MB_DOWNLOADS=[50, 75, 100, 200, 300, 400, 500, 600, 700, 800, 900] #add M.test
GB_DOWNLOADS=[1, 2, 4, 5, 10]; #add G.test


PORT=5000
BUFFER_SIZE=1024
ISP_THROTTLE="10mbit"

def send_message(ip,message):
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.connect((ip,PORT))
	s.send(message)
	data = s.recv(BUFFER_SIZE)
	s.close()
	return data

if __name__ == '__main__':
	for fsize in MB_DOWNLOADS:
		for csize in CHUNK_SIZES:
			for rip in ROUTERS:
				try:
					send_message(rip, "{} {}".format(csize,ISP_THROTTLE))
				except:
					pass #not running
			send_message(SERVER_IP,"{} {}".format(csize,ISP_THROTTLE))



