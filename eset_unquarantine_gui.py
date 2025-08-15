#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ESET Quarantine Recovery GUI (cross-platform)
- Pure-Python ESET .NQF decrypt (no Perl/DeXRAY needed for ESET)
- Optional OCR filename guessing from screenshots
- Keeps the exact GUI layout requested

Python deps:
  pip install pillow pytesseract
System dep:
  Tesseract OCR binary (apt-get install tesseract-ocr tesseract-ocr-eng)
"""

import os
import re
import sys
import math
import queue
import shutil
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------- OCR availability / wiring ----------------
TESS_PATH = None  # e.g. r"C:\Program Files\Tesseract-OCR\tesseract.exe" if needed on Windows

PY_OCR = False
TESS_OK = False
try:
    from PIL import Image, ImageFilter, ImageOps
    import pytesseract
    PY_OCR = True
    from shutil import which as _which
    _cmd = TESS_PATH or _which("tesseract")
    if _cmd:
        try:
            pytesseract.pytesseract.tesseract_cmd = _cmd
        except Exception:
            pass
        TESS_OK = True
except Exception:
    PY_OCR = False
    TESS_OK = False

# ---------------- Utility helpers ----------------

def human_size(n: int) -> str:
    """Robust human readable size (fixed integer-division bug)."""
    if n is None:
        return ""
    num = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(num)} B"
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{int(n)} B"

def to_bytes(size_text: str) -> Optional[int]:
    if not size_text:
        return None
    s = size_text.strip().replace(",", ".").upper()
    m = re.search(r'([\d\.]+)\s*([KMGT]?I?B)\b', s)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2)
    mult = {
        "B": 1,
        "KB": 1024,  "KIB": 1024,
        "MB": 1024**2, "MIB": 1024**2,
        "GB": 1024**3, "GIB": 1024**3,
        "TB": 1024**4, "TIB": 1024**4
    }.get(unit, None)
    if not mult:
        return None
    return int(num * mult)

def within_tolerance(actual: int, target: int) -> bool:
    if target <= 0 or actual <= 0:
        return False
    tol = 0.02 if target >= 1_000_000 else 0.03
    return abs(actual - target) / target <= tol

def safe_basename(p: str) -> str:
    return os.path.basename(p.replace("\\", "/").strip())

# ---------------- ESET decrypt ----------------

def eset_decrypt_bytes(raw: bytes) -> bytes:
    """ ((byte - 84) % 256) XOR 0xA5 """
    out = bytearray(len(raw))
    for i, b in enumerate(raw):
        out[i] = (((b - 84) & 0xFF) ^ 0xA5) & 0xFF
    return bytes(out)

def extract_eset_file(nqf_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = nqf_path.read_bytes()
    dec = eset_decrypt_bytes(data)
    out_path = out_dir / f"{nqf_path.name}.00000000_ESET.out"
    out_path.write_bytes(dec)
    return out_path

# ---------------- OCR parsing ----------------

FILE_RX = re.compile(
    r'([A-Za-z0-9_\-\(\)\[\]\.\s]+?\.(?:zip|rar|7z|exe|msi|apk|img|iso|bin|gz|bz2|xz|tar|dll|scr|php|jar|pdf|sis))',
    re.IGNORECASE
)
SIZE_RX = re.compile(r'([\d\.,]+)\s*([KMGT]?I?B)\b', re.IGNORECASE)

def preprocess_image(img):
    img = img.convert("L")
    w, h = img.size
    scale = 2 if max(w, h) < 2200 else 1.5
    img = img.resize((int(w*scale), int(h*scale)))
    from PIL import ImageOps, ImageFilter
    img = ImageOps.autocontrast(img, cutoff=1)
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=6))
    return img

def tesseract_text(img) -> str:
    if not (PY_OCR and TESS_OK):
        return ""
    texts = []
    for psm in (4, 6, 11):
        try:
            txt = pytesseract.image_to_string(
                img, lang="eng",
                config=f"--oem 1 --psm {psm} -c preserve_interword_spaces=1"
            )
            if txt:
                texts.append(txt)
        except Exception:
            pass
    return "\n".join(texts)

def parse_ocr_candidates(text: str):
    if not text:
        return []
    lines = text.splitlines()
    def size_near(i):
        for j in (i, i+1, i-1):
            if 0 <= j < len(lines):
                m = SIZE_RX.search(lines[j])
                if m:
                    return to_bytes(m.group(0))
        return None

    out = []
    for i, line in enumerate(lines):
        for m in FILE_RX.finditer(line):
            fname = safe_basename(m.group(1))
            sz = size_near(i)
            out.append((fname, sz))
    # dedupe
    seen, uniq = set(), []
    for f, s in out:
        key = (f.lower(), s)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((f, s))
    return uniq

# ---------------- Data model ----------------

from dataclasses import dataclass
@dataclass
class Row:
    idx: int
    nqf_path: Path
    size_bytes: int
    ftype: str
    ocr_name: str = ""
    ocr_size_bytes: Optional[int] = None
    label: str = "missing name"
    extract_checked: bool = True

# ---------------- GUI ----------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ESET Quarantine Recovery")

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Treeview", rowheight=24)
        style.configure("Big.TCheckbutton", font=("TkDefaultFont", 11))

        self.qdir = tk.StringVar()
        self.odir = tk.StringVar()
        self.idir = tk.StringVar()
        self.scan_images = tk.BooleanVar(value=True)

        self.rows: List[Row] = []
        self.entry_editor: Optional[tk.Entry] = None
        self.entry_row_iid: Optional[str] = None
        self.entry_col = None

        # Logs
        self.log = tk.Text(self, height=10, width=140, wrap="word")
        self.log.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=6, pady=(6,0))
        self.log.config(state="disabled")

        # Right panel
        right = ttk.Frame(self)
        right.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=(6,6), pady=(6,6))

        ttk.Label(right, text="Quarantined files folder").grid(row=0, column=0, sticky="w")
        qrow = ttk.Frame(right); qrow.grid(row=1, column=0, sticky="ew", pady=(2,8))
        ttk.Entry(qrow, textvariable=self.qdir, width=42).pack(side="left", fill="x", expand=True)
        ttk.Button(qrow, text="Browse", command=self.browse_qdir, width=8).pack(side="left", padx=(6,0))
        ttk.Button(right, text="Scan Quarantine", command=self.scan_quarantine).grid(row=2, column=0, sticky="w", pady=(2,14))

        ttk.Label(right, text="Extracted files folder").grid(row=3, column=0, sticky="w")
        orow = ttk.Frame(right); orow.grid(row=4, column=0, sticky="ew", pady=(2,14))
        ttk.Entry(orow, textvariable=self.odir, width=42).pack(side="left", fill="x", expand=True)
        ttk.Button(orow, text="Browse", command=self.browse_odir, width=8).pack(side="left", padx=(6,0))

        ttk.Label(right, text="OCR images folder (optional)").grid(row=5, column=0, sticky="w")
        irow = ttk.Frame(right); irow.grid(row=6, column=0, sticky="ew", pady=(2,0))
        ttk.Entry(irow, textvariable=self.idir, width=42).pack(side="left", fill="x", expand=True)
        ttk.Button(irow, text="Browse", command=self.browse_idir, width=8).pack(side="left", padx=(6,0))

        tip = ttk.Label(right, text="Tip: double-click the “OCR Name” cell to edit;\nclick Select/None to toggle Extract.")
        tip.grid(row=7, column=0, sticky="w", pady=(8,2))

        # Table
        cols = ("#", "Quarantine File", "Size", "Type", "OCR Name (double-click to edit)", "Labels", "OCR Size", "Extract")
        self.tv = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse", height=16)
        self.tv.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=6, pady=(6,0))

        widths = [40, 480, 100, 80, 360, 160, 100, 80]
        for c, w in zip(cols, widths):
            self.tv.heading(c, text=c)
            self.tv.column(c, width=w, anchor="w")

        # Editing / toggles
        self.tv.bind("<Double-Button-1>", self.on_double_click)
        self.tv.bind("<Return>", self.edit_selected)   # Fallback: press Enter on selected row to edit OCR Name
        self.tv.bind("<F2>", self.edit_selected)
        self.tv.bind("<Button-1>", self.on_click)
        self.tv.bind("<Configure>", lambda e: self.hide_editor())

        # Bottom left
        bottom_left = ttk.Frame(self); bottom_left.grid(row=2, column=0, sticky="w", padx=6, pady=(6,6))
        self.scan_cb = ttk.Checkbutton(bottom_left, text="scan for filenames in the images folder",
                                       variable=self.scan_images, style="Big.TCheckbutton")
        self.scan_cb.pack(side="left")
        ttk.Button(bottom_left, text="Select All", command=lambda: self.set_all_extract(True)).pack(side="left", padx=(12,4))
        ttk.Button(bottom_left, text="Select None", command=lambda: self.set_all_extract(False)).pack(side="left")

        # Bottom right
        bottom_right = ttk.Frame(self); bottom_right.grid(row=2, column=1, sticky="e", padx=6, pady=(6,6))
        self.btn_ocr = tk.Button(bottom_right, text="START OCR SCAN",
                                 command=self.start_ocr_thread, bg="#2176FF", fg="white", activebackground="#1b61cc")
        self.btn_ocr.pack(side="left", padx=(0,10), ipadx=10, ipady=3)
        self.btn_extract = tk.Button(bottom_right, text="EXTRACT FILES",
                                     command=self.start_extract_thread, bg="#2DA44E", fg="white", activebackground="#238636")
        self.btn_extract.pack(side="left", ipadx=10, ipady=3)

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Initial log
        self.append_log("[i] Ready.")
        if not PY_OCR:
            self.append_log("[ocr] pytesseract/Pillow not importable in THIS Python. Try:")
            self.append_log("     python3 -c \"import PIL, pytesseract; print('ok')\"")
            self.append_log("     If that fails: pip install pillow pytesseract")
        elif not TESS_OK:
            self.append_log("[ocr] Tesseract binary not found. Install it and ensure it's on PATH.")
            self.append_log("     Example (Debian/Ubuntu/Kali): sudo apt-get install tesseract-ocr tesseract-ocr-eng")

    # --- path pickers
    def browse_qdir(self):
        d = filedialog.askdirectory(title="Pick ESET quarantine folder")
        if d: self.qdir.set(d)

    def browse_odir(self):
        d = filedialog.askdirectory(title="Pick output (extracted) folder")
        if d: self.odir.set(d)

    def browse_idir(self):
        d = filedialog.askdirectory(title="Pick screenshots (OCR) folder")
        if d: self.idir.set(d)

    # --- logs
    def append_log(self, s: str):
        self.log.config(state="normal")
        self.log.insert("end", s + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # --- table helpers
    def set_all_extract(self, val: bool):
        for iid in self.tv.get_children(""):
            row = list(self.tv.item(iid, "values"))
            row[7] = "☑" if val else "☐"
            self.tv.item(iid, values=row)

    def rebuild_table(self):
        self.hide_editor()
        self.tv.delete(*self.tv.get_children(""))
        for r in self.rows:
            self.tv.insert("", "end", iid=str(r.idx), values=(
                r.idx,
                r.nqf_path.name,
                human_size(r.size_bytes),
                r.ftype,
                r.ocr_name,
                r.label,
                human_size(r.ocr_size_bytes) if r.ocr_size_bytes else "",
                "☑" if r.extract_checked else "☐",
            ))

    def hide_editor(self):
        if self.entry_editor is not None:
            try:
                self.entry_editor.destroy()
            except Exception:
                pass
            self.entry_editor = None
            self.entry_row_iid = None
            self.entry_col = None

    def on_click(self, event):
        # toggle extract checkbox on single click
        if self.entry_editor and event.widget == self.entry_editor:
            return
        region = self.tv.identify("region", event.x, event.y)
        if region != "cell":
            self.hide_editor()
            return
        col = self.tv.identify_column(event.x)
        row_iid = self.tv.identify_row(event.y)
        if not row_iid:
            self.hide_editor()
            return
        col_index = int(col.replace("#", "")) - 1
        if col_index == 7:
            vals = list(self.tv.item(row_iid, "values"))
            vals[7] = "☐" if vals[7] == "☑" else "☑"
            self.tv.item(row_iid, values=vals)
        else:
            # clicks elsewhere just commit/hide editor
            self.hide_editor()

    def edit_selected(self, event=None):
        sel = self.tv.selection()
        if not sel:
            return
        row_iid = sel[0]
        # column 5 (index 4)
        bbox = self.tv.bbox(row_iid, "#5")
        if not bbox:
            return
        self.start_editor(row_iid, "#5", bbox)

    def on_double_click(self, event):
        region = self.tv.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tv.identify_column(event.x)
        row_iid = self.tv.identify_row(event.y)
        if not row_iid:
            return
        if int(col.replace("#", "")) - 1 != 4:
            return
        bbox = self.tv.bbox(row_iid, col)
        if not bbox:
            return
        self.start_editor(row_iid, col, bbox)

    def start_editor(self, row_iid: str, col: str, bbox):
        x, y, w, h = bbox
        vals = list(self.tv.item(row_iid, "values"))
        current = vals[4]
        self.hide_editor()
        self.entry_editor = tk.Entry(self.tv, borderwidth=1)
        self.entry_editor.insert(0, current)
        self.entry_editor.select_range(0, "end")
        self.entry_editor.icursor("end")
        self.entry_editor.focus_set()
        self.entry_row_iid = row_iid
        self.entry_col = col
        # bindings
        self.entry_editor.bind("<Return>", self.commit_editor)
        self.entry_editor.bind("<Escape>", lambda e: self.hide_editor())
        self.entry_editor.bind("<FocusOut>", self.commit_editor)
        self.entry_editor.bind("<Control-a>", lambda e: (self.entry_editor.select_range(0, "end"), "break"))
        # place inside the Treeview to avoid window coords issues
        self.entry_editor.place(in_=self.tv, x=x, y=y, width=w, height=h)

    def commit_editor(self, event=None):
        if not self.entry_editor or not self.entry_row_iid:
            return
        new_text = self.entry_editor.get().strip()
        vals = list(self.tv.item(self.entry_row_iid, "values"))
        vals[4] = new_text
        # update label
        vals[5] = "" if new_text else "missing name"
        self.tv.item(self.entry_row_iid, values=vals)
        self.hide_editor()

    # --- scanning
    def scan_quarantine(self):
        qdir = Path(self.qdir.get().strip() or "")
        if not qdir.is_dir():
            messagebox.showerror("Error", "Pick a valid quarantine folder.")
            return
        self.append_log(f"[=] Scanning {qdir} …")
        nqfs = sorted([p for p in qdir.iterdir() if p.is_file() and p.suffix.lower() == ".nqf"],
                      key=lambda p: p.name)
        self.append_log(f"[i] Found {len(nqfs)} item(s).")
        self.rows.clear()
        for i, p in enumerate(nqfs, 1):
            try:
                size = p.stat().st_size
            except Exception:
                size = 0
            self.rows.append(Row(
                idx=i, nqf_path=p, size_bytes=size, ftype="data",
                ocr_name="", ocr_size_bytes=None, label="missing name", extract_checked=True
            ))
        self.rebuild_table()

    # --- OCR
    def start_ocr_thread(self):
        threading.Thread(target=self.run_ocr, daemon=True).start()

    def run_ocr(self):
        if not self.scan_images.get():
            self.append_log("[ocr] scan disabled.")
            return
        if not PY_OCR:
            self.append_log("[ocr] pytesseract/Pillow not importable in THIS Python.")
            return
        if not TESS_OK:
            self.append_log("[ocr] Tesseract binary not found on PATH.")
            return
        idir = Path(self.idir.get().strip() or "")
        if not idir.is_dir():
            self.append_log("[ocr] no images folder set.")
            return

        imgs = []
        for ext in ("*.png","*.jpg","*.jpeg","*.bmp","*.tif","*.tiff"):
            imgs.extend(idir.glob(ext))
        if not imgs:
            self.append_log("[ocr] no images found.")
            return

        all_text = []
        self.append_log(f"[ocr] Scanning {len(imgs)} image(s)…")
        for imgp in imgs:
            try:
                im = Image.open(imgp)
                pim = preprocess_image(im)
                txt = tesseract_text(pim)
                all_text.append(txt)
                cands = parse_ocr_candidates(txt)
                self.append_log(f"[ocr] {imgp} candidates: {len(cands)}")
            except Exception as e:
                self.append_log(f"[ocr] {imgp} error: {e}")

        text = "\n".join(all_text)
        cands = parse_ocr_candidates(text)
        self.append_log(f"[ocr] total unique candidates: {len(cands)}")

        for r in self.rows:
            best_name, best_sz, best_score = "", None, 1e9
            for fname, sz in cands:
                if not sz:
                    continue
                score = abs(r.size_bytes - sz) / max(sz, 1)
                if score < best_score:
                    best_score, best_name, best_sz = score, fname, sz
            if best_name and within_tolerance(r.size_bytes, best_sz):
                r.label = "possible duplicate" if any(
                    rr.ocr_name.lower() == best_name.lower() and rr.idx != r.idx for rr in self.rows
                ) else ""
                r.ocr_name = best_name
                r.ocr_size_bytes = best_sz
            else:
                if not r.ocr_name:
                    r.label = "missing name"
                r.ocr_size_bytes = None
        self.rebuild_table()

    # --- extraction
    def start_extract_thread(self):
        threading.Thread(target=self.run_extract, daemon=True).start()

    def run_extract(self):
        odir = Path(self.odir.get().strip() or "")
        if not odir:
            messagebox.showerror("Error", "Pick an output folder.")
            return
        odir.mkdir(parents=True, exist_ok=True)

        chosen: List[Row] = []
        for iid in self.tv.get_children(""):
            v = list(self.tv.item(iid, "values"))
            if v[7] != "☑":
                continue
            idx = int(v[0])
            r = next((x for x in self.rows if x.idx == idx), None)
            if r:
                r.ocr_name = v[4].strip()
                chosen.append(r)

        if not chosen:
            self.append_log("[*] No rows selected.")
            return

        self.append_log(f"[*] Extracting {len(chosen)} file(s)…")
        for r in chosen:
            try:
                hash_folder = odir / Path(r.nqf_path.stem)
                hash_folder.mkdir(parents=True, exist_ok=True)
                dst_nqf = hash_folder / r.nqf_path.name
                if not dst_nqf.exists():
                    shutil.copy2(r.nqf_path, dst_nqf)
                out_path = extract_eset_file(r.nqf_path, hash_folder)
                self.append_log(f"[ok] {r.nqf_path.name} -> {out_path.name}")
                if r.ocr_name:
                    guess_path = hash_folder / r.ocr_name
                    if not guess_path.exists():
                        shutil.copy2(out_path, guess_path)
                        self.append_log(f"[copy] -> {guess_path.name}")
                    else:
                        self.append_log(f"[skip] exists -> {guess_path.name}")
            except Exception as e:
                self.append_log(f"[err] {r.nqf_path.name}: {e}")
        self.append_log("[✓] Done.")

# ---------------- Main ----------------
if __name__ == "__main__":
    app = App()
    app.minsize(1200, 520)
    app.mainloop()
