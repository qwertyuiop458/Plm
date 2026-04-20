#!/usr/bin/env python3
"""
Final sprite decoder using the real game palette from m1.
palettesAmount.bin maps each sprite to a byte-offset into m1's color table.
"""

import struct, os
from PIL import Image

BASE = "/vercel/share/v0-project"
OUT  = os.path.join(BASE, "sprites_final")
os.makedirs(OUT, exist_ok=True)

# ── 1. Load global color table from m1 ─────────────────────────────────────
# m1 uses same header format: u32 count, then (u8_flags + u24_offset) per entry
with open(os.path.join(BASE, "m1"), "rb") as f:
    m1 = f.read()

m1_count = struct.unpack("<I", m1[0:4])[0]
m1_offsets = []
for i in range(m1_count):
    base = 4 + i * 4
    # flags byte + 3-byte LE offset
    off3 = struct.unpack("<I", m1[base:base+4])[0] >> 8
    m1_offsets.append(off3)

HEADER_SIZE = 4 + m1_count * 4

# Build flat color table from all sections concatenated (in order)
m1_offsets_abs = [HEADER_SIZE + o for o in m1_offsets]
m1_offsets_abs.append(len(m1))

color_table_bytes = bytearray()
for i in range(m1_count):
    s = m1_offsets_abs[i]
    e = m1_offsets_abs[i + 1]
    color_table_bytes.extend(m1[s:e])

print(f"m1 color table: {len(color_table_bytes)} bytes = {len(color_table_bytes)//2} RGB565 colors")

def get_color(byte_offset):
    """Get RGB color from global color table at byte_offset."""
    if byte_offset + 1 >= len(color_table_bytes):
        return (255, 0, 255, 255)  # magenta = out of range
    v = struct.unpack("<H", color_table_bytes[byte_offset:byte_offset+2])[0]
    r = ((v >> 11) & 0x1F) * 8
    g = ((v >> 5)  & 0x3F) * 4
    b = (v & 0x1F) * 8
    return (r, g, b, 255)

# ── 2. Load palette assignments ─────────────────────────────────────────────
with open(os.path.join(BASE, "palettesAmount.bin"), "rb") as f:
    pal_raw = f.read()

num_palettes = pal_raw[0]  # 31
pal_byte_offsets = [
    struct.unpack("<H", pal_raw[1 + i*2 : 3 + i*2])[0]
    for i in range(155)
]
print(f"Palette assignments: {num_palettes} palettes, {len(pal_byte_offsets)} sprites")

# ── 3. Parse m3_0 sprite descriptor table ───────────────────────────────────
with open(os.path.join(BASE, "m3_0"), "rb") as f:
    m3 = f.read()

# Header: u32 count=11, then 11*(u8_flags + u24_offset)
m3_sec_count = struct.unpack("<I", m3[0:4])[0]
HEADER_M3 = 4 + m3_sec_count * 4  # = 48 bytes = 0x30

# 155 sprite descriptors of 13 bytes each, starting at 0x30
# Each descriptor: we'll use it to locate the actual pixel data offset
# The brute-force pass found pixels starting at specific offsets;
# we'll scan m3_0 for (w, h, pixels...) blocks with indexed data.

# ── 4. Brute-force scan m3_0 for indexed sprite blocks ──────────────────────
VALID_DIM = {8, 16, 24, 32, 48, 64}
sprites = []   # (file_offset, w, h)

pos = HEADER_M3
while pos < len(m3) - 4:
    w = m3[pos]
    h = m3[pos + 1]
    if w in VALID_DIM and h in VALID_DIM:
        sz = w * h
        if pos + 2 + sz <= len(m3):
            pix = m3[pos + 2 : pos + 2 + sz]
            max_v   = max(pix)
            nonzero = sum(1 for p in pix if p > 0)
            fill    = nonzero / sz
            unique  = len(set(pix))
            if max_v < 200 and fill > 0.05 and fill < 0.99 and unique >= 3:
                sprites.append((pos, w, h))
                pos += 2 + sz
                continue
    pos += 1

print(f"Found {len(sprites)} sprite blocks in m3_0")

# ── 5. Assign palette to each sprite & render ───────────────────────────────
# Map sprite index → palette byte offset (use pal_byte_offsets, cycle if needed)
saved = 0
for idx, (off, w, h) in enumerate(sprites):
    # Get palette byte offset for this sprite
    pal_off = pal_byte_offsets[idx % len(pal_byte_offsets)]

    pixels = m3[off + 2 : off + 2 + w * h]

    img  = Image.new("RGBA", (w, h))
    pix  = img.load()

    for y in range(h):
        for x in range(w):
            cidx  = pixels[y * w + x]
            color = get_color(pal_off + cidx * 2)
            # index 0 → transparent
            if cidx == 0:
                color = (0, 0, 0, 0)
            pix[x, y] = color

    # Scale up small sprites so they're visible
    scale = max(1, 64 // max(w, h))
    out   = img.resize((w * scale, h * scale), Image.NEAREST)
    out.save(os.path.join(OUT, f"sprite_{idx:04d}_{w}x{h}_0x{off:06x}.png"))
    saved += 1

print(f"Saved {saved} sprites to {OUT}/")

# ── 6. Also try ALL pal offsets on the largest sprite for comparison ─────────
if sprites:
    big = max(sprites, key=lambda s: s[1]*s[2])
    off, w, h = big
    pixels = m3[off + 2 : off + 2 + w * h]
    comparison_dir = os.path.join(OUT, "palette_comparison")
    os.makedirs(comparison_dir, exist_ok=True)

    unique_offsets = sorted(set(pal_byte_offsets))
    for pal_off in unique_offsets:
        img  = Image.new("RGBA", (w, h))
        pix  = img.load()
        for y in range(h):
            for x in range(w):
                cidx  = pixels[y * w + x]
                color = (0,0,0,0) if cidx == 0 else get_color(pal_off + cidx * 2)
                pix[x, y] = color
        scale = max(1, 128 // max(w, h))
        out_img = img.resize((w*scale, h*scale), Image.NEAREST)
        out_img.save(os.path.join(comparison_dir, f"pal_off_{pal_off:05d}_{w}x{h}.png"))

    print(f"Saved {len(unique_offsets)} palette variants for largest sprite ({w}x{h})")

print("Done.")
