# ESET Quarantine Recovery

Recover files from **ESET Online Scanner** quarantine (`*.NQF`) on Windows, Linux, and macOS.  
Decryption ogic is implemented directly in Python. Inspired by HexAcorn DexRAY (<a href="https://hexacorn.com/d/DeXRAY.pl" target="_blank">https://hexacorn.com/d/DeXRAY.pl</a>

### Why not just restore files from the ESET GUI?
<p>Because sometimes the AV just refuses to restore them and on their forums, they ask people to send them their files to manually decrypt them.</p>

---

## Features

- **Native ESET `.NQF` decoder** in Python—no DeXRAY or Perl needed  
- **Cross-platform GUI (Tkinter)** for ease of use  
- **OCR integration (optional)** — auto-suggest filenames from quarantine screenshots  
- **Interactive file list**, editable OCR names, labels for missing/duplicates, and per-file extraction toggles  
- **Extract output into structured folders** named by quarantine hashes  

---

## Getting Started

We recommend using a virtual environment to keep dependencies clean.

### 1. Clone the repository

```bash
git clone https://github.com/sorinbotirla/eset-quarantine-recovery.git
cd eset-quarantine-recovery
```


### 2. (Optional) Set up a virtual env

```bash
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate.bat       # Windows
```

### 3. Install Python dependencies
## These are optional if you want OCR:

```bash
pip install pillow pytesseract
```

## On Linux, you may also need:
```bash
sudo apt install python3-tk tesseract-ocr
```

### 4. Run the GUI
```bash
python eset_unquarantine_gui.py
```

---

### Usage Instructions

<ul>
  <li>Select in GUI: Choose your "Quarantined files folder" containing .NQF files.</li>
  <li>Click Scan Quarantine to populate the file list.</li>
  <li>(Optional) Choose your OCR screenshot folder and Start OCR Scan to auto-suggest filenames.</li>
  <li>Edit any OCR name directly by double-clicking the cell.</li>
  <li>Choose an "Extracted files folder".</li>
  <li>Click Extract Files to decrypt and extract. Outputs are organized by hash.</li>
</ul>

---

### Troubleshooting

<ul>
  <li>OCR modules not detected: Ensure Pillow & pytesseract are installed in the same Python you run the GUI with.</li>
  <li>OCR binary missing: Confirm Tesseract is installed and accessible (tesseract --version).</li>
  <li>Tkinter errors: On Linux, you may need sudo apt install python3-tk.</li>
  <li>Permission issues: Select output folder where you have write access.</li>
  <li>OCR name truncations: Layout-specific tweaks added to help restore full names—let me know if any fail.</li>
</ul>

---

### Contributing

<p>Suggestions for OCR heuristics or UI improvements are welcome via Issues or PRs.</p>

<p>Just clone, update, and send a PR—MIT License, go wild.</p>

---

### License

<p>Distributed under the MIT License. See LICENSE.</p>

---

### Contact

<p>Created by sorinbotirla. Feel free to reach out via GitHub or wherever works best!</p>
<p>Enjoy your clean and easy ESET quarantine recovery GUI!</p>
