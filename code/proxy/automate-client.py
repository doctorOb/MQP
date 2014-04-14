#!/usr/bin/env python

import socket
import sys
import os
from time import sleep
import subprocess

SERVER_IP="10.18.234.114"
ROUTERS=['10.18.175.187','10.18.211.123','10.18.228.100']

SERVER_ROOT="http://{}".format(SERVER_IP)

MEGABYTE = 102400

#			  1kb  10kb    100kb    1mb      2mb      3mb      5mb      10mb     16mb      32mb
CHUNK_SIZES=[1024, 10240, 102400, 1048576, 2097152, 3145728, 5242880, 10485760, 16777216, 33554432]

MB_DOWNLOADS=[50, 75, 100, 200, 300, 400, 500, 600, 700, 800, 900] #add M.test
GB_DOWNLOADS=[1, 2, 4, 5, 10]; #add G.test

N_DOWNLOADS=['200M','300M','500M','700M','900M','1GB','2GB','4GB']


PORT=5000
BUFFER_SIZE=1024
ISP_THROTTLE="10mbit"

def send_message(ip,message):
	try:
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.connect((ip,PORT))
		s.send(message)
		data = s.recv(BUFFER_SIZE)
		s.close()
		return data
	except:
		#connection refused
		return ""

def handle_command(cmd):
	out = subprocess.check_output(['sh','automate.sh'] + cmd.split(" "))

if __name__ == '__main__':
	for speed in ['10mbit']:
		send_message(SERVER_IP,"server {}".format(speed))
		for fsize in N_DOWNLOADS:
			for csize in CHUNK_SIZES[2:]:
				for rip in ROUTERS:
					send_message(rip, "router {}".format(csize))
				sleep(15) #wait for each machine to process the request. TODO: wait for confirmation
				handle_command("client {}.test {}".format(fsize,csize))




