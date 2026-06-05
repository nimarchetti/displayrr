import socket
import deflate
import io


class FrameClient:
    _REQUEST = (
        b"GET /frame HTTP/1.1\r\n"
        b"Host: relayrr\r\n"
        b"Connection: keep-alive\r\n"
        b"\r\n"
    )

    def __init__(self, host, port, max_compressed=8192):
        self._addr    = (host, port)
        self._sock    = None
        # Pre-allocated buffers — never replaced, only written into
        self._hdr     = bytearray(512)
        self._cmp     = bytearray(max_compressed)
        # BytesIO pre-allocated to max_compressed so write() never reallocates
        self._bio     = io.BytesIO(bytearray(max_compressed))

    def _connect(self):
        s = socket.socket()
        s.connect(self._addr)
        self._sock = s
        print("frame_client: connected to {}:{}".format(*self._addr))

    def _recv_into(self, mv, n):
        """Copy exactly n bytes into mv using recv(). Temporary bytes freed after each copy."""
        pos = 0
        while pos < n:
            chunk = self._sock.recv(min(n - pos, 4096))
            if not chunk:
                raise OSError("connection closed")
            got = len(chunk)
            mv[pos:pos + got] = chunk
            pos += got

    def _read_response(self):
        """Read HTTP response into pre-allocated _hdr and _cmp.
        Returns number of compressed bytes now in _cmp.
        """
        hdr_mv  = memoryview(self._hdr)
        hdr_pos = 0
        sep     = -1

        # Receive headers chunk by chunk until \r\n\r\n
        while sep < 0:
            chunk = self._sock.recv(256)
            if not chunk:
                raise OSError("connection closed")
            got = len(chunk)
            hdr_mv[hdr_pos:hdr_pos + got] = chunk
            search_from = max(0, hdr_pos - 3)
            hdr_pos += got
            for i in range(search_from, hdr_pos - 3):
                if (self._hdr[i]     == 13 and self._hdr[i + 1] == 10 and
                        self._hdr[i + 2] == 13 and self._hdr[i + 3] == 10):
                    sep = i
                    break

        body_start  = sep + 4
        body_in_hdr = hdr_pos - body_start

        # Parse Content-Length (small temporary bytes, freed immediately)
        cl = 0
        for line in bytes(self._hdr[:sep]).split(b"\r\n"):
            if line.startswith(b"Content-Length: "):
                cl = int(line[16:])
                break

        # Copy any body bytes already received with the headers
        cmp_mv = memoryview(self._cmp)
        if body_in_hdr > 0:
            cmp_mv[:body_in_hdr] = hdr_mv[body_start:body_start + body_in_hdr]

        # Receive the rest of the body directly into _cmp
        need = cl - body_in_hdr
        if need > 0:
            self._recv_into(cmp_mv[body_in_hdr:], need)

        return cl

    def fetch_into(self, pixels):
        """Fetch current frame and decompress directly into pre-allocated pixels buffer.
        Per-frame heap allocations: recv temporaries (~3 KB, immediately freed) +
        one small deflate.DeflateIO object (~100 B).
        """
        if self._sock is None:
            self._connect()
        try:
            self._sock.sendall(self._REQUEST)
            cl = self._read_response()

            # Reuse pre-allocated BytesIO — no new allocation
            self._bio.seek(0)
            self._bio.write(memoryview(self._cmp)[:cl])
            self._bio.seek(0)

            deflate.DeflateIO(self._bio, deflate.ZLIB).readinto(pixels)
        except OSError:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
            raise

    def close(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
