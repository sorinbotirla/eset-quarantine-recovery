#!/usr/bin/env python3
import os, re, shutil
from math import inf

# --- paths ---
OUT_ROOT = "/home/sorin/Desktop/eset/esetextracted"   # hash folders live here

# --- helper to normalize name (drop any leading folder parts) ---
def base_only(name: str) -> str:
    name = name.replace("\\", "/")
    return os.path.basename(name.strip())

# --- corrected list from the screenshots (cache* removed, small <44KB ignored) ---
# Size numbers are "display" sizes; we accept a tolerance when matching.
CANDIDATES = [
    ("Metro Exodus v1.0.0.7 Plus +20 Trainer-FutureX.rar", "594.7 KB"),
    ("Nethunter-Sony_Xperia_XA_F3111-MT6755-20170223_122556.zip", "76.2 MB"),
    ("UltraMP3.zip", "631.1 KB"),
    ("Ultra MP3 v1.45 Keygen.rar", "44.3 KB"),
    ("UltraMP3 keygen.exe (SFILE.MOBI).zip", "44.4 KB"),
    ("keygen ultra mp3.zip", "44.4 KB"),
    ("UltraMP3keygen.exe", "47.5 KB"),                     # from UltraMP3\\UltraMP3keygen.exe
    ("Ultra MP3 v1.45 Keygen.exe", "47.5 KB"),
    ("UltraMP3_keygen.exe", "47.5 KB"),                    # from ...\\UltraMP3_keygen.exe
    # big ones
    ("nethunter-2024.1-oneplus7-oos-eleven-kalifs-full.zip", "2.2 GB"),
    ("Nexus 5-20240115T193417Z-001.zip", "1.6 GB"),
    ("nethunter-2022.4-hammerhead-marshmallow-kalifs-full.zip", "1.8 GB"),
    ("nethunter-2020.3-hammerhead-nougat-kalifs-full.zip", "1.2 GB"),
    ("UFED 7.68 Activation Files.rar", "126.3 MB"),
]

# --- convert "human" size to bytes (binary units like Windows uses) ---
def size_to_bytes(s: str) -> int:
    s = s.strip().upper().replace(",", ".")
    m = re.match(r"([\d\.]+)\s*([KMG]B)", s)
    if not m:
        raise ValueError(f"Bad size: {s}")
    num = float(m.group(1))
    unit = m.group(2)
    mul = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}[unit]
    return int(num * mul)

CANDS = [
    (base_only(name), size_to_bytes(sz))
    for (name, sz) in CANDIDATES
]

# Keep track so we don't reuse the same display-entry for multiple outs of the same size
taken = set()

# Tolerance: relative difference allowed when matching by size
# (screenshots round sizes; start with 2% for big files, 3% for ~44 KB group)
TOL_SMALL = 0.03  # ~3% for tiny files
TOL_BIG   = 0.02  # ~2% for >= 1 MB

def best_match(byte_size: int):
    tol = TOL_SMALL if byte_size < 1024*1024 else TOL_BIG
    best_i, best_diff = None, inf
    for i, (name, target) in enumerate(CANDS):
        if i in taken:
            continue
        # relative difference
        diff = abs(byte_size - target) / target
        if diff < best_diff:
            best_diff = diff
            best_i = i
    if best_i is not None and best_diff <= (TOL_SMALL if byte_size < 1024*1024 else TOL_BIG):
        taken.add(best_i)
        return CANDS[best_i][0], best_diff
    return None, None

def main():
    made = 0
    for hash_dir in sorted(os.listdir(OUT_ROOT)):
        full_dir = os.path.join(OUT_ROOT, hash_dir)
        if not os.path.isdir(full_dir):
            continue
        # find any *_ESET.out
        outs = [f for f in os.listdir(full_dir) if f.endswith("_ESET.out")]
        for of in outs:
            out_path = os.path.join(full_dir, of)
            size = os.path.getsize(out_path)
            if size < 44 * 1024:   # ignore <44 KB
                continue

            guess, diff = best_match(size)
            if not guess:
                print(f"[skip] {out_path}  (no good size match; {size} bytes)")
                continue

            # final target name (next to .out)
            tgt = os.path.join(full_dir, base_only(guess))
            if os.path.exists(tgt):
                print(f"[exists] {tgt}")
                continue

            shutil.copy2(out_path, tgt)
            made += 1
            print(f"[copy]   {of}  ->  {os.path.basename(tgt)}   (size match Δ~{diff*100:.2f}%)")

    print(f"[done] created {made} guessed-name copies.")

if __name__ == "__main__":
    main()
