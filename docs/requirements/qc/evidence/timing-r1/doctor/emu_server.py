"""QC fault server: two STS3215 chains on ptys with QC's own faults, counts every command."""
import json, os, signal, sys, time
from collections import Counter
sys.path.insert(0, sys.argv[1])  # tests/ of the clone (sts_emulator, stdlib only)
import sts_emulator  # noqa: E402
from sts_emulator import STSEmulator, lelab_calibration  # noqa: E402
import errno, types
class _OS(types.SimpleNamespace):
    pass
_os = _OS(**{k: getattr(os, k) for k in dir(os) if not k.startswith('__')})
def _read(fd, n):
    try:
        return os.read(fd, n)
    except OSError as e:
        if e.errno == errno.EIO:  # no one has the slave open (like a USB adapter with no program)
            time.sleep(0.002); return b""
        raise
_os.read = _read
sts_emulator.os = _os

cfg = json.loads(sys.argv[2]); out = sys.argv[3]

class QCEmu(STSEmulator):
    per_id_drop: dict = {}
    truncate_rate = 0.0
    brown_after = None  # (id, n transactions) -> that id goes silent
    garbage_rate = 0.0
    spike = None  # (probability, seconds): a late answer (USB / OS hiccup)
    base_latency = 0.0005
    spikes = 0
    late_once = None  # [id, instr, addr or -1, seconds]: exactly one late answer
    _late_now = 0.0
    def handle(self, pkt_id, instr, params):
        lo = self.late_once
        if lo and pkt_id == lo[0] and instr == lo[1] and (lo[2] < 0 or (params and params[0] == lo[2])):
            self._late_now = lo[3]; self.late_once = None; self.spikes += 1
        return super().handle(pkt_id, instr, params)
    @property
    def latency_s(self):
        if self._late_now:
            d, self._late_now = self._late_now, 0.0
            return self.base_latency + d
        if self.spike and self.rng.random() < self.spike[0]:
            self.spikes += 1
            return self.base_latency + self.spike[1]
        return self.base_latency
    @latency_s.setter
    def latency_s(self, v):
        self.base_latency = v
    def _respond(self, s, params=b""):
        if s is not None and self.brown_after and s.id == self.brown_after[0] and self.transactions > self.brown_after[1]:
            return b""
        if s is not None and not s.dead and self.per_id_drop.get(s.id) and self.rng.random() < self.per_id_drop[s.id]:
            return b""
        r = super()._respond(s, params)
        if r and self.truncate_rate and self.rng.random() < self.truncate_rate:
            r = r[: max(3, len(r) - 2)]
        if r and self.garbage_rate and self.rng.random() < self.garbage_rate:
            r = bytes([0x00, 0xFF, 0x13]) + r
        return r

def make(c, seed):
    e = QCEmu(seed=c.get("seed", seed))
    e.drop_rate = c.get("drop", 0.0); e.corrupt_rate = c.get("corrupt", 0.0)
    e.latency_s = c.get("latency", 0.0005)
    e.per_id_drop = {int(k): v for k, v in c.get("per_id_drop", {}).items()}
    e.spike = tuple(c["spike"]) if c.get("spike") else None
    e.late_once = c.get("late_once")
    e.truncate_rate = c.get("truncate", 0.0); e.garbage_rate = c.get("garbage", 0.0)
    e.brown_after = tuple(c["brown_after"]) if c.get("brown_after") else None
    for i in c.get("dead", []):
        e.servos[i].dead = True
    os.close(e.slave); e.slave = os.open(os.devnull, os.O_RDONLY)  # close the slave side like a real adapter
    if c.get("lelab"):
        e.preload_calibration(lelab_calibration())
    return e

# appended QC r9 faults: pipelined adapter delay, split packets, byte flips anywhere, echo
import threading, heapq
_real_write = os.write
_PIPES = {}  # master fd -> QCEmu
class _Pipe:
    def __init__(self, fd):
        self.fd = fd; self.q = []; self.cv = threading.Condition(); self.last = 0.0; self.n = 0
        threading.Thread(target=self.run, daemon=True).start()
    def put(self, t, data):
        with self.cv:
            t = max(t, self.last); self.last = t; self.n += 1
            heapq.heappush(self.q, (t, self.n, data)); self.cv.notify()
    def run(self):
        while True:
            with self.cv:
                while not self.q: self.cv.wait()
                t, _, data = self.q[0]; now = time.monotonic()
                if t > now:
                    self.cv.wait(t - now); continue
                heapq.heappop(self.q)
            try: _real_write(self.fd, data)
            except OSError: return
def _write(fd, data):
    e = _PIPES.get(fd)
    if e is None:
        return _real_write(fd, data)
    now = time.monotonic(); t = now + e.pipe_delay
    if e.split and data and e.rng.random() < e.split[0] and len(data) > 3:
        k = e.rng.randrange(1, len(data))
        e.pipe.put(t, bytes(data[:k])); e.pipe.put(t + e.split[1], bytes(data[k:]))
    else:
        e.pipe.put(t, bytes(data))
    return len(data)
