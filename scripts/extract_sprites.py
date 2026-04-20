#!/usr/bin/env python3
"""
Sprite extractor for m3_0 game file.
Analyzes the file structure and extracts all sprite images.
"""

import os
import struct
from PIL import Image

def read_bytes(f, n):
    """Read n bytes from file."""
    return f.read(n)

def read_uint8(f):
    """Read unsigned 8-bit integer."""
    return struct.unpack('<B', f.read(1))[0]

def read_uint16(f):
    """Read unsigned 16-bit integer (little-endian)."""
    return struct.unpack('<H', f.read(2))[0]

def read_uint32(f):
    """Read unsigned 32-bit integer (little-endian)."""
    return struct.unpack('<I', f.read(4))[0]

def read_int16(f):
    """Read signed 16-bit integer (little-endian)."""
    return struct.unpack('<h', f.read(2))[0]

def rgb565_to_rgb888(pixel):
    """Convert RGB565 to RGB888."""
    r = ((pixel >> 11) & 0x1F) << 3
    g = ((pixel >> 5) & 0x3F) << 2
    b = (pixel & 0x1F) << 3
    return (r, g, b)

def rgba4444_to_rgba8888(pixel):
    """Convert RGBA4444 to RGBA8888."""
    r = ((pixel >> 12) & 0xF) * 17
    g = ((pixel >> 8) & 0xF) * 17
    b = ((pixel >> 4) & 0xF) * 17
    a = (pixel & 0xF) * 17
    return (r, g, b, a)

def argb8888_to_rgba(pixel):
    """Convert ARGB8888 to RGBA."""
    a = (pixel >> 24) & 0xFF
    r = (pixel >> 16) & 0xFF
    g = (pixel >> 8) & 0xFF
    b = pixel & 0xFF
    return (r, g, b, a)

def analyze_header(filepath):
    """Analyze the file header structure."""
    print(f"Analyzing file: {filepath}")
    print("=" * 60)
    
    with open(filepath, 'rb') as f:
        # Read first bytes to understand structure
        f.seek(0)
        first_int = read_uint32(f)
        print(f"First 4 bytes (uint32): {first_int}")
        
        # This looks like a count or offset table
        f.seek(0)
        data = f.read(100)
        
        # Print as hex
        print("\nFirst 100 bytes (hex):")
        for i in range(0, min(100, len(data)), 16):
            hex_str = ' '.join(f'{b:02x}' for b in data[i:i+16])
            print(f"  {i:04x}: {hex_str}")
        
        # Try to identify the format
        f.seek(0)
        
        # Check if first 4 bytes is a count
        count = read_uint32(f)
        print(f"\nPossible entry count: {count}")
        
        if count > 0 and count < 10000:
            # Read potential offset table
            print(f"\nReading {min(count, 20)} potential offsets:")
            offsets = []
            for i in range(min(count, 20)):
                offset = read_uint32(f)
                offsets.append(offset)
                print(f"  Entry {i}: offset = {offset} (0x{offset:08x})")
            
            return count, offsets
    
    return 0, []

def try_extract_png_chunks(filepath, output_dir):
    """Look for PNG signatures in the file."""
    print("\nSearching for PNG signatures...")
    
    PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
    
    with open(filepath, 'rb') as f:
        data = f.read()
    
    png_positions = []
    pos = 0
    while True:
        pos = data.find(PNG_SIGNATURE, pos)
        if pos == -1:
            break
        png_positions.append(pos)
        pos += 1
    
    print(f"Found {len(png_positions)} PNG signatures")
    
    for i, start in enumerate(png_positions):
        # Find IEND chunk
        iend_pos = data.find(b'IEND', start)
        if iend_pos != -1:
            end = iend_pos + 8  # IEND + CRC
            png_data = data[start:end]
            
            output_path = os.path.join(output_dir, f"png_sprite_{i:04d}.png")
            with open(output_path, 'wb') as out:
                out.write(png_data)
            print(f"  Extracted PNG at offset {start}: {output_path}")
    
    return len(png_positions)

