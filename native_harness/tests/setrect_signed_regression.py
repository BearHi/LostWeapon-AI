"""SetRect shim must preserve negative Win32 LONG coordinates."""
import struct

raw = struct.pack("<Iiiii", 0x12345678, -40, -12, 80, 96)
rectangle, left, top, right, bottom = struct.unpack("<Iiiii", raw)
assert rectangle == 0x12345678
assert (left, top, right, bottom) == (-40, -12, 80, 96)
assert struct.unpack("<iiii", struct.pack("<iiii", left, top, right, bottom)) == (-40, -12, 80, 96)
print("PASS")
