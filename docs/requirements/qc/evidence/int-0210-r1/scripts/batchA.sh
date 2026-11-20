#!/bin/bash
I=/tmp/claude-1000/-home-bigkatoan-lelab/a1dcb981-a281-4451-90bf-5197e9a286c9/scratchpad/qc-int; W=$I/w; cd $W
export QCPORT=18611 QCHOME=$I/hA; PY="$I/qcvenv/bin/python"
echo "== counts"; $PY s_counts.py
echo "== stress"; $PY s_stress.py
echo "== ctrl"; $PY s_ctrl.py
echo "== resume"; $PY s_resume.py
echo "== q6"; $PY -c "
import qc,hammer,time
qc.setup()
for m in ('new','append','append'):
    s,b=hammer.record('q6',2,ep=1.0,mode=m); assert s==200,(s,b); qc.wait_idle(); time.sleep(1)
d=qc.ok('GET','/datasets/q6'); print('q6',d['episodes'],d['frames'],d['finalized'])"
find $QCHOME/datasets/q6 -type f | sed "s#$QCHOME/datasets/##" | sort
echo "== crash"; $PY s_crash.py crasha 3 episode; ./st.sh start $QCHOME 18611; $PY s_crash.py crashb 12 episode; ./st.sh start $QCHOME 18611
(cd $QCHOME/datasets && find crasha crashb crasha.hibiscus crashb.hibiscus -type f -print0 | sort -z | xargs -0 sha256sum) > $I/ev/crash_before.sha
$PY s_r2dmg.py crasha crashb
(cd $QCHOME/datasets && find crasha crashb crasha.hibiscus crashb.hibiscus -type f -print0 | sort -z | xargs -0 sha256sum) > $I/ev/crash_after.sha
diff -q $I/ev/crash_before.sha $I/ev/crash_after.sha && echo CRASH-FILES-IDENTICAL $(wc -l < $I/ev/crash_after.sha) files
$PY -c "
import qc
for n in ('crasha','crashb'):
    s,d=qc.call('GET','/datasets/'+n); print(n, s, d['episodes'], d['finalized'], ''.join(e['state'][0] for e in d['episode_list']), d.get('finalize_reasons'))
    for e in (0,):
        print('  tel', qc.call('GET', f'/datasets/{n}/episodes/{e}/telemetry')[0], 'videos', qc.call('GET', f'/datasets/{n}/episodes/{e}/videos'))
"
echo "== qh9"; $PY mk_qh9.py q6 && $PY s_qh9.py te0 te1 te3 te8 tfm1 tfp1 gap nodata novideo ok
./mkdmg.sh $QCHOME/datasets cnt3
echo "tracebacks $(grep -c Traceback $QCHOME/station.log)"
echo BATCH-A-DONE
