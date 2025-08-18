# ESET Quarantine Recovery

Recover files from **ESET Online Scanner** quarantine (`*.NQF`) on Windows, Linux, and macOS.  
Decryption logic is implemented directly in Python. Inspired by HexAcorn DexRAY (<a href="https://hexacorn.com/d/DeXRAY.pl" target="_blank">https://hexacorn.com/d/DeXRAY.pl</a>

### Why not just restore files from the ESET GUI?
<table>
  <td width="50%">
    <img src="https://raw.githubusercontent.com/sorinbotirla/eset-quarantine-recovery/refs/heads/main/images/cannotrestore.JPG" width='100%' />
  </td>
  <td width="50%">
    <p>Because sometimes the AV just refuses to restore the quarantined files and, on the ESET forums, they ask people to send their files to manually decrypt them. (<a href="https://forum.eset.com/topic/37532-eset-online-scanner-failed-to-restore-files-from-quarantinne/" target="_blank">Example of ESET forum post</a></p>
    <p>Also, when you restore a file from the quarantine, the AV tries to "clean" it, therefore you can get an archive stripped down.</p>
  </td>
</table>



---

## Features

- **Native ESET `.NQF` decoder** in Python
- **Cross-platform GUI (Tkinter)** for ease of use  
- **OCR integration (optional)** — auto-suggest filenames from quarantine screenshots  
- **Interactive file list**, editable OCR names, labels for missing/duplicates, and per-file extraction toggles  
- **Extract output into structured folders** named by quarantine hashes  

---

## Getting Started

I recommend using a virtual environment to keep dependencies clean.

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

If you get the "managed environment" error, you can skip it by adding --break-system-packages at the end of the pip install command

## On Linux (my testing distro was Debian based, update the equivalent for your distro), you may also need:
```bash
sudo apt install python3-tk tesseract-ocr
```

## On Windows you may also need:
The last version of the Tesseract OCR <a href="https://digi.bib.uni-mannheim.de/tesseract/">here</a>

### 4. Run the GUI
```bash
python eset_unquarantine_gui.py
```

---
<img src="https://raw.githubusercontent.com/sorinbotirla/eset-quarantine-recovery/refs/heads/main/images/gui.png" width='100%' />

### Usage Instructions

<ul>
  <li>Select in GUI: Choose your "Quarantined files folder" containing .NQF files.</li>
  <li>Click Scan Quarantine to populate the file list.
  <img src="https://raw.githubusercontent.com/sorinbotirla/eset-quarantine-recovery/refs/heads/main/images/quarantinescan.png" width='100%' />
  </li>
  <li>Choose an "Extracted files folder".</li>
  <li>(Optional) Choose your OCR screenshot folder and Start OCR Scan to auto-suggest filenames.
  <img src="https://raw.githubusercontent.com/sorinbotirla/eset-quarantine-recovery/refs/heads/main/images/ocrscan.png" width='100%' />
  </li>
  <li>Edit any OCR name directly by double-clicking the cell. Press enter to accept the input value
  <img src="https://raw.githubusercontent.com/sorinbotirla/eset-quarantine-recovery/refs/heads/main/images/ocrnameedit.png" width='100%' />
  </li>
  <li>Click Extract Files to decrypt and extract. Outputs are organized by hash.
  <img src="https://raw.githubusercontent.com/sorinbotirla/eset-quarantine-recovery/refs/heads/main/images/extractingfiles.png" width='100%' />
  </li>
</ul>

### Why OCR?

<p>I have used OCR to read the file names and their size from the ESET quarantine screenshots. The quarantined files are stored without their original names, so the only almost-reliable way to keep tracking of the original file names was to check their size. To do that, simply screenshot the quarantine list but keep the screenshots cropped to the last part of the path (file names and their size).</p>

#### Do not take screenshots of the entire quarantine window
<img src="https://raw.githubusercontent.com/sorinbotirla/eset-quarantine-recovery/refs/heads/main/images/1.JPG" width='100%' />

#### Take screenshots only on the file names and their size
<img src="https://raw.githubusercontent.com/sorinbotirla/eset-quarantine-recovery/refs/heads/main/images/1crop.jpg" width='100%' />

---

### Quarantined files (NQF) and the recovered files

<p>You can find the ESET Online Scanner's quarantined files under</p>

```bash
C:\Users\<YourUsername>\AppData\Local\ESET\ESETOnlineScanner\Quarantine
```

<p>Copy the files from the quarantine folder to another folder for convenience. You will use that folder as a source for extraction. </p>

<table>
  <td width="50%">
    <img src="https://raw.githubusercontent.com/sorinbotirla/eset-quarantine-recovery/refs/heads/main/images/quarantinefiles.png" width='100%' />
  </td>
  <td width="50%">
    <img src="https://raw.githubusercontent.com/sorinbotirla/eset-quarantine-recovery/refs/heads/main/images/recoveredfile.png" width='100%' />
  </td>
</table>

---

### Troubleshooting

<ul>
  <li>OCR modules not detected: Ensure Pillow & pytesseract are installed in the same Python you run the GUI with.</li>
  <li>OCR binary missing: Confirm Tesseract is installed and accessible (tesseract --version).</li>
  <li>Tkinter errors: On Linux, you may need sudo apt install python3-tk.</li>
  <li>Permission issues: Select output folder where you have write access.</li>
  <li>OCR name truncations: Try to take clean screenshots, only capturing the file names and their size.</li>
</ul>

---

### License

<p>Distributed under the MIT License. See <a href="https://raw.githubusercontent.com/sorinbotirla/eset-quarantine-recovery/refs/heads/main/LICENSE">LICENSE</a>.</p>

---

### Extras

<p>There is a cli version which doesn't work as well as the GUI script, and also a dexray.sh bash script that downloads and uses DexRAY.pl from HexAcorn website.</p>

---

### Final Notice

<p>Do not rely 100% on the OCR to match the file names. Check yourself if they are the right ones. Use this tool to carefully restore false positives and stay away from malware.</p>

