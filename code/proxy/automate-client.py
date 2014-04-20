#!/usr/bin/env python

import socket
import sys
import os
from time import sleep, strftime
import subprocess

SERVER_IP="10.18.234.114"
ROUTERS=['10.18.175.187','10.18.211.123','10.18.228.100']

SERVER_ROOT="http://{}".format(SERVER_IP)

MEGABYTE = 102400

#			  1kb  10kb    100kb    1mb      2mb      3mb      5mb      10mb     16mb      32mb
CHUNK_SIZES=[1024, 10240, 102400, 1048576, 2097152, 3145728, 5242880, 10485760, 16777216, 33554432]
OPTIMAL_SIZES=[10240, 20480, 40960, 81920,102400,204800, 409600, 819200]

MB_DOWNLOADS=[50, 75, 100, 200, 300, 400, 500, 600, 700, 800, 900] #add M.test
GB_DOWNLOADS=[1, 2, 4, 5, 10]; #add G.test

N_DOWNLOADS=['100M','200M','300M','500M']
THROTTLES=['20mbit','25mbit']


PORT=5000
BUFFER_SIZE=1024
ISP_THROTTLE="20mbit"

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

def run_test(bandwidth=ISP_THROTTLE,routers=ROUTERS):
	send_message(SERVER_IP,"server {}".format(bandwidth))
	with open('nightly.log','a') as f:
		f.write("\n=========New Session: {}=========\n".format(bandwidth))

	for fsize in N_DOWNLOADS:
		for csize in OPTIMAL_SIZES:
			for rip in routers:
				send_message(rip, "router {}".format(csize))
			sleep(15) #wait for each machine to process the request. TODO: wait for confirmation
			handle_command("client {}.test {}".format(fsize,csize))
	date = strftime("%m_%d_%H:%M")
	log_name = "{}-{}:54mbit-x{}.log".format(date, bandwidth, len(routers))
	subprocess.call("mv nightly.log /var/log/nightlies/{}".format(log_name).split(" "))

if __name__ == '__main__':

	for bandwidth in THROTTLES:
		run_test(bandwidth=bandwidth)






