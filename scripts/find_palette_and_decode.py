"""
Find color palette and properly decode sprites from m3_0 game file.
"""
import struct
import os
from PIL import Image

INPUT_FILE = os.path.join(os.path.dirname(__file__), '..', 'm3_0')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'decoded_sprites')

def load_data():
    with open(INPUT_FILE, 'rb') as f:
        return f.read()


def find_palette_candidates(data):
    """Search for RGB565 palette blocks (256 colors = 512 bytes)."""
    candidates = []
    for off in range(0, len(data) - 512, 2):
        # Check if 256 consecutive u16 values all look like valid colors
        # RGB565: any 16-bit value is technically valid, so look for
        # blocks with good color distribution
        block = data[off:off+512]
        colors = [struct.unpack('<H', block[i*2:i*2+2])[0] for i in range(256)]
        
        # Heuristic: diverse colors, not all zero or all same
        unique = len(set(colors))
        if unique > 50:
            # Check that colors[0] is likely transparent (black or fully saturated)
            c0 = colors[0]
            r0 = ((c0 >> 11) & 0x1F)
            g0 = ((c0 >> 5) & 0x3F)
            b0 = (c0 & 0x1F)
            if r0 == 0 and g0 == 0 and b0 == 0:
                candidates.append((off, unique))
    
    # Sort by most unique colors
    candidates.sort(key=lambda x: -x[1])
    return candidates[:10]


def find_palette_rgb(data):
    """Search for RGB (3-byte) palette blocks."""
    candidates = []
    for off in range(0, len(data) - 768, 3):
        block = data[off:off+768]
        colors = [(block[i*3], block[i*3+1], block[i*3+2]) for i in range(256)]
        unique = len(set(colors))
        if unique > 50:
            candidates.append((off, unique))
    candidates.sort(key=lambda x: -x[1])
    return candidates[:5]


def analyze_sprite_pixels(data, offset, w, h):
    """Get pixel values and stats for a sprite."""
    pixels = list(data[offset+2:offset+2+w*h])
    unique = sorted(set(pixels))
    return pixels, unique


def decode_with_palette_rgb565(pixels, w, h, palette_data):
    """Decode indexed pixels using RGB565 palette."""
    img = Image.new('RGB', (w, h))
    pix = img.load()
    
    colors = []
    for i in range(256):
        v = struct.unpack('<H', palette_data[i*2:i*2+2])[0]
        r = ((v >> 11) & 0x1F) << 3
        g = ((v >> 5) & 0x3F) << 2
        b = (v & 0x1F) << 3
        colors.append((r, g, b))
    
    for y in range(h):
        for x in range(w):
            idx = pixels[y * w + x]
            pix[x, y] = colors[idx % 256]
    
    return img


def decode_with_palette_rgb(pixels, w, h, palette_data):
    """Decode indexed pixels using RGB palette."""
    img = Image.new('RGB', (w, h))
    pix = img.load()
    
    colors = [(palette_data[i*3], palette_data[i*3+1], palette_data[i*3+2]) for i in range(256)]
    
    for y in range(h):
        for x in range(w):
            idx = pixels[y * w + x]
            pix[x, y] = colors[idx % 256]
    
    return img


def decode_as_raw_indexed(pixels, w, h):
    """Render the index values as grayscale (1:1)."""
    img = Image.new('L', (w, h))
    img.putdata(pixels)
    return img


