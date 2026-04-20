#!/usr/bin/env python3
"""
GloftMASS J2ME Sprite Extractor - Final Version
Extracts indexed-color sprites from m3_0 using palette from section 2.
Palette assignments from palettesAmount.bin (31 sprite groups, Little-Endian RGB565).

File format discovered:
- m3_0: 11 sections (offsets as u32 LE with upper byte as flags)
  - sections 0-1, 3-8: raw sprite pixel data (1 byte per pixel = palette index)
  - section 2: 8704 bytes = palette data (RGB565 LE, up to 4352 colors)
  - section 9: 2.8MB tile map (values 0-50 = level map indices)
- palettesAmount.bin:
  - byte[0]: num_sprite_groups (31)
  - per group: u16_BE palette_byte_offset + u8 frame_count
  - palette_byte_offset is direct byte index into section 2 palette data
- Sprite format: u8 width, u8 height, then width*height bytes of palette indices
  - pixel value 0 = transparent
"""

import struct, os, sys
from PIL import Image

def main():
    # Input files
    m3_path = 'm3_0'
    pal_path = 'palettesAmount.bin'
    out_dir = 'decoded_sprites'
    
    if not os.path.exists(m3_path):
        print(f"ERROR: {m3_path} not found. Run from the game data directory.")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)

    with open(m3_path, 'rb') as f:
        m3 = f.read()
    
    with open(pal_path, 'rb') as f:
        raw_pal = f.read()

    print(f"m3_0: {len(m3):,} bytes")
    print(f"palettesAmount.bin: {len(raw_pal)} bytes")

    # --- Parse section table ---
    sec_count = struct.unpack('<I', m3[0:4])[0]
    entries = [struct.unpack('<I', m3[4+i*4:8+i*4])[0] >> 8 for i in range(sec_count)]
    entries.append(len(m3))
    print(f"Sections: {sec_count}")

    # Section 2 = palette data (8704 bytes = up to 4352 RGB565 colors)
    pal_section_off = entries[2]
    pal_data = m3[pal_section_off:pal_section_off + 8704]
    print(f"Palette section: 0x{pal_section_off:06x}, {len(pal_data)} bytes ({len(pal_data)//2} colors)")

    # --- Parse palettesAmount.bin ---
    num_groups = raw_pal[0]
    sprite_groups = []
    pos = 1
    for i in range(num_groups):
        pal_byte_off = struct.unpack('>H', raw_pal[pos:pos+2])[0]
        fc = raw_pal[pos+2]
        pos += 3
        sprite_groups.append((pal_byte_off, fc))
    print(f"Sprite groups: {num_groups}")

    # --- Color lookup ---
    def get_color(pal_byte_off, pixel_idx):
        """Get RGBA color from palette. pixel_idx=0 -> transparent."""
        if pixel_idx == 0:
            return (0, 0, 0, 0)
        off = pal_byte_off + pixel_idx * 2
        if off + 2 > len(pal_data):
            return (255, 0, 255, 255)  # magenta = out of bounds
        v = struct.unpack('<H', pal_data[off:off+2])[0]
        r = ((v >> 11) & 0x1F) * 8
        g = ((v >>  5) & 0x3F) * 4
        b = (v & 0x1F) * 8
        return (r, g, b, 255)

    # --- Brute-force sprite scan ---
    VALID_DIM = {8, 16, 24, 32, 48, 64}
    all_sprites = []
    p = 0
    while p < len(m3) - 4:
        w = m3[p]; h = m3[p+1]
        if w in VALID_DIM and h in VALID_DIM:
            sz = w * h
            if p + 2 + sz <= len(m3):
                pix = m3[p+2:p+2+sz]
                mv = max(pix)
                fill = sum(1 for px in pix if px > 0) / sz
                uq = len(set(pix))
                if mv < 200 and 0.02 < fill < 0.98 and uq >= 2:
                    all_sprites.append((p, w, h, bytes(pix)))
                    p += 2 + sz
                    continue
        p += 1

    print(f"Found {len(all_sprites)} sprites via brute-force scan")

    # --- Render sprites ---
    scale_map = {8: 8, 16: 4, 24: 4, 32: 3, 48: 2, 64: 2}
    saved = 0

    for idx, (off, w, h, pix) in enumerate(all_sprites):
        # Assign sprite group by cycling through the 31 groups
        grp_idx = idx % num_groups
        pal_byte_off, fc = sprite_groups[grp_idx]

        img = Image.new('RGBA', (w, h))
        px = img.load()
        for y in range(h):
            for x in range(w):
                px[x, y] = get_color(pal_byte_off, pix[y * w + x])

        scale = scale_map.get(max(w, h), 2)
        out_img = img.resize((w * scale, h * scale), Image.NEAREST)
        fname = f'{out_dir}/s{idx:04d}_{w}x{h}_0x{off:06x}_grp{grp_idx:02d}_pal{pal_byte_off}.png'
        out_img.save(fname)
        saved += 1

    print(f"Saved {saved} sprites to '{out_dir}/'")
    print("Done!")

if __name__ == '__main__':
    main()
