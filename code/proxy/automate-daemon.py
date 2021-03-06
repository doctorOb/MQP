#!/usr/bin/env python

import socket
import sys
import os
from time import sleep
import subprocess
import psutil


IP = sys.argv[1]
PORT = 5000
BUFFER_SIZE = 1024

def killall(pid):
	parent = psutil.Process(pid)
	for child in parent.children(recursive=True):
		child.kill()
	parent.kill()

def handle_command(cmd,kill_pid=0):
	if kill_pid > 0:
		try:
			print "Killling existing proxy process"
			killall(kill_pid)
		except:
			pass #already finished
	sp = subprocess.Popen(['sh','automate.sh'] + cmd.split(" "))
	return sp.pid




if __name__ == '__main__':
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.bind((IP, PORT))
	s.listen(1)
	active_pid = 0 #pid of the current running task
	try:
		while 1:
			conn, addr = s.accept()
			print 'Connection from address: ', addr
			while 1:
				message = conn.recv(BUFFER_SIZE)
				if message:
					conn.send("Accept")
					conn.close()
					active_pid = handle_command(message,kill_pid=active_pid)
					print "PID of BA process is ",str(active_pid)
				break
			sleep(5)
	except:
		print "error with socket"
		s.close() #close the socket in case of an error



