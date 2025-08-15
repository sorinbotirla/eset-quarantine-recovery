#!/usr/bin/env bash
set -euo pipefail

# ==========================================================
#  DeXRAY ESET .NQF Extractor + OCR name mapping (interactive)
#  Clean output • Generic • User confirms before writing
# ==========================================================
# Usage:
#   sudo ./dexray.sh --quarantine <dir> --output <dir> [--ocr <imgdir>] [--install-deps]
# ==========================================================

QDIR=""; OUT=""; IMGDIR=""
INSTALL_DEPS=0

# ---------- parse args ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --quarantine) QDIR="${2:-}"; shift 2 ;;
    --output)     OUT="${2:-}"; shift 2 ;;
    --ocr)        IMGDIR="${2:-}"; shift 2 ;;
    --install-deps) INSTALL_DEPS=1; shift ;;
    -h|--help)
      echo "Usage: $0 --quarantine <dir> --output <dir> [--ocr <images_dir>] [--install-deps]"
      exit 0 ;;
    *) echo "[!] Unknown option: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$QDIR" || -z "$OUT" ]] && { echo "[!] Usage: $0 --quarantine <dir> --output <dir> [--ocr <images_dir>] [--install-deps]"; exit 1; }

LOG="$OUT/logs"; TOOLS="$OUT/tools"
mkdir -p "$OUT" "$LOG" "$TOOLS"

# ---------- deps ----------
if [[ "$INSTALL_DEPS" -eq 1 ]]; then
  sudo apt-get update -y
  sudo apt-get install -y \
    perl libcrypt-blowfish-perl libcrypt-des-perl libcrypt-rc4-perl \
    libdigest-md5-file-perl libdigest-perl curl file p7zip-full
  if [[ -n "$IMGDIR" ]]; then
    sudo apt-get install -y tesseract-ocr tesseract-ocr-eng imagemagick python3
  fi
fi

# ---------- DeXRAY ----------
DEXRAY="$TOOLS/DeXRAY.pl"
if [[ ! -f "$DEXRAY" ]]; then
  curl -sS -L -o "$DEXRAY" https://hexacorn.com/d/DeXRAY.pl
  chmod +x "$DEXRAY"
fi

