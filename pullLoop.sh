#!/bin/bash

while true
do
	git fetch origin master &> /dev/null;
	git reset --hard FETCH_HEAD &> /dev/null;
	git clean -df &> /dev/null;
	sleep 20;
done