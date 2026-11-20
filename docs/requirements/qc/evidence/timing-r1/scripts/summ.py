import json, sys
from pathlib import Path
Q = Path("/tmp/claude-1000/-home-bigkatoan-lelab/a1dcb981-a281-4451-90bf-5197e9a286c9/scratchpad/qc-timing")
for run in sys.argv[1:]:
    R = json.loads((Q / "runs" / run / "results.json").read_text())
    tc, tw = R["teleop_clean_ticks"], R["teleop_clean_writes"]
    print(f"== {run}")
    print(f"  teleop clean 12 s: ticks {tc['n']} mean {tc['mean_hz']} Hz (ws {R['teleop_ws_rate_hz']}), median gap {tc['median_gap_ms']} ms, sd {tc['sd_gap_ms']}, p1 {tc['p1_gap_ms']} p99 {tc['p99_gap_ms']} max {tc['max_gap_ms']}, <0.5T {tc['gaps_lt_half_period']}, >1.5T {tc['gaps_gt_1.5_period']}")
    print(f"  teleop writes  : n {tw['n']} mean {tw['mean_hz']} Hz, min gap {tw['min_gap_ms']} p1 {tw['p1_gap_ms']}, <0.5T {tw['gaps_lt_half_period']}, <0.2T {tw['gaps_lt_0.2_period']}")
    for s in R["teleop_all_writes"]["stalls"]:
        print(f"    stall {s['stall_s']}s writes gaps around: {s['gaps_ms_around'][:5]} ; writes in 1T after resume {s['ticks_within_1_period_after_resume']}, in 3T {s['ticks_within_3_periods_after_resume']}")
    aw = R["teleop_all_writes"]
    print(f"  teleop whole run writes: <0.5T {aw['gaps_lt_half_period']}  <0.2T {aw['gaps_lt_0.2_period']} min {aw['min_gap_ms']} ms; rate excl stalls {aw['rate_hz_excl_stalls']}")
    for k in ("rec_clean", "rec_stall"):
        x = R[k]; t = x["ticks"]; w = x["writes"]
        print(f"  {k}: wall {x['wall_s']} s ticks {t['n']} mean {t['mean_hz']} Hz excl-stall {t['rate_hz_excl_stalls']} sd {t['sd_gap_ms']} p99 {t['p99_gap_ms']} max {t['max_gap_ms']}; writes <0.5T {w['gaps_lt_half_period']} min {w['min_gap_ms']}")
        for s in w["stalls"]:
            print(f"     stall {s['stall_s']} gaps {s['gaps_ms_around'][:5]}")
    print("  estop:", [(e["press_to_estopped_ms"], e["writes_after_press"], e["ticks_completed_between"]) for e in R["estop"]])
    print("  stop-rec:", [(s["answer_s"], s["phase_after"], s["idle_after_s"]) for s in R["stop_record"]])
    print("  deadman:", [(d["last_heartbeat_to_estop_s"], d["reason"], d["ticks_started_after_timeout_before_estop"]) for d in R["deadman"]], R.get("replay_states"))