# ---------- gather NQFs ----------
mapfile -d '' NQF_LIST < <(find "$QDIR" -type f -iname '*.nqf' -print0)
TOTAL=${#NQF_LIST[@]}
[[ $TOTAL -eq 0 ]] && { echo "[!] No .NQF files in: $QDIR"; exit 1; }

# ---------- extraction (only if no .out exists yet) ----------
for NQF in "${NQF_LIST[@]}"; do
  HASH="$(basename "$NQF" .NQF)"
  DEST="$OUT/$HASH"; mkdir -p "$DEST"
  if compgen -G "$DEST/*_ESET.out" > /dev/null; then
    continue
  fi
  cp -n -- "$NQF" "$DEST/"
  ( cd "$DEST" && perl "$DEXRAY" "$(basename "$NQF")" ) > "$LOG/${HASH}.dexray.log" 2>&1 || true
done

# ---------- OCR (optional) ----------
OCRTEXT=""
if [[ -n "$IMGDIR" ]]; then
  OCRTEXT="$OUT/ocr.txt"; : > "$OCRTEXT"
  shopt -s nullglob
  for img in "$IMGDIR"/*.{png,PNG,jpg,JPG,jpeg,JPEG,bmp,BMP,tif,TIF,tiff,TIFF}; do
    convert "$img" -colorspace Gray -resize 200% -sharpen 0x1 -contrast-stretch 1%x1% pnm:- \
      | tesseract stdin stdout -l eng --oem 1 --psm 6 -c preserve_interword_spaces=1 >> "$OCRTEXT" 2>/dev/null || true
    echo >> "$OCRTEXT"
  done
  shopt -u nullglob
fi

# ---------- Python helper: write to a temp file so stdin is free ----------
PYFILE="$(mktemp "$TOOLS/ocr_interactive.XXXXXX.py")"
cat > "$PYFILE" << 'PY'
import os, re, sys, shutil

OUT_ROOT = sys.argv[1]
OCRTEXT  = sys.argv[2] if len(sys.argv) > 2 else ""

def base(p): return os.path.basename(p)

# Collect out files
outs=[]
for h in sorted(os.listdir(OUT_ROOT)):
    d=os.path.join(OUT_ROOT,h)
    if not os.path.isdir(d): continue
    for f in os.listdir(d):
        if f.endswith("_ESET.out"):
            p=os.path.join(d,f)
            try: sz=os.path.getsize(p)
            except: sz=0
            outs.append((p, sz))

if not outs:
    print("[i] No *_ESET.out found.")
    sys.exit(0)

# Parse OCR names/sizes
cands=[]
if OCRTEXT and os.path.exists(OCRTEXT) and os.path.getsize(OCRTEXT)>0:
    text=open(OCRTEXT,"r",encoding="utf-8",errors="ignore").read()
    lines=text.splitlines()
    fname_pat=re.compile(r'([A-Za-z0-9 _\-\(\)\[\].]+?\.(zip|rar|7z|exe|msi|apk|img|iso|bin|gz|bz2|xz|tar|dll|scr|php|jar|pdf))',re.I)

    def norm_units(s): return re.sub(r'\b([kKmMgG])[bB8tTeE]?\b', r'\1', s)
    def sizes(line):
        L=norm_units(line.replace(",","."))
        out=[]
        for m in re.finditer(r'(\d+(?:\.\d+)?)\s*([kKmMgG])\b', L):
            val=float(m.group(1)); unit=m.group(2).upper()
            mul={"K":1024,"M":1024**2,"G":1024**3}[unit]
            out.append(int(val*mul))
        for m in re.finditer(r'\b(\d+)\s*[bB]\b', L): out.append(int(m.group(1)))
        return out

    LOOK=4
    i=0
    while i<len(lines):
        m=fname_pat.search(lines[i])
        if not m: i+=1; continue
        name=os.path.basename(m.group(1))
        # ignore obvious cache patterns
        if re.search(r'(?i)cache|Cache_Data', name): i+=1; continue
        szs=set()
        for j in range(i, min(i+LOOK, len(lines))):
            for s in sizes(lines[j]): szs.add(s)
        if szs:
            for s in sorted(szs):
                cands.append((name, int(s)))
        i+=1

# Pick top-1 by size closeness (12% tolerance)
def within(sz,tgt, tol=0.12): return tgt>0 and abs(sz-tgt)/tgt <= tol
suggest={}
for p,sz in outs:
    best=None; best_rel=1e9
    for nm,tgt in cands:
        r=abs(sz-tgt)/tgt if tgt else 1e9
        if r<best_rel:
            best_rel=r; best=(nm,tgt)
    suggest[p]=best[0] if (best and within(sz,best[1])) else ""

def summary_line(idx, path, chosen, dup_names):
    status="(missing)" if not chosen else ("(possible duplicate)" if dup_names.get(chosen,0)>1 else "")
    return f"{idx} {base(path)} -> {chosen if chosen else '(missing)'} {status}".rstrip()

def print_summary(suggest_map):
    dup={}
    for nm in suggest_map.values():
        if nm: dup[nm]=dup.get(nm,0)+1
    print()
    for i,(p,_) in enumerate(outs, start=1):
        print(summary_line(i, p, suggest_map.get(p,""), dup))
    print()

def edit_loop():
    while True:
        num=input("edit file number (ENTER to stop): ").strip()
        if num=="":
            return
        if not num.isdigit() or not (1<=int(num)<=len(outs)):
            print("  invalid number"); continue
        p,_=outs[int(num)-1]
        nm=input("new name (with extension; ENTER to clear): ").strip()
        suggest[p]=nm

# Require TTY for interaction
if not sys.stdin.isatty():
    print("[!] No interactive TTY. Aborting.")
    sys.exit(1)

# Show summary, ask Y/E/C
while True:
    print_summary(suggest)
    ans=input("confirm [Y]  edit list [E]  cancel [C]: ").strip().lower()
    if ans=="c":
        print("[i] Canceled. No files created.")
        sys.exit(0)
    if ans=="e":
        edit_loop()
        continue
    if ans=="y":
        break

# Create copies
created=0
for p,_ in outs:
    nm=suggest.get(p,"").strip()
    if not nm:
        continue
    dst=os.path.join(os.path.dirname(p), os.path.basename(nm))
    if os.path.exists(dst):
        root,ext=os.path.splitext(dst); i=1
        nd=f"{root}.guess{i}{ext}"
        while os.path.exists(nd):
            i+=1; nd=f"{root}.guess{i}{ext}"
        dst=nd
    shutil.copy2(p,dst); created+=1
    print(f"[create] {os.path.basename(p)} -> {os.path.basename(dst)}")

print(f"[✓] Done. Created {created} file(s).")
PY

# run helper with real stdin attached (interactive)
if ! python3 "$PYFILE" "$OUT" "${OCRTEXT:-}"; then
  rm -f "$PYFILE"
  exit 1
fi
rm -f "$PYFILE"

# ---------- short final summary ----------
find "$OUT" -type f -name '*_ESET.out' -printf '%p\n' | wc -l | xargs echo "out files in output:"
echo "summary: $OUT"
