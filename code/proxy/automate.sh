#!/bin/bash
#serve has files of size {1,5,10,25,50,75,100,200,300,400,500,600,700,800,900}M and {1,2,4,5,10}G housed at /sizes/${size}.test

export SERVER_ROOT=http://10.18.234.114;
export SIZE_URL=${SERVER_ROOT}/sizes/;
export STUFF_URL=${SERVER_ROOT}/stuff/;

SESSION_WAIT='2700'; #45 minutes


function router() {
	CHUNK_SIZE=$1;
	THROTLE=$2; #not used by this script
	PROXY_PATH=../prototype;


	kill -9 `cat current_proc.pid` || true;
	python $PROXY_PATH/proxy-main.py -c $1 -f $PROXY_PATH/module.cfg;
	echo $! > current_proc.pid;
}




