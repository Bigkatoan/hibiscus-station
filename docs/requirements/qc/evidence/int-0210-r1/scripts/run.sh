#!/bin/bash
I=/tmp/claude-1000/-home-bigkatoan-lelab/a1dcb981-a281-4451-90bf-5197e9a286c9/scratchpad/qc-int; S=$I/..; cd $I/cmp
P="env -u PYTHONPATH -u AMENT_PREFIX_PATH $I/qcvenv/bin/python"
start(){ HIBISCUS_STATION_TOKEN=<QC_TOKEN> HF_HOME=$2/hf HF_ENDPOINT=http://127.0.0.1:18699 setsid env -u PYTHONPATH -u AMENT_PREFIX_PATH $1 --mock --no-browser --home $2 --port $3 > $2.log 2>&1 < /dev/null & sleep 12; }
for round in 1 2; do
  start $S/qc-0210/bin0210/hibiscus-station $I/cmp/h0210_$round 18651; $P hb_cmp.py 18651 5 2>&1 | tail -7; pkill -INT -f -- "--home $I/cmp/h0210_$round"
  start $I/bin/hibiscus-station $I/cmp/hint_$round 18652; $P hb_cmp.py 18652 5 2>&1 | tail -7; pkill -INT -f -- "--home $I/cmp/hint_$round"
  sleep 3
done
echo CMP-DONE
