import http.server, threading, sys, struct, zlib, importlib.util, functools
sys.path.insert(0, sys.argv[1])
spec = importlib.util.spec_from_file_location("es", sys.argv[1] + "/e2e_support.py"); es = importlib.util.module_from_spec(spec); sys.modules["es"] = es; spec.loader.exec_module(es)
def chunk(k, b): return struct.pack(">I", len(b)) + k + b + struct.pack(">I", zlib.crc32(k + b))
good = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\0\0\0\0")) + chunk(b"IEND", b"")
bad_crc = bytearray(good); bad_crc[30] ^= 1
cases = {"good.png": (good, None), "trunc.png": (good[:-6], None), "badcrc.png": (bytes(bad_crc), None),
         "noiend.png": (good[:-12], None), "trailing.png": (good + b"xx", None), "notpng.png": (b"GIF89a" + good[6:], None),
         "shortlen.png": (good, len(good) + 5), "good.jpg": (good, None), "404.png": (None, None)}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        n = self.path.lstrip("/"); body, cl = cases.get(n, (None, None))
        if body is None: self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Length", str(cl or len(body))); self.end_headers()
        try: self.wfile.write(body)
        except Exception: pass
s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=s.serve_forever, daemon=True).start()
p = s.server_address[1]
for n in cases:
    try: print(n, es.served_png_is_whole(f"http://127.0.0.1:{p}/{n}"))
    except Exception as e: print(n, "RAISES", type(e).__name__)
print("non-local", es.served_png_is_whole("http://example.invalid/good.png"))
