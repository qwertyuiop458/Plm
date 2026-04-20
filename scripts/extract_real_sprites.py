"""
Extract real JPEG sprites from m3_0 game file.
Finds all top-level (non-nested) JPEG images and saves them.
"""
import struct
import os
import io
import json
from PIL import Image

INPUT_FILE = os.path.join(os.path.dirname(__file__), '..', 'm3_0')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'real_sprites')

def find_jpeg_spans(data):
    """Find all JPEG start/end positions, return only top-level (non-nested)."""
    jpeg_sig = b'\xff\xd8\xff'
    jpeg_end = b'\xff\xd9'

    # Find all starts
    positions = []
    pos = 0
    while True:
        pos = data.find(jpeg_sig, pos)
        if pos == -1:
            break
        positions.append(pos)
        pos += 1

    # Find ends for each start
    jpeg_spans = []
    for start in positions:
        end = data.find(jpeg_end, start + 2)
        if end != -1:
            jpeg_spans.append((start, end + 2))

    # Keep only top-level (merge nested)
    top_level = []
    i = 0
    while i < len(jpeg_spans):
        s, e = jpeg_spans[i]
        j = i + 1
        while j < len(jpeg_spans) and jpeg_spans[j][0] < e:
            if jpeg_spans[j][1] > e:
                e = jpeg_spans[j][1]
            j += 1
        top_level.append((s, e))
        i = j

    return top_level


def main():
    print(f"Reading {INPUT_FILE}...")
    with open(INPUT_FILE, 'rb') as f:
        data = f.read()
    print(f"File size: {len(data):,} bytes")

    spans = find_jpeg_spans(data)
    print(f"Found {len(spans)} top-level JPEG images")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    manifest = []
    valid = 0
    invalid = 0

    for idx, (start, end) in enumerate(spans):
        chunk = data[start:end]
        out_path = os.path.join(OUTPUT_DIR, f'sprite_{idx:04d}.jpg')

        try:
            img = Image.open(io.BytesIO(chunk))
            img.load()
            w, h = img.size
            mode = img.mode

            # Save as JPEG
            img.save(out_path, 'JPEG', quality=95)
            valid += 1
            manifest.append({
                'index': idx,
                'file': f'sprite_{idx:04d}.jpg',
                'offset_hex': f'0x{start:06x}',
                'size_bytes': end - start,
                'width': w,
                'height': h,
                'mode': mode,
            })
            print(f"  [{idx:3d}] OK  {w:4d}x{h:4d}  {mode}  offset=0x{start:06x}  size={end-start}")
        except Exception as ex:
            invalid += 1
            print(f"  [{idx:3d}] ERR offset=0x{start:06x}  {ex}")

    # Save manifest
    manifest_path = os.path.join(OUTPUT_DIR, 'manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    print()
    print(f"Done! Valid: {valid}, Invalid: {invalid}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Manifest: {manifest_path}")


if __name__ == '__main__':
    main()
