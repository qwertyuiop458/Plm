#!/usr/bin/env python3
"""
Gameloft J2ME sprite format parser.

Reverse-engineered from decompiled a.class method `a.a(byte[], int)`.

FILE CONTAINER FORMAT (m0, m1, m2, m3_0, m4_0, m6_*, m7, m8, m9, ...):
    u8 count
    count * u32 LE offsets  (start positions in data, relative to end of header)
    raw data bytes
    
    Each entry i spans data[offsets[i] : offsets[i+1]]
    (last offset marks end, so count-1 actual entries)

ENTRY FORMAT (sprite container):
    Header (9 bytes):
        [0-1]   magic 0xDF 0x03
        [2-5]   flags:u32 LE        -> controls bit 15 (0x8000 = extended anchors)
        [6-7]   frame_count:u16 LE
        [8]     skipped

    Frame table (frame_count entries):
        marker = u8
        if marker == 255 or 254:
            value:u32 LE (4 bytes), width:u8, height:u8   (6 more bytes -> 7 total)
        else (type 0):
            x:u16  (marker is LOW byte, read 1 more byte for high)
            y:u16 LE (2 bytes)
            w:u16 LE (2 bytes)
            h:u16 LE (2 bytes)
            (8 bytes total including marker)

    After frame table, multiple sub-tables (anchors, strips, animations, etc.)

    PALETTE section:
        u16 LE marker:
            0x8888 (-30584): ARGB8888 (4 bytes/color)
            0x4444 (17476):  ARGB4444 (2 bytes/color, expanded to 8888)
            0x6505 (25861):  RGB565   (2 bytes/color, alpha set; idx 0 if color==63519 is transparent)
        u8 palette_bank_count
        u8 colors_per_palette (0 means 256)
        For each bank: colors_per_palette * (2 or 4 bytes) depending on marker

    u16 LE tail_marker (usually 0x64F0 = 25840 for 8-bit compressed)

    Per-frame pixel data:
        For each frame:
            u16 LE size
            size bytes (palette indices)
"""
import struct
import os
import sys
from PIL import Image


def parse_container(data):
    """Parse outer m-file container. Returns list of entry bytes."""
    count = data[0]
    header_size = 1 + count * 4
    offsets = []
    for i in range(count):
        o = struct.unpack('<I', data[1 + i*4:5 + i*4])[0]
        offsets.append(o)
    entries = []
    for i in range(count - 1):
        start = header_size + offsets[i]
        end = header_size + offsets[i+1]
        entries.append(data[start:end])
    return entries


def rgb565_to_argb(v):
    if v == 63519:  # 0xF81F = magenta = transparent
        return 0x00000000
    r = (v & 0xF800) << 8
    g = (v & 0x07E0) << 5
    b = (v & 0x001F) << 3
    return 0xFF000000 | r | g | b


def argb4444_to_argb8888(v):
    a = (v & 0xF000) >> 12
    r = (v & 0x0F00) >> 8
    g = (v & 0x00F0) >> 4
    b = (v & 0x000F)
    return (a | a<<4) << 24 | (r | r<<4) << 16 | (g | g<<4) << 8 | (b | b<<4)


