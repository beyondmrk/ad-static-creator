"""Strip all metadata from final images/videos and PROVE it is gone.

  python clean.py <in> <out>     # clean one file
  python clean.py --check <file> # verify only; exit 1 if anything remains

Images are re-encoded from raw pixels (drops EXIF, XMP, ICC, text chunks,
C2PA/content credentials, AI-generator tags). Videos are remuxed with
ffmpeg -map_metadata -1 in bitexact mode (no re-encode, no encoder tag).
"""
import json, struct, subprocess, sys
from pathlib import Path

from PIL import Image

IMG = {".png", ".jpg", ".jpeg", ".webp"}
VID = {".mp4", ".mov", ".m4v"}
PNG_OK = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"}
JPG_OK = {0xD8, 0xE0, 0xDB, 0xC0, 0xC1, 0xC2, 0xC4, 0xDA, 0xD9, 0xDD} | set(range(0xD0, 0xD8))
VID_FMT_OK = {"major_brand", "minor_version", "compatible_brands"}
VID_STREAM_OK = {"language", "handler_name", "vendor_id"}


def clean_image(src, dst):
    im = Image.open(src)
    im.load()
    alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    im = im.convert("RGBA" if alpha else "RGB")
    bare = Image.frombytes(im.mode, im.size, im.tobytes())  # pixels only, no .info
    ext = dst.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        bare.convert("RGB").save(dst, "JPEG", quality=95, optimize=True)
    elif ext == ".webp":
        bare.save(dst, "WEBP", quality=95)
    else:
        bare.save(dst, "PNG", optimize=True)


def clean_video(src, dst):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-map", "0",
           "-map_metadata", "-1", "-map_chapters", "-1", "-c", "copy",
           "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
           "-movflags", "+faststart", str(dst)]
    subprocess.run(cmd, check=True)


def leftovers(path):
    """Return a list of metadata findings; empty list = clean."""
    p, ext, bad = Path(path), Path(path).suffix.lower(), []
    data = p.read_bytes()
    if ext == ".png":
        i = 8
        while i < len(data):
            n, t = struct.unpack(">I4s", data[i:i + 8])
            if t not in PNG_OK:
                bad.append(f"png chunk {t.decode(errors='replace')}")
            i += 12 + n
    elif ext in (".jpg", ".jpeg"):
        i = 2
        while i < len(data) - 1 and data[i] == 0xFF:
            m = data[i + 1]
            if m not in JPG_OK:
                bad.append(f"jpeg marker 0x{m:02X}")
            if m == 0xDA:
                break
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    elif ext == ".webp":
        for tag in (b"EXIF", b"XMP ", b"ICCP"):
            if tag in data[:4096] or tag in data[-65536:]:
                bad.append(f"webp chunk {tag.decode()}")
    elif ext in VID:
        r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json",
                            "-show_entries", "format_tags:stream_tags", str(p)],
                           capture_output=True, text=True, check=True)
        j = json.loads(r.stdout)
        for k in (j.get("format", {}).get("tags") or {}):
            if k not in VID_FMT_OK:
                bad.append(f"format tag {k}")
        for s in j.get("streams", []):
            for k in (s.get("tags") or {}):
                if k not in VID_STREAM_OK:
                    bad.append(f"stream tag {k}")
    else:
        bad.append(f"unsupported type {ext}")
    return bad


def clean(src, dst):
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in IMG:
        clean_image(src, dst)
    elif src.suffix.lower() in VID:
        clean_video(src, dst)
    else:
        raise SystemExit(f"unsupported type: {src}")
    bad = leftovers(dst)
    if bad:
        raise SystemExit(f"METADATA STILL PRESENT in {dst.name}: {bad}")
    return dst


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        bad = leftovers(sys.argv[2])
        print("CLEAN" if not bad else f"NOT CLEAN: {bad}")
        sys.exit(1 if bad else 0)
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(f"CLEAN -> {clean(sys.argv[1], sys.argv[2])}")
