#!/bin/bash
# usage: st.sh start BUILD HOME PORT [shim|plain]  |  st.sh stop HOME PORT
Q=/tmp/claude-1000/-home-bigkatoan-lelab/a1dcb981-a281-4451-90bf-5197e9a286c9/scratchpad/qc-timing
TOK=${QCTOK:-<QC_TOKEN>}
case $1 in
start)
  b=$2; home=$3; port=$4; mode=${5:-shim}; mkdir -p $home
  PY=$Q/tools-$b/hibiscus-station/bin/python
  if [ $mode = shim ]; then CMD=("$PY" "$Q/scripts/shim.py" "$home/probe.log"); else CMD=("$Q/bin-$b/hibiscus-station"); fi
  HIBISCUS_STATION_TOKEN=$TOK HF_HOME=$home/hf HF_ENDPOINT=http://127.0.0.1:9 setsid env -u PYTHONPATH -u AMENT_PREFIX_PATH "${CMD[@]}" --mock --no-browser --home $home --port $port >> $home/station.log 2>&1 < /dev/null &
  echo $! > $home/pid
  for i in $(seq 1 120); do curl -sf -H "Authorization: Bearer $TOK" http://127.0.0.1:$port/api/v1/status >/dev/null && { echo up $(cat $home/pid); exit 0; }; sleep 1; done; echo notup; exit 1;;
stop) home=$2; port=$3; pkill -INT -f -- "--home $home --port $port"; for i in $(seq 1 60); do pgrep -f -- "--home $home --port $port" >/dev/null || { echo stopped; exit 0; }; sleep 1; done; pkill -9 -f -- "--home $home --port $port"; echo killed;;
esac