class SpriteEntry:
    def __init__(self, data):
        """Parse a single sprite entry (one m-file section)."""
        self.data = data
        self.frame_count = 0
        self.frames = []     # list of (type, x, y, w, h) or (type, val, w, h)
        self.palettes = []   # list of palette banks (each is list of ARGB ints)
        self.pixel_data = [] # list of bytes per frame
        self._parse()

    def _parse(self):
        d = self.data
        n = 0
        # Header
        if len(d) < 9:
            raise ValueError("too short")
        if d[0] != 0xDF or d[1] != 0x03:
            raise ValueError(f"bad magic: {d[0]:02x} {d[1]:02x}")
        self.flags = struct.unpack('<I', d[2:6])[0]
        self.frame_count = struct.unpack('<H', d[6:8])[0]
        # byte 8 skipped
        n = 9

        # Frame table (use Option B: type 0 marker is low byte of x)
        for fi in range(self.frame_count):
            marker = d[n]; n += 1
            if marker == 255 or marker == 254:
                val = struct.unpack('<I', d[n:n+4])[0]; n += 4
                w = d[n]; n += 1
                h = d[n]; n += 1
                self.frames.append({'type': 1 if marker==255 else 2, 'val': val, 'w': w, 'h': h})
            else:
                # marker is the low byte of x
                x_hi = d[n]; n += 1
                x = marker | (x_hi << 8)
                y = struct.unpack('<H', d[n:n+2])[0]; n += 2
                w = struct.unpack('<H', d[n:n+2])[0]; n += 2
                h = struct.unpack('<H', d[n:n+2])[0]; n += 2
                self.frames.append({'type': 0, 'x': x, 'y': y, 'w': w, 'h': h})

        # Sub-section 1: anchor-like table (?)
        n6 = struct.unpack('<H', d[n:n+2])[0]; n += 2
        has_ext = (self.flags & 0x8000) != 0
        for i in range(n6):
            n += 1  # byte
            n += 2  # u16
            if has_ext:
                ext = d[n]; n += 1
                if ext > 0:
                    # nothing extra to skip here in the loop, values stored
                    pass

        # Sub-section 2: strip-like table (5 bytes per entry)
        n5 = struct.unpack('<H', d[n:n+2])[0]; n += 2
        for i in range(n5):
            n += 5  # byte, byte, u16, u16, byte

        # Sub-section 3: animation frame list (3 bytes per entry)
        n4 = struct.unpack('<H', d[n:n+2])[0]; n += 2
        for i in range(n4):
            n += 3  # byte, u16

        # Palette section header
        pal_marker = struct.unpack('<H', d[n:n+2])[0]; n += 2
        bank_count = d[n]; n += 1
        colors_per_bank = d[n]; n += 1
        if colors_per_bank == 0:
            colors_per_bank = 256

        self.pal_marker = pal_marker
        self.bank_count = bank_count
        self.colors_per_bank = colors_per_bank

        # Read palettes
        for bi in range(bank_count):
            bank = []
            if pal_marker == 34952 or pal_marker == 0x8888:  # ARGB8888
                for ci in range(colors_per_bank):
                    v = struct.unpack('<I', d[n:n+4])[0]; n += 4
                    bank.append(v)
            elif pal_marker == 17476 or pal_marker == 0x4444:  # ARGB4444
                for ci in range(colors_per_bank):
                    v = struct.unpack('<H', d[n:n+2])[0]; n += 2
                    bank.append(argb4444_to_argb8888(v))
            elif pal_marker == 25861 or pal_marker == 0x6505:  # RGB565
                for ci in range(colors_per_bank):
                    v = struct.unpack('<H', d[n:n+2])[0]; n += 2
                    bank.append(rgb565_to_argb(v))
            else:
                # unknown palette format — skip bank without parsing
                raise ValueError(f"unknown palette marker: 0x{pal_marker:04x}")
            self.palettes.append(bank)

        # Tail marker
        self.tail = struct.unpack('<H', d[n:n+2])[0]; n += 2

        # Per-frame pixel data: u16 size + size bytes per frame
        for fi in range(self.frame_count):
            sz = struct.unpack('<H', d[n:n+2])[0]; n += 2
            self.pixel_data.append(bytes(d[n:n+sz]))
            n += sz

        self.parse_end = n

    def render_frame(self, frame_idx, palette_bank=0, scale=1):
        """Render frame as RGBA PIL image."""
        frame = self.frames[frame_idx]
        if frame['type'] != 0:
            return None
        w, h = frame['w'], frame['h']
        if w <= 0 or h <= 0:
            return None
        pixels = self.pixel_data[frame_idx]
        pal = self.palettes[palette_bank % len(self.palettes)]
        img = Image.new('RGBA', (w, h))
        px = img.load()
        for y in range(h):
            for x in range(w):
                idx = y * w + x
                if idx >= len(pixels):
                    continue
                ci = pixels[idx]
                argb = pal[ci] if ci < len(pal) else 0xFFFF00FF
                a = (argb >> 24) & 0xFF
                r = (argb >> 16) & 0xFF
                g = (argb >> 8) & 0xFF
                b = argb & 0xFF
                px[x, y] = (r, g, b, a)
        if scale > 1:
            img = img.resize((w*scale, h*scale), Image.NEAREST)
        return img


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    out_dir = 'game_sprites'
    os.makedirs(out_dir, exist_ok=True)

    files = ['m0', 'm1', 'm2', 'm3_0', 'm4_0', 'm6_0', 'm6_1', 'm6_2',
             'm6_3', 'm6_4', 'm6_5', 'm7', 'm8', 'm9', 'm10', 'm11_0',
             'm11_1', 'm12', 't0']
    total_sprites = 0
    total_ok = 0
    for fname in files:
        if not os.path.exists(fname):
            continue
        with open(fname, 'rb') as f:
            data = f.read()
        try:
            entries = parse_container(data)
        except Exception as e:
            print(f"{fname}: container parse failed: {e}")
            continue

        print(f"\n{fname}: {len(entries)} entries")
        for ei, entry in enumerate(entries):
            try:
                sprite = SpriteEntry(entry)
                total_ok += 1
                print(f"  entry[{ei}]: {sprite.frame_count} frames, "
                      f"{sprite.bank_count} palette banks ({sprite.colors_per_bank} colors), "
                      f"pal_marker=0x{sprite.pal_marker:04x}, consumed={sprite.parse_end}/{len(entry)}")
                # Render all frames
                for fi, frame in enumerate(sprite.frames):
                    if frame['type'] != 0:
                        continue
                    w, h = frame['w'], frame['h']
                    if w == 0 or h == 0:
                        continue
                    try:
                        img = sprite.render_frame(fi, palette_bank=0, scale=2)
                        if img:
                            img.save(f'{out_dir}/{fname}_e{ei}_f{fi:03d}_{w}x{h}.png')
                            total_sprites += 1
                    except Exception as e:
                        pass
            except Exception as e:
                print(f"  entry[{ei}]: parse failed: {e}")
    print(f"\n=== Total sprite entries parsed: {total_ok} ===")
    print(f"=== Total frame PNGs saved: {total_sprites} ===")


if __name__ == '__main__':
    main()
