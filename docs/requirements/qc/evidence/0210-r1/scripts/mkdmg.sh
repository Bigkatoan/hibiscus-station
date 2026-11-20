#!/bin/bash
# mkdmg.sh DATASETS_DIR SRC
cd $1; S=$2
mk(){ rm -rf $1 $1.hibiscus; cp -a $S $1; cp -a $S.hibiscus $1.hibiscus; }
mk dmgsc; T=dmgsc.hibiscus/telemetry; head -c 50 $T/episode_000000.jsonl.gz > x && mv x $T/episode_000000.jsonl.gz; echo garbage > $T/episode_000001.jsonl.gz; printf '' > $T/episode_000002.jsonl.gz; echo '[1,2' | gzip > $T/episode_000003.jsonl.gz; printf '1\n"str"\nnull\n[1]\n' | gzip > $T/episode_000004.jsonl.gz; echo '{"t": "x", "temp_c": "hot"}' | gzip > $T/episode_000005.jsonl.gz
mk dmgsj; echo '{bad' > dmgsj.hibiscus/dataset.json
mk dmgi1; printf '' > dmgi1/meta/info.json
mk dmgi2; echo '{"features": [1,2], "total_episodes": "x", "fps": "30"' > dmgi2/meta/info.json
mk dmgi3; echo '[]' > dmgi3/meta/info.json
mk dmgi4; python3 -c "
import json;p='dmgi4/meta/info.json';d=json.load(open(p));d['total_episodes']=-5;d['total_frames']=None;d['features']['action']=None;json.dump(d,open(p,'w'))"
mk dmgv; rm -rf dmgv/videos
mk dmgm; rm -rf dmgm/meta/episodes
mk dmgp; f=$(ls dmgp/meta/episodes/chunk-000/*.parquet|head -1); echo junk > $f
mk dmgd; rm -rf dmgd/data
mk dmgx; chmod 000 dmgx/meta/info.json
mk dmgt; rm -rf dmgt.hibiscus
