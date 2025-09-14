import os
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Image, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from PIL import Image as PILImage
import io
import unicodedata
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Provide a Pillow-version-safe LANCZOS / high-quality resample filter
try:
    RESAMPLE_LANCZOS = PILImage.Resampling.LANCZOS  # Pillow >= 9.1
except AttributeError:  # Older / different Pillow
    RESAMPLE_LANCZOS = getattr(PILImage, 'LANCZOS', getattr(PILImage, 'BICUBIC', getattr(PILImage, 'NEAREST', 0)))

path = "Klassenfotos"

rotation_class = {"2AHIT": 270, "2BHIT": 270, "3AHIT": 270, "4DHIT": 270}
remove_doubles = {"2BHIT": 1, "3AHIT": 1, "3CHIT": 1, "3DHIT": 1, "4BHIT": 1, "4CHIT": 1}

def extract_student_name(filename):
    """Extract student name from filename by removing number prefix and file extension"""
    name = os.path.splitext(filename)[0]  # Remove file extension
    # Remove number prefix (e.g., "01_", "1_", etc.)
    parts = name.split('_', 1)
    if len(parts) > 1 and parts[0].isdigit():
        return parts[1].replace('_', ' ')
    return name.replace('_', ' ')


def ensure_unicode_font():
    """Register and return a Unicode-capable font name.
    Tries common system fonts (Windows Arial) then falls back to DejaVu if user supplies it.
    If registration fails, returns a base font (may not render extended characters)."""
    candidates = [
        ("ArialUnicode", r"C:\\Windows\\Fonts\\arial.ttf"),  # Windows Arial normal
        ("Arial", r"C:\\Windows\\Fonts\\arial.ttf"),
        ("DejaVuSans", "DejaVuSans.ttf"),  # Allow user to drop into project dir
        ("NotoSans", "NotoSans-Regular.ttf"),
    ]
    for font_name, path in candidates:
        if os.path.isfile(path):
            try:
                if font_name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(font_name, path))
                return font_name
            except Exception as e:
                print(f"⚠️  Font register failed for {path}: {e}")
    print("⚠️  No Unicode TTF font registered; extended characters may not display.")
    return "Helvetica"  # fallback

def parse_katalognummer_and_name(filename):
    """Return (katalognummer(str or None), cleaned_name).
    katalognummer: taken from leading numeric prefix before first underscore; padded to 2 digits.
    cleaned_name: remaining parts joined with spaces, with any trailing purely numeric tokens removed (e.g., version markers like _2).
    Applies NFC normalization so composed characters (e.g. 'Ö', 'ć') display properly in PDF fonts."""
    stem = os.path.splitext(filename)[0]
    parts = stem.split('_')
    if not parts:
        return None, unicodedata.normalize('NFC', stem)
    katalog = None
    remaining = parts
    if parts[0].isdigit():
        katalog = parts[0].zfill(2)
        remaining = parts[1:]
    while remaining and remaining[-1].isdigit():
        remaining = remaining[:-1]
    cleaned_name = ' '.join(remaining).strip()
    cleaned_name = ' '.join(cleaned_name.split())  # collapse spaces
    cleaned_name = unicodedata.normalize('NFC', cleaned_name)
    return katalog, cleaned_name


