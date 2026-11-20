import http.server, sys, time
LOG = sys.argv[2]
class H(http.server.BaseHTTPRequestHandler):
    def _h(self):
        with open(LOG, "a") as f: f.write(f"{time.strftime('%H:%M:%S')} {self.command} {self.path}\n")
        self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers()
    do_GET = do_HEAD = do_POST = do_PUT = _h
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
