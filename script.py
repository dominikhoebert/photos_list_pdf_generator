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
import shutil  # added for copying originals when no face detected

# Attempt lazy import of OpenCV; proceed without cropping if unavailable
try:
    import cv2  # type: ignore
except Exception:
    cv2 = None

try:
    import numpy as np  # Ensure numpy present for cv2 conversion
except Exception:
    np = None

# Provide a Pillow-version-safe LANCZOS / high-quality resample filter
try:
    RESAMPLE_LANCZOS = PILImage.Resampling.LANCZOS  # Pillow >= 9.1
except AttributeError:  # Older / different Pillow
    RESAMPLE_LANCZOS = getattr(PILImage, 'LANCZOS', getattr(PILImage, 'BICUBIC', getattr(PILImage, 'NEAREST', 0)))

path = "Klassenfotos"

rotation_class = {"2AHIT": 270, "2BHIT": 270, "3AHIT": 270}
remove_doubles = {"2BHIT": 1, "3AHIT": 1, "3CHIT": 1, "3DHIT": 1, "4BHIT": 1, "4CHIT": 1}

# Global toggle for face cropping
FACE_CROP_ENABLED = True
# Minimum face size relative to image height to accept (avoid false tiny detections)
MIN_FACE_REL_HEIGHT = 0.10  # 10%

# Cached cascade classifier
_HAAR_CASCADE = None

def _load_face_cascade():
    """Load (and cache) the OpenCV Haar cascade. Return classifier or None if unavailable."""
    global _HAAR_CASCADE
    if _HAAR_CASCADE is not None:
        return _HAAR_CASCADE
    if cv2 is None:
        return None
    try:
        cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        if not os.path.isfile(cascade_path):
            return None
        _HAAR_CASCADE = cv2.CascadeClassifier(cascade_path)
        if _HAAR_CASCADE.empty():
            _HAAR_CASCADE = None
        return _HAAR_CASCADE
    except Exception:
        return None


def crop_image_to_face(pil_im: PILImage.Image, target_aspect: float) -> PILImage.Image:
    """Detect the largest face and crop the image to a box with the given target_aspect (w/h).
    Returns original image if detection fails.
    Algorithm:
      1. Detect faces (largest area kept).
      2. Build a crop rectangle centered on face center with margin (scale factors) while enforcing aspect.
      3. Ensure crop fits inside image; adjust if necessary.
      4. If resulting crop would cut off too much (<= face bbox) still proceed; fallback only if detection invalid.
    """
    if not FACE_CROP_ENABLED or cv2 is None or np is None:
        return pil_im
    cascade = _load_face_cascade()
    if cascade is None:
        return pil_im

    try:
        im_rgb = pil_im.convert("RGB")
        arr = np.array(im_rgb)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        # Improve contrast slightly
        gray = cv2.equalizeHist(gray)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=5, minSize=(60, 60))
        if len(faces) == 0:
            return pil_im
        # Choose largest face by area
        x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
        img_w, img_h = pil_im.size
        # Reject too-small detections
        if h / img_h < MIN_FACE_REL_HEIGHT:
            return pil_im
        # Face center
        cx = x + w / 2.0
        cy = y + h / 2.0
        # Desired crop height with margin around face (tune factor)
        desired_face_height_ratio = 0.55  # face occupies ~55% of crop height
        crop_h = h / desired_face_height_ratio
        # Clamp crop_h to image
        crop_h = min(crop_h, img_h * 0.98)
        # Corresponding width from aspect
        crop_w = crop_h * target_aspect
        # Ensure width covers face with margin horizontally comparable to vertical margin
        min_width_for_face = w / 0.70  # face ~70% of width target
        if crop_w < min_width_for_face:
            crop_w = min_width_for_face
            crop_h = crop_w / target_aspect
        # If crop exceeds image bounds, shrink uniformly
        scale = 1.0
        if crop_w > img_w:
            scale = min(scale, img_w / crop_w)
        if crop_h > img_h:
            scale = min(scale, img_h / crop_h)
        if scale < 1.0:
            crop_w *= scale
            crop_h *= scale
        # Top-left corner centered at face center
        left = cx - crop_w / 2.0
        top = cy - crop_h / 2.0
        # Adjust to stay inside image
        if left < 0:
            left = 0
        if top < 0:
            top = 0
        if left + crop_w > img_w:
            left = img_w - crop_w
        if top + crop_h > img_h:
            top = img_h - crop_h
        # Final integers
        left_i = int(round(left))
        top_i = int(round(top))
        right_i = int(round(left + crop_w))
        bottom_i = int(round(top + crop_h))
        # Safety clamps
        left_i = max(0, min(left_i, img_w - 1))
        top_i = max(0, min(top_i, img_h - 1))
        right_i = max(left_i + 1, min(right_i, img_w))
        bottom_i = max(top_i + 1, min(bottom_i, img_h))
        # Extra validation: aspect tolerance
        final_w = right_i - left_i
        final_h = bottom_i - top_i
        if final_h == 0 or final_w == 0:
            return pil_im
        final_aspect = final_w / final_h
        if not (0.90 * target_aspect <= final_aspect <= 1.10 * target_aspect):
            # Minor adjust width to enforce aspect exactly
            target_w_exact = int(round(final_h * target_aspect))
            if target_w_exact <= img_w:
                # Center horizontally within available (clamp)
                new_left = int(max(0, min(left_i + (final_w - target_w_exact) / 2, img_w - target_w_exact)))
                left_i = new_left
                right_i = new_left + target_w_exact
        cropped = pil_im.crop((left_i, top_i, right_i, bottom_i))
        return cropped
    except Exception:
        return pil_im


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


