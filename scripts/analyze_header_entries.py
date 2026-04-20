"""Analyze 13-byte header entries and find sprite palette."""
import struct
import os
from PIL import Image

with open('m3_0', 'rb') as f:
    data = f.read()

os.makedirs('real_sprites_final', exist_ok=True)

file_size = len(data)

# === Part 1: Analyze 13-byte header entries ===
print("=== 13-byte entries, bytes 4-12 ===")
for i in range(40):
    base = 0x30 + i * 13
    rec = bytes(data[base:base+13])
    w = rec[4]
    h = rec[5]
    b6 = rec[6]
    b7 = rec[7]
    off3 = struct.unpack('<I', rec[8:12])[0] & 0xFFFFFF
    b12 = rec[12]
    valid = 0 < off3 < file_size
    print(f"  [{i:3d}] w={w:3d} h={h:3d} [6]={b6:3d} [7]={b7:3d} off24=0x{off3:06x} {'VALID' if valid else '     '} [12]={b12}")

# === Part 2: Scan for valid offsets in first 4 bytes of each entry ===
print("\n=== Looking for valid offsets in bytes 0-3 ===")
for i in range(155):
    base = 0x30 + i * 13
    rec = bytes(data[base:base+13])
    off = struct.unpack('<I', rec[0:4])[0]
    # check truncated versions
    off24 = off & 0xFFFFFF
    if 0x80b < off24 < file_size:
        print(f"  Entry {i:3d}: bytes 0-3 as 24-bit = 0x{off24:06x}  data: {' '.join(f'{b:02x}' for b in data[off24:off24+4])}")

# === Part 3: Render the 64x64 block at 0x080000 as a sprite with game colors ===
# Game uses indices 0-79. We know area 0x080000 has mostly small values (0-25).
# Let's understand the pattern better.

print("\n=== Block analysis at 0x080000 ===")
region = 0x080000
# Value histogram in first 4096 bytes
vals = list(data[region:region+4096])
from collections import Counter
hist = Counter(vals)
print(f"Value distribution (top 15): {hist.most_common(15)}")
print(f"Max value: {max(vals)}")

# Look at the special value 0xee=238 at position 0x080011
# and 0xb0=176 at 0x01ea20
# These are likely SENTINEL/END-OF-SPRITE markers!
print(f"\nSpecial values at 0x{region:x}+17: {data[region+17]:02x}")
print(f"Special value in sprite data at 0x01ea20: {data[0x01ea20]:02x}")

# Search for all 0xb0 and 0xee occurrences in the sprite region (0x01ea44 to 0x090000)
print("\nOccurrences of 0xb0 and 0xee in sprite region 0x01ea44-0x090000:")
for sentinel in [0xb0, 0xee, 0xfe, 0xff, 0xfd, 0xfc]:
    positions = [i for i in range(0x01ea44, 0x090000) if data[i] == sentinel]
    print(f"  0x{sentinel:02x}: {len(positions)} occurrences, first 5: {[f'0x{p:06x}' for p in positions[:5]]}")

# === Part 4: Try treating region as row-based with row markers ===
# What if the format is:
#   sentinel_0xee = end of current sprite
#   sentinel_0xb0 = separator/next element  
print("\n=== Trying sentinel-based parsing ===")
# Look at sprite region 0x07f7b7 (first found sprite)
off = 0x07f7b7
print(f"Data around first sprite 0x{off:x}:")
for j in range(off - 16, off + 80, 16):
    row = data[j:j+16]
    hex_str = ' '.join(f'{b:02x}' for b in row)
    marker = "<<<" if j == off else "   "
    print(f"  {marker} 0x{j:06x}: {hex_str}")
