"""
Extract PNG images embedded in game data files.

Discovered: dataIGP (Gameloft IGP - In-Game Promotion bundle) contains 28
standard PNG images: font glyphs, UI icons, and game splash screens for
SOUL OF DARKNESS, REAL FOOTBALL, and ASPHALT 4.

PNG files are identified by the standard magic sequence:
  Start: 89 50 4E 47 0D 0A 1A 0A  (PNG signature)
  End:   49 45 4E 44 AE 42 60 82  (IEND chunk + CRC32)
"""
import os
import sys
from io import BytesIO

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_END = b"IEND\xae\x42\x60\x82"


def extract_pngs(filepath, out_dir):
    """Scan a binary file for embedded PNG images and save them."""
    with open(filepath, "rb") as f:
        data = f.read()

    fname = os.path.basename(filepath)
    pngs = []
    pos = 0
    while pos < len(data):
        sig_pos = data.find(PNG_SIG, pos)
        if sig_pos == -1:
            break
        end_pos = data.find(PNG_END, sig_pos)
        if end_pos == -1:
            break
        png_data = data[sig_pos : end_pos + 8]
        pngs.append((sig_pos, png_data))
        pos = end_pos + 8

    if not pngs:
        return []

    saved = []
    os.makedirs(out_dir, exist_ok=True)
    for i, (off, png_data) in enumerate(pngs):
        dims = ""
        if HAS_PIL:
            try:
                img = Image.open(BytesIO(png_data))
                dims = f"_{img.size[0]}x{img.size[1]}"
            except Exception:
                pass
        out_path = os.path.join(
            out_dir, f"{fname}_png{i:02d}{dims}_off0x{off:06x}.png"
        )
        with open(out_path, "wb") as o:
            o.write(png_data)
        saved.append(out_path)
    return saved


def main():
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(project_dir, "extracted_images")

    # Scan all likely binary data files in project root
    candidates = []
    for name in sorted(os.listdir(project_dir)):
        fp = os.path.join(project_dir, name)
        if not os.path.isfile(fp):
            continue
        # Skip obvious non-binary or output files
        if name.endswith((".py", ".md", ".png", ".jpg", ".json", ".yml", ".lock", ".txt")):
            continue
        if name.startswith("."):
            continue
        candidates.append(fp)

    total = 0
    for fp in candidates:
        saved = extract_pngs(fp, out_dir)
        if saved:
            print(f"{os.path.basename(fp)}: {len(saved)} PNG(s)")
            total += len(saved)

    print(f"\nTotal PNGs extracted: {total}")
    print(f"Output directory: {out_dir}")


if __name__ == "__main__":
    main()
