# extract_trademarks.py
# ─────────────────────────────────────────────────────────────
# Full trademark record extraction from a PDF journal:
#
#   PDF page -> YOLO field detection -> group detections into one record
#   per filing (serial_number boxes anchor each filing; every other box -
#   including MULTIPLE logo boxes for one composite mark - is assigned by
#   vertical position alone, never by class, so N logo boxes in one
#   filing's band all end up under the same record) -> pull the REAL
#   embedded PDF text for each field via pdfplumber (this PDF has a
#   genuine text layer, so no OCR / no recognition errors) -> crop + embed
#   each logo -> one `trademarks` row (master) + one `trademark_logos` row
#   per logo (children, same trademark_id).
#
# DRY RUN BY DEFAULT: saves a JSON preview so you can check the extracted
# data before anything touches the database. Pass --commit to actually
# insert.
#
# Usage:
#   python extract_trademarks.py --pdf index.cfm.pdf --start_page 4 --max_pages 5
#   python extract_trademarks.py --pdf index.cfm.pdf --start_page 4 --max_pages 5 --commit
# ─────────────────────────────────────────────────────────────

import os
import re
import io
import json
import argparse

import numpy as np
import cv2
import pdfplumber
from PIL import Image
from ultralytics import YOLO

# Must match the model this script is pointed at (models/best_colab2.pt by
# default - the 9-class-v2 scheme). Same note as test_model.py/pre_label.py:
# this list has to match whatever model --model actually loads.
CLASS_NAMES = [
    "logo",
    "serial_number",
    "description",
    "agent",
    "applicant",
    "class",
    "date",
    "international_registration_date",
    "international_registration_number",
]


def merge_overlapping_boxes(boxes):
    """Collapses boxes whose y-ranges overlap into one (via their union
    bbox) - the model sometimes draws 2-3 near-duplicate overlapping boxes
    for the same physical field, which would otherwise get their text
    extracted and concatenated once per box, tripling it. Genuinely
    separate, non-overlapping boxes (e.g. a field that legitimately spans
    two stacked lines) are left as-is and still get joined afterwards."""
    if not boxes:
        return []
    boxes_sorted = sorted(boxes, key=lambda d: d["xyxy"][1])
    merged = [dict(boxes_sorted[0])]
    for d in boxes_sorted[1:]:
        last = merged[-1]
        if d["xyxy"][1] <= last["xyxy"][3]:  # y-ranges overlap
            merged[-1] = {
                "class_name": last["class_name"],
                "xyxy": [
                    min(last["xyxy"][0], d["xyxy"][0]),
                    min(last["xyxy"][1], d["xyxy"][1]),
                    max(last["xyxy"][2], d["xyxy"][2]),
                    max(last["xyxy"][3], d["xyxy"][3]),
                ],
                "conf": max(last["conf"], d["conf"]),
            }
        else:
            merged.append(dict(d))
    return merged


def group_detections_into_records(detections):
    """Groups one page's flat detection list into one record per filing.

    serial_number boxes anchor each filing (exactly one per filing); every
    other box is assigned purely by vertical position, never by class - so
    multiple logo boxes belonging to one composite mark end up in the same
    record the same way multiple fields do. Near-duplicate overlapping
    anchors (two serial_number boxes for the same filing) are merged first,
    so they don't split one filing into a real record plus an empty one."""
    raw_anchors = [d for d in detections if d["class_name"] == "serial_number"]
    anchors = merge_overlapping_boxes(raw_anchors)
    if not anchors:
        return []

    records = []
    for i, anchor in enumerate(anchors):
        band_top = anchor["xyxy"][1]
        band_bottom = anchors[i + 1]["xyxy"][1] if i + 1 < len(anchors) else float("inf")
        record = {"serial_number_box": anchor, "fields": {}, "logo_boxes": []}

        for d in detections:
            if d["class_name"] == "serial_number":
                continue  # anchors themselves, never a field
            y_center = (d["xyxy"][1] + d["xyxy"][3]) / 2
            if band_top <= y_center < band_bottom:
                if d["class_name"] == "logo":
                    record["logo_boxes"].append(d)
                else:
                    record["fields"].setdefault(d["class_name"], []).append(d)

        # Merge overlapping duplicates within each field before text extraction.
        for class_name, boxes in record["fields"].items():
            record["fields"][class_name] = merge_overlapping_boxes(boxes)

        records.append(record)
    return records


def pixel_box_to_points(xyxy, dpi):
    scale = dpi / 72.0
    x1, y1, x2, y2 = xyxy
    return (x1 / scale, y1 / scale, x2 / scale, y2 / scale)