def try_extract_raw_sprites(filepath, output_dir):
    """Try to extract raw pixel data as sprites."""
    print("\nTrying to extract raw sprite data...")
    
    with open(filepath, 'rb') as f:
        f.seek(0)
        
        # Read header
        entry_count = read_uint32(f)
        print(f"Entry count from header: {entry_count}")
        
        if entry_count == 0 or entry_count > 10000:
            print("Invalid entry count, trying different approach...")
            return 0
        
        # Skip the 0x00 after count
        # Read offset table
        offsets = []
        for i in range(entry_count):
            offset = read_uint32(f)
            offsets.append(offset)
        
        print(f"Read {len(offsets)} offsets")
        print(f"Offset table ends at: {f.tell()}")
        
        # Now try to read sprite data at each offset
        sprites_extracted = 0
        
        for i, offset in enumerate(offsets[:50]):  # Try first 50
            try:
                f.seek(offset)
                
                # Try to read sprite header
                # Common formats: width (2 bytes), height (2 bytes), then pixel data
                width = read_uint16(f)
                height = read_uint16(f)
                
                if width > 0 and width < 512 and height > 0 and height < 512:
                    print(f"\n  Sprite {i} at offset {offset}: {width}x{height}")
                    
                    # Try to read as RGB565
                    pixel_count = width * height
                    data_size = pixel_count * 2
                    
                    pixel_data = f.read(data_size)
                    if len(pixel_data) == data_size:
                        # Create image
                        img = Image.new('RGB', (width, height))
                        pixels = img.load()
                        
                        for y in range(height):
                            for x in range(width):
                                idx = (y * width + x) * 2
                                if idx + 1 < len(pixel_data):
                                    pixel = struct.unpack('<H', pixel_data[idx:idx+2])[0]
                                    r, g, b = rgb565_to_rgb888(pixel)
                                    pixels[x, y] = (r, g, b)
                        
                        output_path = os.path.join(output_dir, f"sprite_{i:04d}_{width}x{height}.png")
                        img.save(output_path)
                        sprites_extracted += 1
                        print(f"    Saved: {output_path}")
                        
            except Exception as e:
                pass
        
        return sprites_extracted

def extract_m3_format(filepath, output_dir):
    """
    Extract sprites from M3 mobile game format.
    This format typically has:
    - Header with sprite count
    - Offset table
    - Sprite data with dimensions and pixel data
    """
    print("\nExtracting M3 format sprites...")
    
    with open(filepath, 'rb') as f:
        data = f.read()
    
    # Analyze structure
    # First 4 bytes: number of entries (0x0B = 11)
    entry_count = struct.unpack('<I', data[0:4])[0]
    print(f"Entry count: {entry_count}")
    
    # Read offset table (each entry is 4 bytes, starting at offset 4)
    offsets = []
    for i in range(entry_count):
        offset = struct.unpack('<I', data[4 + i*4:4 + i*4 + 4])[0]
        offsets.append(offset)
        print(f"  Section {i}: offset = {offset} (0x{offset:06x})")
    
    sprites_extracted = 0
    
    # Process each section
    for section_idx, section_offset in enumerate(offsets):
        print(f"\nProcessing section {section_idx} at offset {section_offset}...")
        
        # Determine section size
        if section_idx + 1 < len(offsets):
            section_size = offsets[section_idx + 1] - section_offset
        else:
            section_size = len(data) - section_offset
        
        print(f"  Section size: {section_size} bytes")
        
        section_data = data[section_offset:section_offset + section_size]
        
        # Create section output directory
        section_dir = os.path.join(output_dir, f"section_{section_idx:02d}")
        os.makedirs(section_dir, exist_ok=True)
        
        # Try to parse sprites from this section
        pos = 0
        sprite_num = 0
        
        while pos < len(section_data) - 8:
            try:
                # Read potential sprite header
                # Format could be: x, y, width, height, flags, data...
                
                # Try reading as: offset_x (1), something (1), offset_y (1), something (1), width (1), height (1)
                x = section_data[pos]
                flag1 = section_data[pos + 1]
                y = section_data[pos + 2]
                flag2 = section_data[pos + 3]
                w = section_data[pos + 4]
                h = section_data[pos + 5]
                
                # Check if this looks like valid sprite dimensions
                if w > 0 and w <= 256 and h > 0 and h <= 256:
                    # Calculate expected data size
                    expected_size = w * h
                    
                    if pos + 6 + expected_size <= len(section_data):
                        print(f"    Potential sprite at {pos}: pos=({x},{y}) size={w}x{h}")
                        
                        # Try to extract as indexed color (1 byte per pixel)
                        pixel_data = section_data[pos + 6:pos + 6 + expected_size]
                        
                        # Create grayscale image
                        img = Image.new('L', (w, h))
                        img.putdata(list(pixel_data))
                        
                        output_path = os.path.join(section_dir, f"sprite_{sprite_num:04d}_{w}x{h}.png")
                        img.save(output_path)
                        sprites_extracted += 1
                        sprite_num += 1
                        
                        pos += 6 + expected_size
                        continue
                
                pos += 1
                
            except Exception as e:
                pos += 1
    
    return sprites_extracted

