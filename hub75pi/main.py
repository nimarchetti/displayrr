import zmq
import zlib
import struct
import serial
import sys

BOARDRR = "tcp://10.0.3.55:5600"
SERIAL  = "/dev/ttyAMA0"
BAUD    = 2_000_000
MODE    = b"uk_tdd"

print(f"hub75pi: opening {SERIAL} at {BAUD} baud")
ser = serial.Serial(SERIAL, BAUD, timeout=5)

ctx = zmq.Context()
sub = ctx.socket(zmq.SUB)
sub.connect(BOARDRR)
sub.setsockopt(zmq.SUBSCRIBE, MODE)
print(f"hub75pi: subscribed to {BOARDRR} mode={MODE.decode()}")

last_hash = None
sent = 0
while True:
    parts = sub.recv_multipart()
    if len(parts) != 4 or parts[0] != MODE:
        continue
    h = hash(parts[3])
    if h == last_hash:
        continue
    last_hash = h
    compressed = zlib.compress(parts[3], 1)
    ser.write(b'\xde\xad\xbe\xef' + struct.pack('>I', len(compressed)) + compressed)
    ser.flush()
    sent += 1
    if sent % 30 == 0:
        print(f"hub75pi: {sent} frames sent, last {len(compressed)}B compressed")