_os.write = _write
_orig_handle = QCEmu.handle
_orig_respond = QCEmu._respond
def _handle(self, pkt_id, instr, params):
    if self.echo:
        body = bytes([pkt_id, len(params) + 2, instr]) + bytes(params)
        _os.write(self.master, b"\xff\xff" + body + bytes([(~sum(body)) & 0xFF]))
    return _orig_handle(self, pkt_id, instr, params)
def _respond(self, s, params=b""):
    r = _orig_respond(self, s, params)
    io = self.idflip_once
    if r and io and s is not None and s.id == io[0] and len(r) - 6 == io[2]:
        b = bytearray(r); b[2] = io[1]; r = bytes(b); self.idflip_once = None; self.spikes += 1
    if r and self.flip and self.rng.random() < self.flip:
        b = bytearray(r); i = self.rng.randrange(len(b)); b[i] ^= (1 << self.rng.randrange(8)); r = bytes(b)
    return r
QCEmu.handle = _handle; QCEmu._respond = _respond
QCEmu.idflip_once = None; QCEmu.echo = False; QCEmu.flip = 0.0; QCEmu.split = None; QCEmu.pipe_delay = 0.0
_orig_make = make
def make(c, seed):
    e = _orig_make(c, seed)
    e.echo = bool(c.get("echo")); e.idflip_once = c.get("idflip_once"); e.flip = c.get("flip", 0.0)
    e.split = tuple(c["split"]) if c.get("split") else None; e.pipe_delay = c.get("pipe", 0.0)
    if e.echo or e.split or e.pipe_delay:
        e.pipe = _Pipe(e.master); _PIPES[e.master] = e
    return e


# appended QC r10 faults: bus noise frames, jittered latency, servo that powers up late, a foreign id,
# a window where every answer is lost (cable wiggle)
_r9_handle = QCEmu.handle
_r9_respond = QCEmu._respond
def _h10(self, pkt_id, instr, params):
    r = _r9_handle(self, pkt_id, instr, params)
    if self.noise and self.rng.random() < self.noise:
        n = self.rng.randrange(2, 9); nid = self.rng.choice(self.noise_ids) if self.noise_ids else self.rng.randrange(0, 254)
        body = bytes([nid, n]) + bytes(self.rng.randrange(256) for _ in range(n - 1))
        r = (r or b"") + b"\xff\xff" + body + bytes([(checksum10(body) ^ 0x33) & 0xFF])
        self.spikes += 1
    return r
def checksum10(b): return (~sum(b)) & 0xFF
def _r10(self, s, params=b""):
    if s is not None and self.brown_in and s.id == self.brown_in[0] and self.transactions <= self.brown_in[1]:
        return b""
    if self.win and self.win[0] <= self.transactions <= self.win[1]:
        return b""
    out = _r9_respond(self, s, params)
    if out and s is not None:
        self.sent_by_id[s.id] = self.sent_by_id.get(s.id, 0) + 1
    return out
QCEmu.handle = _h10; QCEmu._respond = _r10
QCEmu.noise = 0.0; QCEmu.noise_ids = None; QCEmu.brown_in = None; QCEmu.win = None; QCEmu.jitter = None
_lat_prop = QCEmu.latency_s
def _lat_get(self):
    v = _lat_prop.fget(self)
    if self.jitter:
        v += self.jit_rng.uniform(*self.jitter)
    return v
QCEmu.latency_s = property(_lat_get, _lat_prop.fset)
_r9_make = make
def make(c, seed):
    e = _r9_make(c, seed)
    import random as _rd
    e.noise = c.get("noise", 0.0); e.noise_ids = c.get("noise_ids"); e.brown_in = tuple(c["brown_in"]) if c.get("brown_in") else None
    e.win = tuple(c["win"]) if c.get("win") else None; e.jitter = tuple(c["jitter"]) if c.get("jitter") else None
    e.sent_by_id = {}
    e.jit_rng = _rd.Random(c.get("seed", seed) + 77)
    for i in c.get("extra", []):
        e.servos[i] = sts_emulator.Servo(i)
    return e

_r10_make = make
def make(c, seed):
    e = _r10_make(c, seed)
    if c.get("realistic"):
        e.realistic()
    if c.get("adapter_delay"):
        e.adapter_delay_s = c["adapter_delay"]
    if c.get("voltage"):
        for sv in e.servos.values(): sv.voltage_v = c["voltage"]
    return e
f = make(cfg.get("follower", {}), 1); l = make(cfg.get("leader", {}), 2)
with open(out + ".ports", "w") as fh:
    json.dump({"follower": f.port, "leader": l.port}, fh)
def stop(*_):
    res = {arm: dict(Counter(x[0] for x in e.log), spikes=e.spikes, sent_by_id=e.sent_by_id) for arm, e in (("follower", f), ("leader", l))}
    with open(out + ".counts", "w") as fh:
        json.dump(res, fh)
    f.close(); l.close(); sys.exit(0)
def snap(*_):
    res = {arm: dict(Counter(x[0] for x in e.log)) for arm, e in (("follower", f), ("leader", l))}
    with open(out + ".snap", "a") as fh:
        fh.write(json.dumps(res) + "\n")
signal.signal(signal.SIGUSR1, snap)
signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
while True:
    time.sleep(1)
