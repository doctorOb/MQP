#!/bin/bash
#serve has files of size {1,5,10,25,50,75,100,200,300,400,500,600,700,800,900}M and {1,2,4,5,10}G housed at /sizes/${size}.test

export SERVER_ROOT=http://10.18.234.114;
export SIZE_URL=${SERVER_ROOT}/sizes;
export STUFF_URL=${SERVER_ROOT}/stuff;

LOG_FILE="nightly.log";


ARG=$2;

router() {
	#kill the proxy if it is currently running, then start again with the new chunk size
	CHUNK_SIZE=$ARG;

	#kill -9 `cat current_proc.pid` || true;
	python proxy-main.py "-c $CHUNK_SIZE";
	#echo $! > current_proc.pid;
}

server() {
	#clear the current tc queues attached to eth1, reapply them with the new limit, for all possible router IPs.
	LIMIT=$ARG
	sudo tc qdisc del dev eth1 root;
	sudo tc qdisc add dev eth1 root handle 1: htb;
	sudo tc class add dev eth1 parent 1:1 classid 1:11 htb rate $LIMIT ceil $LIMIT;
	sudo tc class add dev eth1 parent 1:1 classid 1:12 htb rate $LIMIT ceil $LIMIT;

	A_IP=10.18.175.187;
	B_IP=10.18.211.123;
	sudo tc filter add dev $DEV protocol ip parent 1:0 prio 1 u32 match ip dst ${A_IP} flowid 1:11;
	sudo tc filter add dev $DEV protocol ip parent 1:0 prio 1 u32 match ip dst ${B_IP} flowid 1:12;
}

client() {
	SIZE_URL=$ARG
	(time time curl $SIZE_URL/$SIZE >/dev/null 2>&1) &>> $LOG_FILE;
}



case "$1" in

	router)
		#do router stuff
		echo "doing router stuff";
		router
		;;
	server)
		#do server stuff
		server
		;;
	client)
		#do client stuff
		client
		;;
	*)
		#error
		echo "Improper command piped from coordinator"
		;;

esac
exit 0;



