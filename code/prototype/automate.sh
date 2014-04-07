#!/bin/bash
#serve has files of size {1,5,10,25,50,75,100,200,300,400,500,600,700,800,900}M and {1,2,4,5,10}G housed at /sizes/${size}.test

export SERVER_ROOT=http://10.18.234.114;
export SIZE_URL=${SERVER_ROOT}/sizes/;
export STUFF_URL=${SERVER_ROOT}/stuff/;

SESSION_WAIT='2700'; #45 minutes


#			  1kb  10kb  100kb   1mb     2mb     3mb     5mb      10mb    16mb     32mb
CHUNK_SIZES='1024 10240 102400 1048576 2097152 3145728 5242880 10485760 16777216 33554432';

MB_DOWNLOADS='50M 75M 100M 200M 300M 400M 500M 600M 700M 800M 900M';
GB_DOWNLOADS='1G 2G 4G 5G 10G';


echo "================= Starting Nightly Session ====================" >> log.txt;
for i in MB_DOWNLOADS
do
	echo "::::::::Beginning Test session for $i file" >> log.txt;
done

