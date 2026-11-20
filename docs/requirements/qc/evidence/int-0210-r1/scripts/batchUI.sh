#!/bin/bash
I=/tmp/claude-1000/-home-bigkatoan-lelab/a1dcb981-a281-4451-90bf-5197e9a286c9/scratchpad/qc-int; W=$I/w; cd $W/pw
export QCPORT=18611
for s in "ui_static.py" "ui_live.py en 1280 light live12 12" "ui_live.py vi 390 dark live4 4" "ui_flow.py en 1280 light" "ui_flow.py vi 390 dark" "ui_robot.py connected" "ui_sweep8.py"; do
  n=$(echo $s | tr ' ' '_'); echo "=== $s"; ./run.sh $s > $I/ev/ui_$n.out 2>&1; tail -c 1500 $I/ev/ui_$n.out; echo
done
echo UI-DONE
