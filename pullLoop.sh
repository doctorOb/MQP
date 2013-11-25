#!/bin/bash

while true
do
	git fetch origin master;
	git reset --hard FETCH_HEAD;
	git clean -df;
	sleep 20;
done