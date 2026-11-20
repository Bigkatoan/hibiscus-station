#!/bin/bash
# usage: st.sh start|stop|kill VER HOME PORT
Q=/tmp/claude-1000/-home-bigkatoan-lelab/a1dcb981-a281-4451-90bf-5197e9a286c9/scratchpad/qc-0210
act=$1; ver=$2; home=$3; port=$4
case $act in
start)
  mkdir -p $home
  HIBISCUS_STATION_TOKEN=<QC_TOKEN> HF_HOME=$home/hf HF_ENDPOINT=http://127.0.0.1:18599 setsid env -u PYTHONPATH -u AMENT_PREFIX_PATH $Q/bin$ver/hibiscus-station $MOCKFLAG --no-browser --home $home --port $port >> $home/station.log 2>&1 < /dev/null &
  for i in $(seq 1 60); do curl -sf -H "Authorization: Bearer <QC_TOKEN>" http://127.0.0.1:$port/api/v1/status >/dev/null && { pgrep -f "tools$ver/hibiscus-station/bin/python.*--home $home --port $port" | head -1 > $home/pid; echo up $(cat $home/pid); exit 0; }; sleep 1; done; echo notup; exit 1;;
kill) pkill -9 -f -- "--home $home --port $port"; sleep 1; echo killed;;
stop) pkill -INT -f -- "--home $home --port $port"; for i in $(seq 1 60); do pgrep -f -- "--home $home --port $port" >/dev/null || { echo stopped; exit 0; }; sleep 1; done; echo still;;
esac
