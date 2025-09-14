# Student Class Photo PDF Generator

Generate a neatly formatted PDF contact sheet of student photos grouped by class folders. The script scans subfolders inside `Klassenfotos/`, extracts student names from file names, optionally rotates images per class, rescales & compresses them, and lays them out two per row (image + name) across pages.

## Key Features
- Auto-discovers class folders under `Klassenfotos/`
- Supports common image formats: JPG/JPEG/PNG (case-insensitive)
- Name extraction from filename pattern: `<number>_<First>_<Last>.jpg`
- Optional forced rotation per class (configured in code)
- Automatic portrait correction for landscape images
- Downscales images to a target box (30mm x 40mm) to keep PDF size small
- Efficient in‑memory JPEG recompression (quality=80, progressive)
- Progress logging with counts & percentages
- Graceful handling of missing/invalid images (displays placeholder text)
- Optional face detection + smart crop (OpenCV Haar cascade) for more uniform head framing
- Duplicate version handling (keeps highest numbered variant for selected classes)
- Automatic Unicode-capable font registration (accents, umlauts, etc.)

## Project Structure (excerpt)
```
Klassenfotos/
  1AHIT/
    01_Muster_Max.jpg
    02_Example_Anna.jpg
  2AHIT/
    1_Abdel-Latif_Zainab.JPG
script.py
requirements.txt
student_photos_list.pdf (output after running)
```

## Filename Convention
Expected (recommended) pattern:
```
<number>_<FirstName>_<LastName>[ _OptionalParts].<ext>
```
Examples:
- `01_Smith_John.jpg` → "Smith John"
- `3_Bachinger_Florian.JPG` → "Bachinger Florian"
If no numeric prefix is present, the full (underscore‑separated) filename (without extension) becomes the displayed name.

### Katalognummer + Name Parsing
Files with a leading numeric token become `katalognummer name` in the PDF. Trailing purely numeric tokens (used for versioning like `_2`) are removed from the display name. Example: `05_Ernst_Sonja_2.jpg` → `05 Ernst Sonja` (version `2` retained only internally for duplicate resolution).

## Installation
Use Python 3.10+ (earlier versions may work but are untested).

Standard install (includes optional OpenCV for face cropping):
```
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShell
# source .venv/bin/activate    # Linux / macOS
pip install --upgrade pip
pip install -r requirements.txt
```
Minimal install (skip face cropping to avoid OpenCV): remove the `opencv-python-headless` line from `requirements.txt` before installing, then set `FACE_CROP_ENABLED = False` in `script.py`.

## Usage
Place your class folders and images inside `Klassenfotos/` (same directory as `script.py`). Then run:
```
python script.py
```
Output: `student_photos_list.pdf` in the project root.

### Command-Line Arguments
Currently there are no CLI flags; adjust behavior by editing constants inside `script.py` (see Customization below). If you need CLI options (e.g. output file name or DPI), see Roadmap.

## Customization
Edit `script.py`:
- Base folder: change `path = "Klassenfotos"`
- Output filename: modify `output_filename` inside `create_pdf()`
- Per-class forced rotation: extend the `rotation_class` dict
  ```python
  rotation_class = {"2AHIT": 270, "2BHIT": 270, "MyClass": 90}
  ```
- Duplicate strategy classes: adjust `remove_doubles` dict (value `1` = keep highest version suffix)
  ```python
  remove_doubles = {"2BHIT": 1, "3AHIT": 1}
  ```
- Face cropping: toggle `FACE_CROP_ENABLED = True/False`; tune `MIN_FACE_REL_HEIGHT`
- Image sizing: adjust `max_img_width` and `max_img_height` (points) inside `create_pdf()`
  ```python
  max_img_width = 30 * mm
  max_img_height = 40 * mm
  ```
- Compression quality: inside `create_student_entry()` edit `im.save(... quality=80 ...)`
- Target DPI for scaling: parameter `target_dpi=110` in `create_student_entry`
- Accepted font: drop a `DejaVuSans.ttf` or `NotoSans-Regular.ttf` next to the script if system Arial is insufficient

## Duplicate & Version Handling
When a class is listed in `remove_doubles` with value `1`, files that share the same logical identity (same katalognummer + normalized base name) but differ by a numeric version suffix are deduplicated.

Version suffix patterns recognized:
- Underscore form: `Name_2.jpg`
- Space form (after parsing): `Name 2.jpg`

The script keeps the variant with the highest numeric suffix; if none have a suffix it keeps the lexicographically first filename. Removed duplicates are logged (trash can icon) for transparency.