def create_student_entry(image_path, student_name, img_width, img_height, target_dpi=110, rotation_angle=None, font_name="Helvetica"):
    """Create (image_flowable, name_paragraph) pair for table cells.
    Enhancements:
      * Optional forced rotation based on class (rotation_angle in degrees, applied if provided).
      * Otherwise, auto-rotate landscape images to portrait.
      * Physically downscale image to fit (img_width,img_height) at target_dpi.
      * Keep JPEG (quality=80) to drastically lower in-memory size.
      * Use a Unicode-capable font for names.
    img_width / img_height are in POINTS (ReportLab). Converted to pixels using target_dpi.
    """
    styles = getSampleStyleSheet()
    # Normalize display name to NFC to avoid combining mark issues (e.g. O8\u0308)
    student_name = unicodedata.normalize('NFC', student_name)
    try:
        with PILImage.open(image_path) as im:
            # Apply class-based rotation if specified
            if rotation_angle is not None:
                try:
                    im = im.rotate(rotation_angle, expand=True)
                except Exception as re:
                    print(f"⚠️  Rotation failed for {image_path}: {re}")
            else:
                # Fallback heuristic rotate landscape images
                if im.width > im.height:
                    im = im.rotate(90, expand=True)

            # Compute max pixel dimensions based on target DPI (points -> inches -> pixels)
            max_w_px = max(1, int(round((img_width / 72.0) * target_dpi)))
            max_h_px = max(1, int(round((img_height / 72.0) * target_dpi)))

            # Downscale preserving aspect ratio
            if im.width > max_w_px or im.height > max_h_px:
                im.thumbnail((max_w_px, max_h_px), RESAMPLE_LANCZOS)

            # Calculate display size in points while preserving aspect ratio within bounding box
            ratio = im.width / im.height if im.height else 1
            disp_w = img_width
            disp_h = disp_w / ratio if ratio else img_height
            if disp_h > img_height:
                disp_h = img_height
                disp_w = disp_h * ratio

            # Ensure RGB for JPEG
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            elif im.mode == "L":
                im = im.convert("RGB")

            buf = io.BytesIO()
            im.save(buf, format='JPEG', quality=80, optimize=True, progressive=True)
            buf.seek(0)
            img = Image(buf, width=disp_w, height=disp_h)

    except Exception as e:
        print(f"⚠️  Error loading image: {image_path} -> {e}")
        img = Paragraph("(kein Bild)", getSampleStyleSheet()['Normal'])

    name_style = ParagraphStyle(
        'StudentName',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=8,
        leading=10,
        alignment=0,  # Left
        spaceAfter=2,
    )
    name_para = Paragraph(student_name, name_style)
    return img, name_para


