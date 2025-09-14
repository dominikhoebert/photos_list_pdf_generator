import os
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Image, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from PIL import Image as PILImage
import io

# Provide a Pillow-version-safe LANCZOS / high-quality resample filter
try:
    RESAMPLE_LANCZOS = PILImage.Resampling.LANCZOS  # Pillow >= 9.1
except AttributeError:  # Older / different Pillow
    RESAMPLE_LANCZOS = getattr(PILImage, 'LANCZOS', getattr(PILImage, 'BICUBIC', getattr(PILImage, 'NEAREST', 0)))

path = "Klassenfotos"

rotation_class = {"2AHIT": 270, "2BHIT": 270}


def extract_student_name(filename):
    """Extract student name from filename by removing number prefix and file extension"""
    name = os.path.splitext(filename)[0]  # Remove file extension
    # Remove number prefix (e.g., "01_", "1_", etc.)
    parts = name.split('_', 1)
    if len(parts) > 1 and parts[0].isdigit():
        return parts[1].replace('_', ' ')
    return name.replace('_', ' ')


def parse_katalognummer_and_name(filename):
    """Return (katalognummer(str or None), cleaned_name).
    katalognummer: taken from leading numeric prefix before first underscore; padded to 2 digits.
    cleaned_name: remaining parts joined with spaces, with any trailing purely numeric tokens removed (e.g., version markers like _2)."""
    stem = os.path.splitext(filename)[0]
    parts = stem.split('_')
    if not parts:
        return None, stem
    katalog = None
    remaining = parts
    if parts[0].isdigit():
        katalog = parts[0].zfill(2)
        remaining = parts[1:]
    while remaining and remaining[-1].isdigit():
        remaining = remaining[:-1]
    cleaned_name = ' '.join(remaining).strip()
    cleaned_name = ' '.join(cleaned_name.split())  # collapse any repeated whitespace
    return katalog, cleaned_name


def create_student_entry(image_path, student_name, img_width, img_height, target_dpi=110, rotation_angle=None):
    """Create (image_flowable, name_paragraph) pair for table cells.
    Enhancements:
      * Optional forced rotation based on class (rotation_angle in degrees, applied if provided).
      * Otherwise, auto-rotate landscape images to portrait.
      * Physically downscale image to fit (img_width,img_height) at target_dpi.
      * Keep JPEG (quality=80) to drastically lower in-memory size.
    img_width / img_height are in POINTS (ReportLab). Converted to pixels using target_dpi.
    """
    styles = getSampleStyleSheet()
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
        # Sort by extracted student name (ignore katalog number prefixes)
        sortable_entries = []  # (normalized_name, katalog, base_name, filename)
        for f in files:
            katalog, base_name = parse_katalognummer_and_name(f)
            normalized = base_name.casefold()
            sortable_entries.append((normalized, katalog, base_name, f))
        sortable_entries.sort(key=lambda x: x[0])

        print(f"\n🏫 Processing class: {class_folder} (students: {len(sortable_entries)})" + (
            f" | 🔄 rotation {rotation_angle}°" if rotation_angle is not None else ""))

        story.append(Paragraph(class_folder, header_style))
        story.append(Spacer(0, 4 * mm))

        table_data = []
        row = []  # Accumulate 4 cells per completed row (img, name, img, name)

        for _, katalog, base_name, filename in sortable_entries:
            image_path = os.path.join(class_path, filename)
            display_name = f"{katalog} {base_name}" if katalog else base_name
            img_flow, name_para = create_student_entry(image_path, display_name, max_img_width, max_img_height,
                                                       rotation_angle=rotation_angle)

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