## Face Cropping (Optional)
If OpenCV (`opencv-python-headless`) and `numpy` are installed and `FACE_CROP_ENABLED = True`:
- A Haar cascade (`haarcascade_frontalface_default.xml`) locates faces.
- The largest detected face defines a centered crop with a consistent aspect ratio, improving visual alignment.
- Very small detections (<10% image height) are ignored to avoid false positives.
- If anything fails (no OpenCV, cascade missing, detection error) the original image is used.

Disable by either uninstalling OpenCV or setting `FACE_CROP_ENABLED = False`.

## Unicode Fonts
`ensure_unicode_font()` tries to register (in order): Arial (Windows), DejaVuSans, NotoSans. Drop one of these `.ttf` files beside `script.py` if special characters (e.g., `Ö`, `Ś`, `ğ`) don't render. Falls back to `Helvetica` with limited glyph coverage.

## How Name Extraction Works
1. Strip file extension
2. Split on first underscore `_`
3. If the left part is entirely digits, drop it (katalognummer is still used for ordering)
4. Replace remaining underscores with spaces
5. Remove trailing pure numeric version token from display name

Edge case example: `07_Goonawardana_Vienna_2.jpg` → `07 Goonawardana Vienna` (the `_2` influences duplicate logic only).

## Table Layout
Each row represents up to two students: `[Image | Name | Image | Name]`. Odd leftover student rows are padded with blank cells.

## Logging Output Sample
```
🚀 Starting PDF generation...
📁 Found 5 class folders. 🖼️ Total images: 142
🏫 Processing class: 2AHIT (students: 26) | 🔄 rotation 270°
  ✅ [  1/142]  0.7% -> 01 Abdel-Latif Zainab
   🗑️  Duplicate removed in 2BHIT: 05_Ernst_Sonja.jpg (kept 05_Ernst_Sonja_2.jpg)
  ...
💾 Building PDF file: student_photos_list.pdf ...
🎉 Done! PDF created: student_photos_list.pdf (classes: 5, images processed: 142)
```

## Troubleshooting
| Issue | Cause | Fix |
|-------|-------|-----|
| "❌ Base path not found" | `Klassenfotos/` missing or misnamed | Create folder or update `path` variable |
| Image appears sideways | Class not in `rotation_class` or EXIF ignored | Add class to `rotation_class` or manually rotate original |
| Names look wrong | Unexpected filename format | Rename files to match `<number>_First_Last.ext` |
| Memory usage high | Very large source images | Pre‑resize originals or lower `target_dpi` / `quality` |
| PDF too large | Compression settings conservative | Lower `quality` (e.g. 70) or reduce dimensions |
| No face cropping | OpenCV not installed / disabled | Install deps or set `FACE_CROP_ENABLED = True` |
| Missing accents | Font not registered | Add `DejaVuSans.ttf` / `NotoSans-Regular.ttf` to project |

## Performance Tips
- Keep original images ≤ 1500px on longest side for faster processing
- Batch rename with tools (PowerShell, `rename`, or a Python helper) to maintain consistent numbering
- Remove unused / duplicate images—every file is processed
- Disable face cropping if speed is critical on very large sets

## Extending the Script (Ideas)
- CLI arguments via `argparse` (e.g. `--input`, `--output`, `--rotate 2AHIT=270`)
- Embed a table of contents listing all classes
- Add page headers/footers (date stamp, school logo)
- Support CSV roster import to detect missing photos
- Highlight missing images or duplicates visually
- Asynchronous / parallel preprocessing for multi-core speedup

## Roadmap
Planned (not yet implemented):
- Optional sorting by last name when filenames contain multi-part names
- Automatic EXIF orientation handling (instead of heuristic rotate for landscape)
- Parallel image preprocessing for speed on multi-core systems
- CLI interface for configuration

## Privacy & Data
If these are real student photos, ensure compliance with local privacy regulations before distribution or version control. Consider `.gitignore` for the `Klassenfotos/` directory in public repositories.

## Contributing
1. Fork / create feature branch
2. Make a small, focused change
3. Run the script to ensure PDF generation still works
4. Open a pull request describing the change & rationale

## License
Add your preferred license (e.g., MIT) here.

## Quick Start (All-in-One)
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python script.py
start student_photos_list.pdf   # Windows only; use 'open' on macOS
```

## Support
Issues & feature requests: open an issue or extend the script as needed.

Enjoy creating clean class photo overviews! 🎓