def try_alternate_formats(data, offset, w, h):
    """Try different pixel encoding formats."""
    results = []
    
    # 1. RGB565 direct (2 bytes per pixel)
    size_565 = w * h * 2
    if offset + size_565 <= len(data):
        img = Image.new('RGB', (w, h))
        pix = img.load()
        for y in range(h):
            for x in range(w):
                i = y * w + x
                v = struct.unpack('<H', data[offset+i*2:offset+i*2+2])[0]
                r = ((v >> 11) & 0x1F) << 3
                g = ((v >> 5) & 0x3F) << 2
                b = (v & 0x1F) << 3
                pix[x, y] = (r, g, b)
        results.append(('rgb565', img))
    
    # 2. ARGB4444 (2 bytes per pixel)
    if offset + size_565 <= len(data):
        img = Image.new('RGBA', (w, h))
        pix = img.load()
        for y in range(h):
            for x in range(w):
                i = y * w + x
                v = struct.unpack('<H', data[offset+i*2:offset+i*2+2])[0]
                a = ((v >> 12) & 0xF) * 17
                r = ((v >> 8) & 0xF) * 17
                g = ((v >> 4) & 0xF) * 17
                b = (v & 0xF) * 17
                pix[x, y] = (r, g, b, a)
        results.append(('argb4444', img))
    
    # 3. Raw indexed as grayscale
    size_1 = w * h
    if offset + size_1 <= len(data):
        pixels = list(data[offset:offset+size_1])
        img = Image.new('L', (w, h))
        img.putdata(pixels)
        results.append(('indexed_gray', img))
    
    return results


def main():
    print(f"Loading {INPUT_FILE}...")
    data = load_data()
    print(f"File size: {len(data):,} bytes")
    print()

    # Known sprite locations from brute force
    known_sprites = [
        (0x018919, 16, 16),
        (0x019625, 16, 32),
        (0x01a60b, 64, 64),
        (0x01d881, 8, 16),
        (0x01dc29, 8, 8),
        (0x01e492, 48, 48),
        (0x01ee67, 16, 16),
    ]

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- Step 1: Try to find palettes ---
    print("=== Searching for RGB565 palettes ===")
    rgb565_candidates = find_palette_candidates(data)
    print(f"Found {len(rgb565_candidates)} RGB565 palette candidates:")
    for off, uniq in rgb565_candidates:
        print(f"  offset=0x{off:06x}  unique_colors={uniq}")

    print()
    print("=== Trying alternate pixel formats on known sprites ===")
    
    for sprite_off, w, h in known_sprites:
        print(f"\nSprite at 0x{sprite_off:06x} ({w}x{h}):")
        
        # Try RGB565 direct (no palette)
        formats = try_alternate_formats(data, sprite_off + 2, w, h)
        for fmt_name, img in formats:
            out = os.path.join(OUTPUT_DIR, f"s_{sprite_off:06x}_{w}x{h}_{fmt_name}.png")
            img_scaled = img.resize((max(64, w*4), max(64, h*4)), Image.NEAREST)
            img_scaled.save(out)
            print(f"  Saved: {out}")
        
        # Try with each palette candidate
        pixels_indexed, unique = analyze_sprite_pixels(data, sprite_off, w, h)
        for pal_off, uniq in rgb565_candidates[:3]:
            pal_data = data[pal_off:pal_off+512]
            img = decode_with_palette_rgb565(pixels_indexed, w, h, pal_data)
            out = os.path.join(OUTPUT_DIR, f"s_{sprite_off:06x}_{w}x{h}_pal565_0x{pal_off:06x}.png")
            img_scaled = img.resize((max(64, w*4), max(64, h*4)), Image.NEAREST)
            img_scaled.save(out)
            print(f"  With palette@0x{pal_off:06x}: {out}")

    # --- Step 2: Also scan the area BETWEEN 0x30 and the first sprite ---
    print()
    print(f"=== Scanning area 0x30 to 0x18919 for data patterns ===")
    # Print a summary of what's in there
    start_of_data = 0x30 + 155 * 13  # after header table = 0x80b
    first_sprite = 0x018919
    gap_size = first_sprite - start_of_data
    print(f"Gap from 0x{start_of_data:06x} to 0x{first_sprite:06x} = {gap_size:,} bytes")
    
    # Dump gap samples
    for off in range(start_of_data, min(start_of_data + 512, first_sprite), 32):
        row = data[off:off+32]
        hexs = ' '.join(f'{b:02x}' for b in row)
        print(f"  0x{off:06x}: {hexs}")


if __name__ == '__main__':
    main()
