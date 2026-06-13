import os
import zlib
import json
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import zmq

SOURCE = os.environ.get("SOURCE_ADDR", "tcp://boardrr:5600")
PORT   = int(os.environ.get("PORT", "5700"))

_lock       = threading.Lock()
_frame      = zlib.compress(b"\x00" * (256 * 64 * 3), 1)  # blank frame, zlib format
_meta       = {"mode": "", "raw_bytes": 0, "compressed_bytes": len(_frame)}


def _zmq_loop():
    global _frame, _meta
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(SOURCE)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    print(f"relayrr: subscribed to {SOURCE}", flush=True)
    last_hash = None
    while True:
        parts = sub.recv_multipart()
        if len(parts) != 4:
            continue
        h = hash(parts[3])
        if h == last_hash:
            continue
        last_hash = h
        compressed = zlib.compress(parts[3], 1)  # zlib format (header + checksum)
        with _lock:
            _frame = compressed
            _meta  = {
                "mode":             parts[0].decode(),
                "raw_bytes":        len(parts[3]),
                "compressed_bytes": len(compressed),
            }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == "/frame":
            with _lock:
                data = _frame
            self._respond(200, "application/octet-stream", data)
        elif self.path == "/status":
            with _lock:
                body = json.dumps(_meta).encode()
            self._respond(200, "application/json", body)
        else:
            self._respond(404, "text/plain", b"not found")

    def _respond(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


threading.Thread(target=_zmq_loop, daemon=True).start()
print(f"relayrr: HTTP :{PORT}  source={SOURCE}", flush=True)
ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
