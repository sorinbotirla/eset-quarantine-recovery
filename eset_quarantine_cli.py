#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ESET Quarantine Recovery – bash-like CLI, pure-Python decryptor

Usage:
  python3 eset_quarantine_cli.py --quarantine /path/to/quarantine \
                                 --output /path/to/extracted \
                                 [--ocr /path/to/screenshots]

Behavior:
- Scans only *.NQF files (ignores *.NAF).
- Decrypts each NQF to "<basename>.NQF.00000000_ESET.out" under output/<hash>/
- If --ocr provided and pytesseract+Pillow importable, scrapes candidate (name,size)
  pairs from screenshots and tries to match each .out by size (±2% for MB/GB, ±3% for KB).
- Prints list like dexray3.sh, supports:
    confirm [Y] | edit list [E] | cancel [C]
- On confirm, for each item with a final target name, copies the .out to that name
  (next to the .out file); items with (missing) are left as-is (only the .out).
"""

import argparse
import os
import re
import sys
import shutil
from pathlib import Path

# ----------------------------
# Optional OCR dependencies
# ----------------------------
HAS_OCR_DEPS = False
try:
    from PIL import Image, ImageFilter, ImageOps
    import pytesseract
    HAS_OCR_DEPS = True
except Exception:
    HAS_OCR_DEPS = False

# ----------------------------
# ESET Decryptor (pure Python)
# ----------------------------
def decrypt_eset_bytes(data: bytes) -> bytes:
    # Port of DeXRAY's extract_eset transformation:
    # new_byte = ((orig_byte - 84) % 256) ^ 0xA5
    out = bytearray(len(data))
    for i, b in enumerate(data):
        out[i] = ((b - 84) & 0xFF) ^ 0xA5
    return bytes(out)

# ----------------------------
# Size helpers
# ----------------------------
def to_bytes_human(s: str):
    """
    Parse sizes like: '54 B', '44.4 KB', '47.5 kB', '126.3 MB', '1.2 GB'
    Robust to commas/locale: '76,2 MB' or stray trailing punctuation.
    Returns int bytes or None.
    """
    if not s:
        return None
    raw = s.strip().upper()
    raw = raw.replace(",", ".")
    # remove trailing junk like '.' or ',' at end
    raw = re.sub(r"[^\d\.KMG B]+$", "", raw)
    m = re.search(r"([\d\.]+)\s*([KMG]?B)\b", raw)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2)
    mult = {"B":1, "KB":1024, "MB":1024**2, "GB":1024**3}[unit]
    return int(num * mult)

def humanize(nbytes: int) -> str:
    if nbytes is None:
        return "-"
    if nbytes >= 1024**3:
        return f"{nbytes/1024**3:.1f} GB"
    if nbytes >= 1024**2:
        return f"{nbytes/1024**2:.1f} MB"
    if nbytes >= 1024:
        return f"{nbytes/1024:.1f} KB"
    return f"{nbytes} B"

def within_tol(sz: int, target: int) -> bool:
    if target <= 0:
        return False
    rel = abs(sz - target) / target
    # keep your earlier tolerances
    return rel <= (0.02 if target >= 1024*1024 else 0.03)

# ----------------------------
# OCR: parse candidates
# ----------------------------
FILE_EXTS = (
    "zip","rar","7z","exe","msi","apk","img","iso","bin","gz","bz2","xz","tar",
    "dll","scr","php","jar","pdf","sis","sisx"
)
FILE_RE = re.compile(
    r'([A-Za-z0-9_\-\(\)\[\].\s]+?\.(?:' + "|".join(FILE_EXTS) + r'))',
    re.IGNORECASE
)
SIZE_RE = re.compile(r'([\d\.,]+)\s*([KMG]B)\b', re.IGNORECASE)

def ocr_text_from_image(path: Path) -> str:
    # light pre-processing; robust & fast
    img = Image.open(path).convert("L")
    # normalize contrast and slightly sharpen
    img = ImageOps.autocontrast(img)
    img = img.filter(ImageFilter.SHARPEN)
    # upscale modestly
    w, h = img.size
    img = img.resize((int(w*1.8), int(h*1.8)))
    text = pytesseract.image_to_string(
        img,
        lang="eng",
        config="--oem 1 --psm 4 -c preserve_interword_spaces=1"
    )
    return text

def ocr_candidates(img_dir: Path):
    """
    Return list of (name, size_bytes). Dedup results.
    """
    cands = []
    if not img_dir or not img_dir.exists():
        return cands
    for img in sorted(img_dir.iterdir()):
        if not img.is_file():
            continue
        if img.suffix.lower() not in (".png",".jpg",".jpeg",".bmp",".tif",".tiff"):
            continue
        try:
            text = ocr_text_from_image(img)
        except Exception:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            mf = FILE_RE.search(line)
            if not mf:
                continue
            name = Path(mf.group(1)).name.strip()
            # look for size on same line or neighbors
            slines = " ".join(lines[max(i-1,0): i+2])
            ms = SIZE_RE.search(slines)
            if not ms:
                continue
            sz = to_bytes_human(ms.group(0))
            if sz:
                cands.append((name, sz))
    # dedup
    seen = set()
    uniq = []
    for nm, sz in cands:
        key = (nm.lower(), sz)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((nm, sz))
    return uniq

# ----------------------------
# Core CLI
# ----------------------------
def scan_nqf(quarantine: Path):
    return sorted([p for p in quarantine.rglob("*") if p.suffix.upper()==".NQF"])

def decrypt_one(nqf_path: Path, out_root: Path):
    """
    Decrypt nqf_path into out_root/<hash>/<basename>.NQF.00000000_ESET.out
    Returns (folder, out_path, size_bytes)
    """
    base = nqf_path.name
    hash_dir = out_root / nqf_path.stem  # folder by hash-like stem
    hash_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"{base}.00000000_ESET.out"
    out_path = hash_dir / out_name

    # Always overwrite out to reflect the current flow (fast).
    data = nqf_path.read_bytes()
    dec = decrypt_eset_bytes(data)
    out_path.write_bytes(dec)

    return hash_dir, out_path, out_path.stat().st_size

def propose_names(out_items, cand_list):
    """
    out_items: list of dict with keys: idx, nqf, out_path, out_size
    cand_list: list of (name, size_b)
    Returns dict idx->proposal with fields name, label ('', '(possible duplicate)' or '(missing)')
    """
    proposals = {}
    # For quick lookup group candidates by size
    by_size = {}
    for nm, sz in cand_list:
        by_size.setdefault(sz, []).append(nm)

    # If many items have the same OCR size/name, mark duplicates
    for it in out_items:
        matched_names = []
        for cand_sz, names in by_size.items():
            if within_tol(it["out_size"], cand_sz):
                matched_names.extend(names)
        matched_names = list(dict.fromkeys(matched_names))  # unique preserve order

        if not matched_names:
            proposals[it["idx"]] = {"name":"(missing)", "label":"(missing)"}
        else:
            # Prefer the single best name; if many, pick first but flag duplicate
            nm = matched_names[0]
            label = "(possible duplicate)" if len(matched_names) > 1 else ""
            proposals[it["idx"]] = {"name": nm, "label": label}
    return proposals

def print_header(quarantine, out_root, img_dir, found):
    print(f"[i] Scanning quarantine: {quarantine}")
    print(f"[i] Found {found} quarantined file(s).")
    if img_dir:
        if HAS_OCR_DEPS:
            print("[ocr] scanning images…")
            for p in sorted(img_dir.iterdir()):
                if p.suffix.lower() in (".png",".jpg",".jpeg",".bmp",".tif",".tiff"):
                    print(f"[ocr] parsed: {p}")
        else:
            print("[ocr] pytesseract/Pillow not available; skipping OCR.")

def print_decrypt_lines(items):
    # Lines like bash:
    # [ok] HASH.NQF -> HASH.NQF.00000000_ESET.out (47.5 KB)
    for it in items:
        nqf = it["nqf"].name
        out = it["out_path"].name
        size = humanize(it["out_size"])
        print(f"[ok] {nqf} -> {out} ({size})")

def compact_listing(items, proposals):
    # Mimic your shell layout without headers:
    # "1 HASH.NQF -> HASH.NQF.00000000_ESET.out -> Some Name (possible duplicate)"
    lines = []
    for it in items:
        idx = it["idx"]
        nqf = it["nqf"].name
        out = it["out_path"].name
        prop = proposals.get(idx, {"name":"(missing)", "label":"(missing)"})
        nm = prop["name"]
        lb = f" {prop['label']}" if prop["label"] else ""
        lines.append(f"{idx:>2} {nqf}  ->  {out}  ->  {nm}{lb}")
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser(description="ESET Quarantine Recovery (bash-like, pure-Python)")
    ap.add_argument("--quarantine", required=True, help="Path to ESET quarantine folder")
    ap.add_argument("--output", required=True, help="Path to output root")
    ap.add_argument("--ocr", help="Optional OCR screenshots folder")
    args = ap.parse_args()

    qdir = Path(args.quarantine).resolve()
    out_root = Path(args.output).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    imgdir = Path(args.ocr).resolve() if args.ocr else None

    nqfs = scan_nqf(qdir)
    print_header(qdir, out_root, imgdir, len(nqfs))
    if not nqfs:
        print(f"[!] No .NQF files under: {qdir}")
        sys.exit(0)

    # Decrypt stage (like bash: show immediate progress)
    items = []
    for i, p in enumerate(nqfs, start=1):
        folder, out_path, out_sz = decrypt_one(p, out_root)
        items.append({
            "idx": i,
            "nqf": p,
            "folder": folder,
            "out_path": out_path,
            "out_size": out_sz,
        })
    print_decrypt_lines(items)

    # OCR stage
    cand_list = []
    if imgdir and imgdir.exists() and HAS_OCR_DEPS:
        try:
            cand_list = ocr_candidates(imgdir)
        except Exception:
            cand_list = []

    proposals = propose_names(items, cand_list)

    # Show the compact list
    print("\nProposed names\n")
    print(compact_listing(items, proposals))
    print("\nconfirm [Y]  edit list [E]  cancel [C]: ", end="", flush=True)

    while True:
        try:
            choice = input().strip().lower()
        except EOFError:
            choice = "c"
        if choice in ("y", "yes"):
            break
        elif choice in ("c", "q", "cancel"):
            print("[!] Aborting.")
            sys.exit(0)
        elif choice in ("e", "edit"):
            # ask which index
            try:
                idx = int(input("Which number to edit? ").strip())
            except Exception:
                print("[!] Invalid index.")
                print("confirm [Y]  edit list [E]  cancel [C]: ", end="", flush=True)
                continue
            if not any(it["idx"] == idx for it in items):
                print("[!] Index not in list.")
                print("confirm [Y]  edit list [E]  cancel [C]: ", end="", flush=True)
                continue
            newname = input("Enter new name (with extension) or leave blank to mark (missing): ").strip()
            if not newname:
                proposals[idx] = {"name":"(missing)", "label":"(missing)"}
            else:
                proposals[idx] = {"name": newname, "label": ""}

            print()  # re-render after edit
            print(compact_listing(items, proposals))
            print("\nconfirm [Y]  edit list [E]  cancel [C]: ", end="", flush=True)
        else:
            print("confirm [Y]  edit list [E]  cancel [C]: ", end="", flush=True)

    # Confirmed — write “named copies” where applicable
    made = 0
    for it in items:
        idx = it["idx"]
        out_path = it["out_path"]
        prop = proposals.get(idx, {"name":"(missing)", "label":"(missing)"})
        nm = prop["name"]
        if nm and nm != "(missing)":
            target = it["folder"] / nm
            if not target.exists():
                shutil.copy2(out_path, target)
                made += 1

    print(f"[✓] Done. Created {made} named copy/copies next to .out files.")
    print("    Output root: ", out_root)

if __name__ == "__main__":
    main()
