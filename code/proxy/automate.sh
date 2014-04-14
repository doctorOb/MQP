#!/bin/bash
#serve has files of size {1,5,10,25,50,75,100,200,300,400,500,600,700,800,900}M and {1,2,4,5,10}G housed at /sizes/${size}.test

export SERVER_ROOT=http://10.18.234.114;
export SIZE_URL=${SERVER_ROOT}/sizes;
export STUFF_URL=${SERVER_ROOT}/stuff;

LOG_FILE="nightly.log";


ARG=$2;
CHUNK=$3;
DEV="eth1"

router() {
	CHUNK_SIZE=$ARG;
	python proxy-main.py -c $CHUNK_SIZE -i $DEV;
}

server() {
	#clear the current tc queues attached to eth1, reapply them with the new limit, for all possible router IPs.
	LIMIT=$ARG
	sudo tc qdisc del dev eth1 root;
	sudo tc qdisc add dev eth1 root handle 1: htb;
	sudo tc class add dev eth1 parent 1:1 classid 1:11 htb rate $LIMIT ceil $LIMIT;
	sudo tc class add dev eth1 parent 1:1 classid 1:12 htb rate $LIMIT ceil $LIMIT;
	sudo tc class add dev eth1 parent 1:1 classid 1:13 htb rate $LIMIT ceil $LIMIT;


	A_IP=10.18.175.187;
	B_IP=10.18.211.123;
	C_IP=10.18.228.100;
	sudo tc filter add dev eth1 protocol ip parent 1:0 prio 1 u32 match ip dst ${A_IP} flowid 1:11;
	sudo tc filter add dev eth1 protocol ip parent 1:0 prio 1 u32 match ip dst ${B_IP} flowid 1:12;
	sudo tc filter add dev eth1 protocol ip parent 1:0 prio 1 u32 match ip dst ${C_IP} flowid 1:13;

}

client() {
	SIZE=$ARG;
	echo "==================================\n" >> $LOG_FILE;
	echo "[INFO]{'fsize' : '$SIZE', 'chunk' : '$CHUNK'}" >> $LOG_FILE;
	(/usr/bin/time -ao $LOG_FILE -f "[TIME] %e\n" curl $SIZE_URL/$SIZE >/dev/null);
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



