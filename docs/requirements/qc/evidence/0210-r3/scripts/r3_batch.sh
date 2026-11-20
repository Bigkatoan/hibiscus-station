#!/bin/bash
Q=/tmp/claude-1000/-home-bigkatoan-lelab/a1dcb981-a281-4451-90bf-5197e9a286c9/scratchpad/qc-0210
cd $Q; export QCPORT=18501 QCHOME=$Q/h4; rm -rf h4
./st.sh start 0210 $QCHOME 18501
python3 s_counts.py && python3 s_stress.py && python3 s_ctrl.py && python3 s_resume.py
python3 s_crash.py crasha 3 episode; ./st.sh start 0210 $QCHOME 18501; python3 s_crash.py crashb 12 episode; ./st.sh start 0210 $QCHOME 18501
cd h4/datasets && find crasha crashb crasha.hibiscus crashb.hibiscus -type f -print0 | sort -z | xargs -0 sha256sum > $Q/r3_crash_before.sha; cd $Q
python3 s_r2dmg.py crasha crashb
cd h4/datasets && find crasha crashb crasha.hibiscus crashb.hibiscus -type f -print0 | sort -z | xargs -0 sha256sum > $Q/r3_crash_after.sha; cd $Q
diff -q r3_crash_before.sha r3_crash_after.sha && echo CRASH-FILES-IDENTICAL
python3 -c "
import qc
for n in ('crasha','crashb'):
    s,d=qc.call('GET','/datasets/'+n); print(n, s, d['episodes'], d['finalized'], ''.join(e['state'][0] for e in d['episode_list']))
"
./mkdmg.sh $QCHOME/datasets cnt3
cd pw
./run.sh ui_static.py > $Q/r3_ui_static.json 2>&1
./run.sh ui_live.py en 1280 light live12 12 > $Q/r3_ui_live_en.txt 2>&1
./run.sh ui_live.py vi 390 dark live4 4 > $Q/r3_ui_live_vi.txt 2>&1
./run.sh ui_flow.py en 1280 light > $Q/r3_ui_flow_en.json 2>&1
./run.sh ui_flow.py vi 390 dark > $Q/r3_ui_flow_vi.json 2>&1
./run.sh ui_sweep.py > $Q/r3_ui_sweep.json 2>&1
./run.sh ui_robot.py connected > $Q/r3_ui_robot.json 2>&1
cd $Q; echo "tracebacks $(grep -c Traceback h4/station.log) unhandled $(grep -c 'unhandled error' h4/station.log)"
echo BATCH-DONE
