"""QC probe: run the INSTALLED hibiscus-station unchanged, logging (perf_counter) every loop tick
start (LoopStats.tick), every follower goal write (send_action), e-stop presses and estopped
entries. Nothing in the product is altered; the wrappers call the originals.
Usage: python shim.py <logfile> <hibiscus-station args...>"""
import os, sys, time, threading
log_path = sys.argv[1]
sys.argv = ["hibiscus-station"] + sys.argv[2:]
_f = open(log_path, "a", buffering=1)
_lk = threading.Lock()
def w(*a):
    with _lk:
        _f.write(" ".join(str(x) for x in a) + "\n")

from hibiscus_station.hw import loop as _loop, owner as _owner
_t = _loop.LoopStats.tick
def tick(self, start, duration, period):
    w("T", f"{start:.6f}", f"{duration:.6f}", f"{period:.6f}")
    return _t(self, start, duration, period)
_loop.LoopStats.tick = tick

from lerobot.robots.so_follower import SOFollower
_sa = SOFollower.send_action
def send_action(self, action):
    w("W", f"{time.perf_counter():.6f}")
    return _sa(self, action)
SOFollower.send_action = send_action

HO = _owner.HardwareOwner
_pe = HO.press_estop
def press_estop(self, reason="user", **kw):
    w("P", f"{time.perf_counter():.6f}", reason)
    return _pe(self, reason, **kw)
HO.press_estop = press_estop
_ee = HO._enter_estop
def _enter_estop(self):
    w("E", f"{time.perf_counter():.6f}", self.estop.reason)
    return _ee(self)
HO._enter_estop = _enter_estop
_hb = HO.heartbeat
def heartbeat(self):
    w("H", f"{time.perf_counter():.6f}")
    return _hb(self)
HO.heartbeat = heartbeat
_ss = HO._stop_session if hasattr(HO, "_stop_session") else None
w("START", f"{time.perf_counter():.6f}", os.getpid())
from hibiscus_station.cli import main
main()
