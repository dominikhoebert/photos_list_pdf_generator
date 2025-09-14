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

## Installation
Use Python 3.10+ (earlier versions may work but are untested).

```
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShell
# source .venv/bin/activate    # Linux / macOS
pip install --upgrade pip
pip install -r requirements.txt
```

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
- Image sizing: adjust `max_img_width` and `max_img_height` (points). Current values:
  ```python
  max_img_width = 30 * mm
  max_img_height = 40 * mm
  ```
- Compression quality: inside `create_student_entry()` edit `im.save(... quality=80 ...)`
- Target DPI for scaling: parameter `target_dpi=110` in `create_student_entry`

## How Name Extraction Works
1. Strip file extension
2. Split on first underscore `_`
3. If the left part is entirely digits, drop it
4. Replace remaining underscores with spaces

Edge case example: `07_Goonawardana_Vienna_2.jpg` → `Goonawardana Vienna 2` (the trailing `_2` remains as part of the visible name).

## Table Layout
Each row represents up to two students: `[Image | Name | Image | Name]`. Odd leftover student rows are padded with blank cells.

## Logging Output Sample
```
🚀 Starting PDF generation...
📁 Found 5 class folders. 🖼️ Total images: 142
🏫 Processing class: 2AHIT (students: 26) | 🔄 rotation 270°
  ✅ [  1/142]  0.7% -> Abdel-Latif Zainab
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

## Performance Tips
- Keep original images ≤ 1500px on longest side for faster processing
- Batch rename with tools (PowerShell, `rename`, or a Python helper) to maintain consistent numbering
- Remove unused / duplicate images—every file is processed

## Extending the Script (Ideas)
- CLI arguments via `argparse` (e.g. `--input`, `--output`, `--rotate 2AHIT=270`)
- Embed a table of contents listing all classes
- Add page headers/footers (date stamp, school logo)
- Support CSV roster import to detect missing photos
- Highlight missing images or duplicates visually

## Roadmap
Planned (not yet implemented):
- Optional sorting by last name when filenames contain multi-part names
- Automatic EXIF orientation handling (instead of heuristic)
- Parallel image preprocessing for speed on multi-core systems

## Privacy & Data
If these are real student photos, ensure compliance with local privacy regulations before distribution or version control. Consider .gitignore for the `Klassenfotos/` directory in public repositories.

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

