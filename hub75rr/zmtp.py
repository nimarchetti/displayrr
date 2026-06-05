import socket

_GREETING = (
    b'\xff' + b'\x00' * 8 + b'\x7f'
    + b'\x03\x01'
    + b'NULL' + b'\x00' * 16
    + b'\x00'
    + b'\x00' * 31
)

_READY_BODY = (
    b'\x05READY'
    + b'\x0bSocket-Type'
    + b'\x00\x00\x00\x03SUB'
)


class ZMTPSub:
    def __init__(self, host, port):
        self._sock = socket.socket()
        self._sock.connect((host, port))
        self._handshake()

    def _recv_exact(self, n):
        buf = bytearray(n)
        view = memoryview(buf)
        pos = 0
        while pos < n:
            chunk = self._sock.recv(n - pos)
            if not chunk:
                raise OSError("connection closed")
            view[pos:pos + len(chunk)] = chunk
            pos += len(chunk)
        return bytes(buf)

    def _send_frame(self, data, command=False, more=False):
        flags = 0
        if more:
            flags |= 0x01
        if command:
            flags |= 0x04
        if len(data) > 255:
            flags |= 0x02
            header = bytes([flags]) + len(data).to_bytes(8, 'big')
        else:
            header = bytes([flags, len(data)])
        self._sock.sendall(header + data)

    def _recv_frame(self):
        flags = self._recv_exact(1)[0]
        if flags & 0x02:
            length = int.from_bytes(self._recv_exact(8), 'big')
        else:
            length = self._recv_exact(1)[0]
        data = self._recv_exact(length)
        return data, bool(flags & 0x01), bool(flags & 0x04)

    def _handshake(self):
        self._sock.sendall(_GREETING)
        self._recv_exact(64)
        self._send_frame(_READY_BODY, command=True)
        self._recv_frame()
        self._send_frame(b'\x01', command=False)

    def recv_multipart(self):
        parts = []
        while True:
            data, more, is_cmd = self._recv_frame()
            if is_cmd:
                continue
            parts.append(data)
            if not more:
                return parts

    def close(self):
        self._sock.close()
