import deflate
import io
from machine import UART, Pin

_M0, _M1, _M2, _M3 = 0xde, 0xad, 0xbe, 0xef


class SerialClient:
    """Receive zlib-compressed RGB888 frames from Pi Zero over UART.

    Protocol: 4-byte magic (0xDEADBEEF) + 4-byte big-endian length + zlib frame.
    All intermediate buffers are pre-allocated — zero per-frame heap allocation
    (except the unavoidable ~200 B DeflateIO object) to prevent MicroPython GC pauses.
    """

    def __init__(self, baudrate=2_000_000):
        self._uart = UART(0, baudrate=baudrate, tx=Pin(16), rx=Pin(17), rxbuf=8192)
        self._bio  = io.BytesIO(bytearray(8192))  # reused decompress stream
        self._cmp  = bytearray(8000)              # reused compressed-data buffer
        self._mv   = memoryview(self._cmp)        # persistent memoryview into _cmp
        self._lbuf = bytearray(4)                 # length header buffer
        self._wbuf = bytearray(4)                 # sync sliding window
        self._obuf = bytearray(1)                 # single-byte read buffer
        print("serial_client: UART0 {}baud GP16(TX) GP17(RX)".format(baudrate))

    def _read_byte(self):
        ob = self._obuf
        while not self._uart.readinto(ob):
            pass
        return ob[0]

    def _read_into(self, mv, n):
        """Read exactly n bytes into pre-allocated memoryview slice."""
        pos = 0
        while pos < n:
            got = self._uart.readinto(mv[pos:n])
            if got:
                pos += got

    def _sync(self):
        """Slide a 4-byte window until the magic header is found."""
        w = self._wbuf
        for i in range(4):
            w[i] = self._read_byte()
        while w[0] != _M0 or w[1] != _M1 or w[2] != _M2 or w[3] != _M3:
            w[0] = w[1]; w[1] = w[2]; w[2] = w[3]; w[3] = self._read_byte()

    def fetch_into(self, pixels):
        """Block until a complete frame arrives, decompress into pixels."""
        self._sync()
        self._read_into(memoryview(self._lbuf), 4)
        lb = self._lbuf
        length = lb[0] << 24 | lb[1] << 16 | lb[2] << 8 | lb[3]
        if length > 8000:
            raise ValueError("bad length: {}".format(length))
        mv = self._mv
        self._read_into(mv, length)
        bio = self._bio
        bio.seek(0)
        bio.write(mv[:length])   # memoryview slice — no bytes copy allocation
        bio.seek(0)
        deflate.DeflateIO(bio, deflate.ZLIB).readinto(pixels)
