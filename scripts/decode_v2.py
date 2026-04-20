#!/usr/bin/env python3
"""
Correct sprite decoder using m3_0 section[2] as the palette (17 banks x 256 RGB565).
palettesAmount.bin provides the byte-offset into this palette for each of 155 sprite groups.
"""

import struct, os
from PIL import Image

BASE = "/vercel/share/v0-project"
OUT  = os.path.join(BASE, "sprites_v2")
os.makedirs(OUT, exist_ok=True)

# ── 1. Load m3_0 and extract the built-in palette from section 2 ─────────────
with open(os.path.join(BASE, "m3_0"), "rb") as f:
    m3 = f.read()

count = struct.unpack("<I", m3[0:4])[0]  # 11 sections

def get_section(idx):
    base = 4 + idx * 4
    off = struct.unpack("<I", m3[base:base+4])[0] >> 8
    if idx + 1 < count:
        end = struct.unpack("<I", m3[4+(idx+1)*4:8+(idx+1)*4])[0] >> 8
    else:
        end = len(m3)
    return m3[off:end], off

pal_sec, pal_off = get_section(2)  # 8704 bytes = 17 banks * 512 bytes/bank
print(f"Palette section[2]: {len(pal_sec)} bytes = {len(pal_sec)//2} RGB565 colors")
print(f"  (= {len(pal_sec)//512} banks of 256 colors)")

def get_color(byte_offset, alpha_index=None):
    """Get RGBA from palette given byte offset. Index 0 = transparent."""
    if byte_offset + 1 >= len(pal_sec):
        return (255, 0, 255, 255)
    v = struct.unpack("<H", pal_sec[byte_offset:byte_offset+2])[0]
    r = ((v >> 11) & 0x1F) * 8
    g = ((v >> 5)  & 0x3F) * 4
    b = (v & 0x1F) * 8
    return (r, g, b, 255)

# ── 2. Show first 16 colors from each bank ──────────────────────────────────
print("\nFirst 8 colors per bank:")
for bank in range(len(pal_sec) // 512):
    bank_off = bank * 512
    colors = []
    for j in range(8):
        v = struct.unpack("<H", pal_sec[bank_off + j*2:bank_off + j*2 + 2])[0]
        r = ((v>>11)&0x1F)*8; g = ((v>>5)&0x3F)*4; b = (v&0x1F)*8
        colors.append(f"({r:3d},{g:3d},{b:3d})")
    print(f"  bank {bank:2d} (byte off {bank_off:5d}): {' '.join(colors)}")

# ── 3. Load palette assignments ──────────────────────────────────────────────
with open(os.path.join(BASE, "palettesAmount.bin"), "rb") as f:
    pal_raw = f.read()

num_pal = pal_raw[0]  # 31
pal_byte_offsets = [struct.unpack("<H", pal_raw[1+i*2:3+i*2])[0] for i in range(155)]

print(f"\npalettesAmount: {num_pal} palettes, {len(pal_byte_offsets)} assignments")
print(f"Unique palette byte-offsets: {sorted(set(pal_byte_offsets))}")

# ── 4. Parse sprite blocks from m3_0 sections 0,1,3-8 ──────────────────────
# Sections with sprite data have max ~255 and unique ~200+
# We brute-force scan all those sections for (w:u8, h:u8, pixels...) blocks
SPRITE_SECTIONS = [0, 1, 3, 4, 5, 6, 7, 8]  # skip sec[2]=palette, sec[9]=tilemap, sec[10]=empty

VALID_DIM = {8, 16, 24, 32, 48, 64}

all_sprites = []  # (abs_offset, w, h, section_idx)

for si in SPRITE_SECTIONS:
    sec_data, sec_abs = get_section(si)
    pos = 0
    sec_sprites = []
    while pos < len(sec_data) - 4:
        w = sec_data[pos]
        h = sec_data[pos + 1]
        if w in VALID_DIM and h in VALID_DIM:
            sz = w * h
            if pos + 2 + sz <= len(sec_data):
                pix = sec_data[pos + 2 : pos + 2 + sz]
                max_v   = max(pix)
                nonzero = sum(1 for p in pix if p > 0)
                fill    = nonzero / sz
                unique  = len(set(pix))
                # Accept if has reasonable content and index values fit in palette
                if max_v < 220 and fill > 0.05 and fill < 0.99 and unique >= 3:
                    abs_off = sec_abs + pos
                    all_sprites.append((abs_off, w, h, si))
                    pos += 2 + sz
                    continue
        pos += 1
    print(f"  Section {si}: found {len(all_sprites) - sum(1 for s in all_sprites if s[3] != si)} sprites")

print(f"\nTotal sprites found: {len(all_sprites)}")

# ── 5. Render each sprite with its assigned palette ─────────────────────────
# Match sprite abs_offset to descriptor index via ordering
# Since palettesAmount has 155 entries, we assign palette by sprite order
saved = 0
for idx, (abs_off, w, h, si) in enumerate(all_sprites):
    # Get palette byte offset for this sprite
    pal_off_bytes = pal_byte_offsets[idx % len(pal_byte_offsets)]

    pixels = m3[abs_off + 2 : abs_off + 2 + w * h]
    img  = Image.new("RGBA", (w, h))
    pix  = img.load()

    for y in range(h):
        for x in range(w):
            cidx  = pixels[y * w + x]
            color = (0, 0, 0, 0) if cidx == 0 else get_color(pal_off_bytes + cidx * 2)
            pix[x, y] = color

    scale = max(1, 64 // max(w, h))
    out   = img.resize((w * scale, h * scale), Image.NEAREST)
    fname = f"s{idx:04d}_{w}x{h}_sec{si}_0x{abs_off:06x}.png"
    out.save(os.path.join(OUT, fname))
    saved += 1

print(f"Saved {saved} sprites to {OUT}/")

# ── 6. Generate palette comparison grid ─────────────────────────────────────
# For one representative 48x48 sprite, try all 17 banks
big_sprites = [(abs_off, w, h, si) for abs_off, w, h, si in all_sprites if w >= 32 and h >= 32]
if big_sprites:
    abs_off, w, h, si = big_sprites[0]
    pixels = m3[abs_off + 2 : abs_off + 2 + w * h]
    compare_dir = os.path.join(OUT, "bank_compare")
    os.makedirs(compare_dir, exist_ok=True)

    for bank in range(len(pal_sec) // 512):
        pal_off_bytes = bank * 512
        img  = Image.new("RGBA", (w, h))
        pix  = img.load()
        for y in range(h):
            for x in range(w):
                cidx  = pixels[y * w + x]
                color = (0, 0, 0, 0) if cidx == 0 else get_color(pal_off_bytes + cidx * 2)
                pix[x, y] = color
        scale = max(1, 128 // max(w, h))
        out = img.resize((w*scale, h*scale), Image.NEAREST)
        out.save(os.path.join(compare_dir, f"bank{bank:02d}_{w}x{h}.png"))

    print(f"Bank comparison for {w}x{h} sprite saved to {compare_dir}/")

print("Done.")
