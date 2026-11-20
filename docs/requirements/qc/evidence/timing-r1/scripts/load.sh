#!/bin/bash
# N busy loops for S seconds
N=${1:-24}; S=${2:-900}
for i in $(seq $N); do timeout $S sh -c 'while :; do :; done' & done; wait