def extract_with_header_analysis(filepath, output_dir):
    """
    More sophisticated extraction based on detailed header analysis.
    """
    print("\nDetailed header analysis extraction...")
    
    with open(filepath, 'rb') as f:
        data = f.read()
    
    # The file starts with what looks like offset table
    # 0x0B (11) entries, followed by offsets
    
    num_sections = struct.unpack('<I', data[0:4])[0]
    print(f"Number of sections: {num_sections}")
    
    sections = []
    for i in range(num_sections):
        offset = struct.unpack('<I', data[4 + i*4:8 + i*4])[0]
        sections.append(offset)
    
    # Each section likely contains sprite sheets or individual sprites
    sprites_extracted = 0
    
    for sec_idx, sec_start in enumerate(sections):
        sec_end = sections[sec_idx + 1] if sec_idx + 1 < len(sections) else len(data)
        sec_data = data[sec_start:sec_end]
        
        sec_dir = os.path.join(output_dir, f"section_{sec_idx:02d}")
        os.makedirs(sec_dir, exist_ok=True)
        
        print(f"\nSection {sec_idx}: {sec_start} - {sec_end} ({len(sec_data)} bytes)")
        
        # Analyze section structure
        if len(sec_data) < 10:
            continue
        
        # Print first bytes of section
        print(f"  First 32 bytes: {' '.join(f'{b:02x}' for b in sec_data[:32])}")
        
        # The section might have its own header with sprite count and sub-offsets
        # Try to extract based on pattern matching
        
        pos = 0
        sprite_idx = 0
        
        # Look for sprite-like patterns
        while pos < len(sec_data) - 6:
            # Check for various sprite header patterns
            
            # Pattern: short entries (x, flags, y, flags, w, h)
            x = sec_data[pos]
            f1 = sec_data[pos + 1] 
            y = sec_data[pos + 2]
            f2 = sec_data[pos + 3]
            w = sec_data[pos + 4]
            h = sec_data[pos + 5]
            
            # Validate dimensions
            if 4 <= w <= 128 and 4 <= h <= 128:
                pixel_count = w * h
                
                # Check for indexed pixels (1 byte per pixel)
                if pos + 6 + pixel_count <= len(sec_data):
                    pixel_bytes = sec_data[pos + 6:pos + 6 + pixel_count]
                    
                    # Basic validation - not all zeros or all same value
                    unique_vals = len(set(pixel_bytes))
                    if unique_vals > 1:
                        # Create indexed image
                        img = Image.new('L', (w, h))
                        pixels = list(pixel_bytes)
                        img.putdata(pixels)
                        
                        # Scale up for visibility
                        img_scaled = img.resize((w * 2, h * 2), Image.NEAREST)
                        
                        out_path = os.path.join(sec_dir, f"sprite_{sprite_idx:04d}_{w}x{h}.png")
                        img_scaled.save(out_path)
                        
                        print(f"  Extracted sprite {sprite_idx} at {pos}: {w}x{h}, {unique_vals} colors")
                        sprites_extracted += 1
                        sprite_idx += 1
                        
                        pos += 6 + pixel_count
                        continue
            
            pos += 1
    
    return sprites_extracted