def extract_text_for_boxes(page, boxes, dpi, pad=2.0):
    """Pulls the real embedded PDF text under a list of boxes (top to
    bottom), via pdfplumber - no OCR, so no recognition errors."""
    texts = []
    for box in sorted(boxes, key=lambda d: d["xyxy"][1]):
        x0, top, x1, bottom = pixel_box_to_points(box["xyxy"], dpi)
        x0 = max(0, x0 - pad)
        top = max(0, top - pad)
        x1 = min(page.width, x1 + pad)
        bottom = min(page.height, bottom + pad)
        if x1 <= x0 or bottom <= top:
            continue
        cropped = page.crop((x0, top, x1, bottom))
        text = cropped.extract_text() or ""
        if text.strip():
            texts.append(text.strip())
    return "\n".join(texts)


def parse_class_indices(text):
    match = re.search(r"CLASS\s*:?\s*([\d,\s]+)", text, re.IGNORECASE)
    if not match:
        return text.strip()
    return re.sub(r"\s+", "", match.group(1)).strip(",")


def split_name_and_address(text):
    """These blocks consistently read 'NAME ; address...' - split on the
    first semicolon; if there isn't one, keep it all as the name."""
    if ";" in text:
        name, _, address = text.partition(";")
        return name.strip(), address.strip()
    return text.strip(), ""


def parse_batch_header(page_text):
    """Pulls 'BATCH 23/2026' from the page header - shared by every record
    on the page, so this is extracted once per page, not per filing."""
    match = re.search(r"BATCH\s+(\d+)\s*/\s*(\d{4})", page_text, re.IGNORECASE)
    if match:
        return match.group(1), match.group(2)
    return None, None