def create_pdf():
    """Main function to create the PDF with two columns (image+name pairs)."""
    output_filename = "student_photos_list.pdf"
    print("🚀 Starting PDF generation...")
    # Register Unicode font once
    unicode_font = ensure_unicode_font()
    doc = SimpleDocTemplate(output_filename, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm, leftMargin=15 * mm,
                            rightMargin=15 * mm)

    # Get all class folders
    if not os.path.isdir(path):
        print(f"❌ Base path not found: {path}")
        return

    class_folders = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]
    class_folders.sort()  # Sort alphabetically

    # Count total images first for progress reporting
    valid_ext = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'}
    total_images = 0
    class_image_counts = {}
    for cf in class_folders:
        cpath = os.path.join(path, cf)
        imgs = [f for f in os.listdir(cpath) if os.path.splitext(f)[1] in valid_ext]
        class_image_counts[cf] = len(imgs)
        total_images += len(imgs)

    print(f"📁 Found {len(class_folders)} class folders. 🖼️ Total images: {total_images}")

    story = []
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle(
        'ClassHeader',
        parent=styles['Heading2'],
        fontName=unicode_font,
        fontSize=16,
        spaceAfter=6,
        spaceBefore=12,
        alignment=0,
    )

    # Constants (points) for image sizing
    max_img_width = 30 * mm
    max_img_height = 40 * mm

    # Table column widths: [img, name, img, name]
    col_widths = [max_img_width, 45 * mm, max_img_width, 45 * mm]

    processed = 0

    for class_folder in class_folders:
        class_path = os.path.join(path, class_folder)
        rotation_angle = rotation_class.get(class_folder)  # Fetch rotation if defined

        # Gather image files
        files = [f for f in os.listdir(class_path) if os.path.splitext(f)[1] in valid_ext]
        if not files:
            print(f"ℹ️  Skipping empty class folder: {class_folder}")
            continue

        # --- Duplicate handling ---
        # We consider files duplicates if katalog + cleaned base name (version number removed) match.
        # Version suffix can be provided either as an underscore + digits (e.g., Name_2) or a space + digits (e.g., Name 2).
        # For classes listed in remove_doubles with value==1 keep the variant that has the HIGHEST numeric version suffix.
        grouped = {}
        for f in files:
            katalog, base_name = parse_katalognummer_and_name(f)
            key_katalog = katalog  # may be None
            stem = os.path.splitext(f)[0]

            # Detect underscore-based version suffix from original stem tokens (already partially handled by parse)
            tokens_us = stem.split('_')
            last_token_us = tokens_us[-1] if tokens_us else ''
            underscore_numeric = last_token_us.isdigit()
            underscore_version_num = int(last_token_us) if underscore_numeric else None

            has_version_suffix = underscore_numeric
            version_num = underscore_version_num

            # If no underscore version detected, attempt space-based version suffix on the (possibly version-including) base_name
            if not has_version_suffix:
                space_parts = base_name.split()
                if len(space_parts) > 1 and space_parts[-1].isdigit():
                    version_num = int(space_parts[-1])
                    has_version_suffix = True
                    # Remove trailing numeric token for grouping/display
                    base_name = ' '.join(space_parts[:-1]).strip()

            # Grouping key uses katalog + casefold of base_name without trailing version number
            grouping_key = (key_katalog, base_name.casefold())
            grouped.setdefault(grouping_key, []).append({
                'filename': f,
                'katalog': katalog,
                'base_name': base_name,  # version-stripped for display
                'normalized': base_name.casefold(),
                'has_version_suffix': has_version_suffix,
                'version_num': version_num,
                'stem': stem,
            })

        deduped_records = []
        removed_count = 0
        for key, variants in grouped.items():
            if len(variants) == 1:
                deduped_records.append(variants[0])
                continue
            strategy = remove_doubles.get(class_folder)
            chosen = None
            if strategy == 1:
                # Prefer highest numeric version (space or underscore based)
                with_version = [v for v in variants if v['has_version_suffix'] and v['version_num'] is not None]
                if with_version:
                    chosen = max(with_version, key=lambda v: v['version_num'])
                else:
                    chosen = sorted(variants, key=lambda v: v['filename'])[0]
            else:
                chosen = sorted(variants, key=lambda v: v['filename'])[0]
            for v in variants:
                if v is not chosen:
                    removed_count += 1
                    print(f"   🗑️  Duplicate removed in {class_folder}: {v['filename']} (kept {chosen['filename']})")
            deduped_records.append(chosen)
        if removed_count:
            print(f"   ➖ Duplicates filtered: {removed_count} removed in {class_folder}")

        # Build sortable entries from deduped records
        sortable_entries = []  # (normalized_name, katalog, base_name, filename)
        for rec in deduped_records:
            sortable_entries.append((rec['normalized'], rec['katalog'], rec['base_name'], rec['filename']))

        # Sort primarily by katalognummer (numeric ascending) where present; entries without katalog go after, sorted by name
        def _sort_key(entry):
            normalized, katalog, base_name, filename = entry
            if katalog is not None:
                try:
                    return (0, int(katalog), normalized)
                except ValueError:
                    return (0, 9999, normalized)
            return (1, normalized)
        sortable_entries.sort(key=_sort_key)

        print(f"\n🏫 Processing class: {class_folder} (students: {len(sortable_entries)})" + (
            f" | 🔄 rotation {rotation_angle}°" if rotation_angle is not None else ""))

        story.append(Paragraph(class_folder, header_style))
        story.append(Spacer(0, 4 * mm))

        table_data = []
        row = []  # Accumulate 4 cells per completed row (img, name, img, name)

        for _, katalog, base_name, filename in sortable_entries:
            image_path = os.path.join(class_path, filename)
            display_name = f"{katalog} {base_name}" if katalog else base_name
            display_name = unicodedata.normalize('NFC', display_name)
            img_flow, name_para = create_student_entry(image_path, display_name, max_img_width, max_img_height,
                                                       rotation_angle=rotation_angle, font_name=unicode_font)

            # Append two cells (image then name)
            row.extend([img_flow, name_para])

            processed += 1
            if total_images:
                pct = (processed / total_images) * 100
            else:
                pct = 100.0
            print(f"  ✅ [{processed}/{total_images}] {pct:5.1f}% -> {display_name}")

            if len(row) == 4:  # Completed one row (two students)
                table_data.append(row)
                row = []

        # If leftover (odd number of students), pad remaining cells
        if row:
            # Pad missing cells to complete row
            while len(row) < 4:
                row.append(Paragraph("", styles['Normal']))
            table_data.append(row)

        # Build table
        table = Table(table_data, colWidths=col_widths, hAlign='LEFT')
        table_style = TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ('BOX', (0, 0), (-1, -1), 0.25, colors.grey),
        ])
        table.setStyle(table_style)
        story.append(table)
        story.append(PageBreak())
        print(f"📦 Finished class: {class_folder}")

    # Remove last page break if present
    if story and isinstance(story[-1], PageBreak):
        story.pop()

    print(f"💾 Building PDF file: {output_filename} ...")
    doc.build(story)
    print(f"🎉 Done! PDF created: {output_filename} (classes: {len(class_folders)}, images processed: {processed})")


if __name__ == "__main__":
    create_pdf()