def brute_force_sprite_search(filepath, output_dir):
    """
    Brute force search for sprite-like data patterns.
    """
    print("\nBrute force sprite search...")
    
    with open(filepath, 'rb') as f:
        data = f.read()
    
    os.makedirs(os.path.join(output_dir, "found_sprites"), exist_ok=True)
    
    sprites_found = 0
    
    # Common sprite sizes to look for
    common_sizes = [
        (8, 8), (16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
        (16, 8), (8, 16), (32, 16), (16, 32), (32, 24), (24, 32),
        (48, 32), (32, 48), (64, 32), (32, 64)
    ]
    
    # Look for patterns where width/height bytes precede valid pixel data
    pos = 0
    while pos < len(data) - 100:
        w = data[pos]
        h = data[pos + 1]
        
        if (w, h) in common_sizes or (h, w) in common_sizes:
            pixel_count = w * h
            
            if pos + 2 + pixel_count <= len(data):
                pixel_data = data[pos + 2:pos + 2 + pixel_count]
                
                unique = len(set(pixel_data))
                
                # Check if it looks like valid sprite data
                if 2 < unique < pixel_count * 0.9:
                    img = Image.new('L', (w, h))
                    img.putdata(list(pixel_data))
                    
                    out_path = os.path.join(output_dir, "found_sprites", f"bf_sprite_{sprites_found:04d}_at_{pos}_{w}x{h}.png")
                    img.save(out_path)
                    
                    print(f"  Found potential sprite at {pos}: {w}x{h}, {unique} unique values")
                    sprites_found += 1
                    
                    pos += 2 + pixel_count
                    continue
        
        pos += 1
    
    return sprites_found

def dump_raw_sections(filepath, output_dir):
    """
    Dump each section as raw binary for further analysis.
    """
    print("\nDumping raw sections...")
    
    with open(filepath, 'rb') as f:
        data = f.read()
    
    num_sections = struct.unpack('<I', data[0:4])[0]
    
    sections_dir = os.path.join(output_dir, "raw_sections")
    os.makedirs(sections_dir, exist_ok=True)
    
    sections = []
    for i in range(num_sections):
        offset = struct.unpack('<I', data[4 + i*4:8 + i*4])[0]
        sections.append(offset)
    
    for i, start in enumerate(sections):
        end = sections[i + 1] if i + 1 < len(sections) else len(data)
        sec_data = data[start:end]
        
        out_path = os.path.join(sections_dir, f"section_{i:02d}.bin")
        with open(out_path, 'wb') as f:
            f.write(sec_data)
        
        print(f"  Section {i}: {start}-{end} ({len(sec_data)} bytes) -> {out_path}")

def main():
    filepath = "/vercel/share/v0-project/m3_0"
    output_dir = "/vercel/share/v0-project/extracted_sprites"
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # First, analyze the file structure
    analyze_header(filepath)
    
    # Try various extraction methods
    
    # 1. Look for embedded PNGs
    png_count = try_extract_png_chunks(filepath, output_dir)
    print(f"\nExtracted {png_count} PNG images")
    
    # 2. Try M3 format extraction
    m3_count = extract_m3_format(filepath, output_dir)
    print(f"\nExtracted {m3_count} M3 format sprites")
    
    # 3. Detailed header analysis
    header_count = extract_with_header_analysis(filepath, output_dir)
    print(f"\nExtracted {header_count} sprites via header analysis")
    
    # 4. Brute force search
    bf_count = brute_force_sprite_search(filepath, output_dir)
    print(f"\nFound {bf_count} sprites via brute force")
    
    # 5. Dump raw sections for manual inspection
    dump_raw_sections(filepath, output_dir)
    
    print("\n" + "=" * 60)
    print(f"Total sprites extracted to: {output_dir}")
    print("=" * 60)

if __name__ == "__main__":
    main()