def create_student_entry(image_path, student_name, img_width, img_height, target_dpi=110, rotation_angle=None, font_name="Helvetica",
                         save_cropped_root=None, katalog=None, base_name=None, class_folder=None, original_image_path=None):
    """Create (image_flowable, name_paragraph) pair for table cells.
    Enhancements:
      * Optional forced rotation based on class (rotation_angle in degrees, applied if provided).
      * Otherwise, auto-rotate landscape images to portrait.
      * Face detection crop to consistent aspect ratio (if enabled & face found).
      * Physically downscale image to fit (img_width,img_height) at target_dpi.
      * Keep JPEG (quality=80) to drastically lower in-memory size.
      * Use a Unicode-capable font for names.
      * NEW: Save cropped face image (pre-resize) to save_cropped_root/[class]/[katalog]_[name].jpg; if no face detected, copy original.
    img_width / img_height are in POINTS (ReportLab). Converted to pixels using target_dpi.
    """
    styles = getSampleStyleSheet()
    student_name = unicodedata.normalize('NFC', student_name)
    try:
        with PILImage.open(image_path) as im:
            # Preserve a flag to know if we cropped
            # Apply class-based rotation if specified
            if rotation_angle is not None:
                try:
                    im = im.rotate(rotation_angle, expand=True)
                except Exception as re:
                    print(f"⚠️  Rotation failed for {image_path}: {re}")
            else:
                if im.width > im.height:
                    im = im.rotate(90, expand=True)
            # Face crop step (preserve aspect of allocated cell)
            target_aspect = (img_width / img_height) if img_height else 0.75
            before_crop = im
            im_cropped = crop_image_to_face(im, target_aspect=target_aspect)
            cropped_performed = (im_cropped is not before_crop)

            # Save cropped (or original) if requested
            if save_cropped_root and base_name and class_folder:  # removed katalog requirement
                try:
                    dest_dir = os.path.join(save_cropped_root, class_folder)
                    os.makedirs(dest_dir, exist_ok=True)
                    # Sanitize base_name for filesystem: replace multiple spaces with single underscore
                    base_clean = ' '.join(base_name.split())
                    base_clean = base_clean.replace(' ', '_')
                    katalog_used = katalog if katalog else "00"
                    dest_filename = f"{katalog_used}_{base_clean}.jpg"
                    dest_path = os.path.join(dest_dir, dest_filename)
                    if cropped_performed:
                        # Save the cropped image (before resizing)
                        save_im = im_cropped
                        if save_im.mode not in ("RGB", "L"):
                            save_im = save_im.convert("RGB")
                        elif save_im.mode == "L":
                            save_im = save_im.convert("RGB")
                        save_im.save(dest_path, format='JPEG', quality=90, optimize=True, progressive=True)
                    else:
                        # Copy original file bytes (not the rotated PIL image) to keep exact original if no crop
                        src_path = original_image_path or image_path
                        try:
                            shutil.copy2(src_path, dest_path)
                        except Exception:
                            # Fallback: save current (possibly rotated) image if copy fails
                            temp_im = before_crop
                            if temp_im.mode not in ("RGB", "L"):
                                temp_im = temp_im.convert("RGB")
                            elif temp_im.mode == "L":
                                temp_im = temp_im.convert("RGB")
                            temp_im.save(dest_path, format='JPEG', quality=90, optimize=True, progressive=True)
                except Exception as se:
                    print(f"⚠️  Failed to save cropped image for {image_path}: {se}")

            # Continue with the (possibly cropped) image for PDF scaling
            im = im_cropped
            # Compute max pixel dimensions based on target DPI (points -> inches -> pixels)
            max_w_px = max(1, int(round((img_width / 72.0) * target_dpi)))
            max_h_px = max(1, int(round((img_height / 72.0) * target_dpi)))
            if im.width > max_w_px or im.height > max_h_px:
                im.thumbnail((max_w_px, max_h_px), RESAMPLE_LANCZOS)
            ratio = im.width / im.height if im.height else 1
            disp_w = img_width
            disp_h = disp_w / ratio if ratio else img_height
            if disp_h > img_height:
                disp_h = img_height
                disp_w = disp_h * ratio
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
        alignment=0,
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
    col_widths = [max_img_width+3, 45 * mm, max_img_width+3, 45 * mm]

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
                                                       rotation_angle=rotation_angle, font_name=unicode_font,
                                                       save_cropped_root="Klassenfotos_cropped", katalog=katalog,
                                                       base_name=base_name, class_folder=class_folder,
                                                       original_image_path=image_path)

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
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
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