def tight_crop_by_nonwhite(img_bytes, white_thresh=245, pad=2):
    """Trims uniform white margin down to the actual content - only a light
    cleanup, since the YOLO box already localizes the logo precisely."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    arr = np.array(img)
    mask = np.any(arr < white_thresh, axis=2)
    if not mask.any():
        return img_bytes
    ys, xs = np.where(mask)
    y0, y1 = max(0, ys.min() - pad), min(arr.shape[0], ys.max() + 1 + pad)
    x0, x1 = max(0, xs.min() - pad), min(arr.shape[1], xs.max() + 1 + pad)
    cropped = img.crop((x0, y0, x1, y1))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()


def remove_white_bg_make_transparent(png_bytes, white_thresh=245, soft=12):
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    arr = np.array(img)
    rgb = arr[:, :, :3].astype(np.int16)
    m = rgb.min(axis=2)
    alpha = np.clip((white_thresh - m) / max(1, soft) * 255, 0, 255)
    alpha = np.where(m >= white_thresh, 0, np.where(m >= white_thresh - soft, alpha, 255)).astype(np.uint8)
    arr[:, :, 3] = alpha
    out_img = Image.fromarray(arr, mode="RGBA")
    bbox = out_img.split()[-1].getbbox()
    if bbox:
        out_img = out_img.crop(bbox)
    buf = io.BytesIO()
    out_img.save(buf, format="PNG")
    return buf.getvalue()


def crop_logo(page_image, xyxy):
    x1, y1, x2, y2 = [int(round(v)) for v in xyxy]
    crop = page_image.crop((x1, y1, x2, y2))
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    try:
        png_bytes = tight_crop_by_nonwhite(png_bytes)
        png_bytes = remove_white_bg_make_transparent(png_bytes)
    except Exception:
        pass
    return png_bytes


def extract_page(model, ml_model, plumber_pdf, pdf_path, page_number, dpi, conf):
    """Extracts every trademark record on one page (1-indexed, matching
    --start_page elsewhere in this project)."""
    plumber_page = plumber_pdf.pages[page_number - 1]
    page_image = plumber_page.to_image(resolution=dpi).original
    page_text = plumber_page.extract_text() or ""
    batch_number, batch_year = parse_batch_header(page_text)

    img_arr = np.array(page_image)
    img_bgr = cv2.cvtColor(img_arr, cv2.COLOR_RGB2BGR)
    results = model(img_bgr, conf=conf, verbose=False)
    r = results[0]

    detections = []
    if r.boxes is not None:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            if cls_id >= len(CLASS_NAMES):
                continue
            detections.append({
                "class_name": CLASS_NAMES[cls_id],
                "xyxy": [float(v) for v in box.xyxy[0].cpu().numpy()],
                "conf": float(box.conf[0]),
            })

    records = group_detections_into_records(detections)

    extracted = []
    for record in records:
        fields = record["fields"]

        serial_number = extract_text_for_boxes(plumber_page, [record["serial_number_box"]], dpi)
        serial_number = re.sub(r"\s+", "", serial_number)[:50]

        class_text = extract_text_for_boxes(plumber_page, fields.get("class", []), dpi)
        date_text = extract_text_for_boxes(plumber_page, fields.get("date", []), dpi)
        intl_date_text = extract_text_for_boxes(
            plumber_page, fields.get("international_registration_date", []), dpi
        )
        intl_number_text = extract_text_for_boxes(
            plumber_page, fields.get("international_registration_number", []), dpi
        )
        description_text = extract_text_for_boxes(plumber_page, fields.get("description", []), dpi)
        agent_text = extract_text_for_boxes(plumber_page, fields.get("agent", []), dpi)
        applicant_text = extract_text_for_boxes(plumber_page, fields.get("applicant", []), dpi)

        applicant_name, applicant_address = split_name_and_address(applicant_text)
        # The applicant box occasionally overlaps slightly into the agent
        # line below it - trim anything from "AGENT :" onward if it leaked in.
        applicant_address = re.split(r"\bAGENT\s*:", applicant_address, flags=re.IGNORECASE)[0].strip()
        agent_details = re.sub(r"^AGENT\s*:?\s*", "", agent_text, flags=re.IGNORECASE).strip()

        logos = []
        for logo_box in record["logo_boxes"]:
            logo_bytes = crop_logo(page_image, logo_box["xyxy"])
            embedding = None
            if ml_model is not None:
                embedding = ml_model.generate_image_embedding(io.BytesIO(logo_bytes))
            logos.append({"logo_data": logo_bytes, "logo_embedding": embedding})

        extracted.append({
            "page": page_number,
            "serial_number": serial_number,
            "class_indices": parse_class_indices(class_text),
            "registration_date": date_text,
            "international_registration_date": intl_date_text or None,
            "international_registration_number": intl_number_text or None,
            "description": description_text,
            "applicant_name": applicant_name,
            "applicant_address": applicant_address,
            "agent_details": agent_details,
            "batch_number": batch_number,
            "batch_year": batch_year,
            "logos": logos,
        })

    return extracted


def main():
    p = argparse.ArgumentParser(description="Extract trademark records from a PDF journal.")
    p.add_argument("--pdf", required=True)
    p.add_argument("--start_page", type=int, default=4)
    p.add_argument("--max_pages", type=int, default=5)
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--model", default="models/best_colab2.pt")
    p.add_argument("--out", default="extracted_preview.json", help="Where to save the dry-run preview")
    p.add_argument("--commit", action="store_true", help="Actually write to the database (default: dry run only)")
    p.add_argument("--no_embeddings", action="store_true",
                    help="Skip CLIP embeddings - faster, no ml_utils model load, good for a quick text-only check")
    args = p.parse_args()

    if not os.path.exists(args.model):
        print(f"Model not found: {args.model}")
        return

    print(f"Loading model: {args.model}")
    model = YOLO(args.model)

    ml_model = None
    if not args.no_embeddings:
        import ml_utils
        ml_model = ml_utils.MLModel()

    all_records = []
    with pdfplumber.open(args.pdf) as plumber_pdf:
        total_pages = len(plumber_pdf.pages)
        end_page = min(args.start_page + args.max_pages - 1, total_pages)

        for page_number in range(args.start_page, end_page + 1):
            print(f"Processing page {page_number}/{total_pages}...")
            records = extract_page(model, ml_model, plumber_pdf, args.pdf, page_number, args.dpi, args.conf)
            all_records.extend(records)
            print(f"  -> {len(records)} record(s) found")

    print(f"\nTotal records extracted: {len(all_records)}")

    if args.commit:
        import database as db
        for record in all_records:
            if not record["serial_number"]:
                print("  ! Empty serial_number, skipping record")
                continue
            trademark_data = {k: v for k, v in record.items() if k not in ("logos", "page")}
            db.insert_trademark(trademark_data)

            conn = db.get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT id FROM trademarks WHERE serial_number = %s", (record["serial_number"],))
            row = cur.fetchone()
            cur.close(); conn.close()
            if not row:
                print(f"  ! Could not resolve trademark id for {record['serial_number']}, skipping its logos")
                continue
            trademark_id = row[0]
            for logo in record["logos"]:
                db.insert_trademark_logo(trademark_id, logo["logo_data"], logo.get("logo_embedding"))
        print(f"Committed {len(all_records)} trademark record(s) to the database.")
    else:
        preview = []
        for record in all_records:
            preview_record = {k: v for k, v in record.items() if k != "logos"}
            preview_record["logo_count"] = len(record["logos"])
            preview.append(preview_record)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(preview, f, indent=2, ensure_ascii=False)
        print("\nDry run only - nothing written to the database.")
        print(f"Preview saved to: {args.out}")
        print(f"Pass --commit to actually insert these {len(all_records)} record(s).")


if __name__ == "__main__":
    main()
