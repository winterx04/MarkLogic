"""Pre-labeling assist for splitting the merged `logo` class back into
`logo` (device) and a new `text_logo` (wordmark) class.

For every image with an existing `logo` (class 0) box in final_dataset/labels/,
runs OCR (reusing pdf_extractor.py's existing tiny PaddleOCR engine - no new
model, no new dependency) to check whether that region is pure device, pure
wordmark text, or a mix:
  - No text detected / negligible text area -> keep as `logo` (device), unchanged
  - Text covers most of the box -> reclassify the whole box as `text_logo`
  - Text covers only part of the box -> keep the original box as `logo`
    (device) AND add a new `text_logo` box for just the OCR-detected text
    region (the two boxes may overlap - that's fine, they're different classes)

Output goes to a NEW folder (final_dataset/labels_autolabel/), never touching
or overwriting final_dataset/labels/ - review the results and copy over
whichever ones you accept.

Usage:
    python auto_label_text_logo.py            # full run
    python auto_label_text_logo.py --limit 10  # smoke test on first N images
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdf_extractor import _get_block_ocr_engine

DATASET_ROOT = Path(__file__).resolve().parent / "final_dataset"
IMAGES_DIR = DATASET_ROOT / "images" / "all"
LABELS_DIR = DATASET_ROOT / "labels" / "all"
OUT_DIR = DATASET_ROOT / "labels_autolabel" / "all"

LOGO_CLASS = 0
TEXT_LOGO_CLASS = 9  # new class - add "9: text_logo" to logo_dataset.yaml before training

TEXT_AREA_FRACTION_FOR_PURE_TEXT = 0.6  # OCR text covers >= this much of the box -> whole box is text_logo
MIN_TEXT_FRACTION_TO_SPLIT = 0.05  # ignore tiny/noise OCR detections


def yolo_to_pixel(xc, yc, w, h, img_w, img_h):
    x0 = (xc - w / 2) * img_w
    y0 = (yc - h / 2) * img_h
    x1 = (xc + w / 2) * img_w
    y1 = (yc + h / 2) * img_h
    return x0, y0, x1, y1


def pixel_to_yolo(x0, y0, x1, y1, img_w, img_h):
    xc = (x0 + x1) / 2 / img_w
    yc = (y0 + y1) / 2 / img_h
    w = (x1 - x0) / img_w
    h = (y1 - y0) / img_h
    return xc, yc, w, h


def ocr_text_bbox(crop_img, engine):
    """Union bounding box (crop-local pixel coords) of all OCR-detected text
    in this crop, or None if no text found."""
    arr = np.array(crop_img.convert("RGB"))
    bgr = arr[:, :, ::-1]
    boxes = []
    for res in engine.predict(bgr):
        polys = res.get("rec_polys") or res.get("dt_polys") or []
        scores = res.get("rec_scores") or []
        for poly, score in zip(polys, scores):
            if score < 0.5:
                continue
            # Cast to Python float explicitly - these come back as numpy int16
            # points, which silently overflow (wraps to garbage) once
            # multiplied for anything but tiny crops.
            xs = [float(p[0]) for p in poly]
            ys = [float(p[1]) for p in poly]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def process_image(img_path: Path, label_path: Path, engine):
    img = Image.open(img_path)
    img_w, img_h = img.size

    lines = label_path.read_text(encoding="utf-8").strip().splitlines() if label_path.exists() else []
    out_lines = []
    changed = False

    for line in lines:
        parts = line.split()
        cls = int(parts[0])
        xc, yc, w, h = map(float, parts[1:5])

        if cls != LOGO_CLASS:
            out_lines.append(line)
            continue

        x0, y0, x1, y1 = yolo_to_pixel(xc, yc, w, h, img_w, img_h)
        crop = img.crop((max(0, int(x0)), max(0, int(y0)), min(img_w, int(x1)), min(img_h, int(y1))))
        crop_w, crop_h = crop.size
        if crop_w == 0 or crop_h == 0:
            out_lines.append(line)
            continue

        text_bbox = ocr_text_bbox(crop, engine)
        if text_bbox is None:
            out_lines.append(line)
            continue

        tx0, ty0, tx1, ty1 = text_bbox
        text_area = (tx1 - tx0) * (ty1 - ty0)
        crop_area = crop_w * crop_h
        text_fraction = text_area / crop_area if crop_area else 0

        if text_fraction < MIN_TEXT_FRACTION_TO_SPLIT:
            out_lines.append(line)
            continue

        if text_fraction >= TEXT_AREA_FRACTION_FOR_PURE_TEXT:
            out_lines.append(f"{TEXT_LOGO_CLASS} {xc} {yc} {w} {h}")
            changed = True
        else:
            abs_tx0, abs_ty0 = x0 + tx0, y0 + ty0
            abs_tx1, abs_ty1 = x0 + tx1, y0 + ty1
            txc, tyc, tw, th = pixel_to_yolo(abs_tx0, abs_ty0, abs_tx1, abs_ty1, img_w, img_h)
            out_lines.append(f"{LOGO_CLASS} {xc} {yc} {w} {h}")
            out_lines.append(f"{TEXT_LOGO_CLASS} {txc} {tyc} {tw} {th}")
            changed = True

    out_path = OUT_DIR / label_path.name
    out_path.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N images (smoke test)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = _get_block_ocr_engine()
    if not engine:
        raise SystemExit("PaddleOCR not available in this environment - check paddleocr is installed")

    image_files = sorted(IMAGES_DIR.glob("*.png")) + sorted(IMAGES_DIR.glob("*.jpg"))
    if args.limit:
        image_files = image_files[:args.limit]

    n_changed = 0
    n_no_label = 0
    for img_path in image_files:
        label_path = LABELS_DIR / (img_path.stem + ".txt")
        if not label_path.exists():
            n_no_label += 1
            continue
        if process_image(img_path, label_path, engine):
            n_changed += 1

    print(f"Processed {len(image_files)} images ({n_no_label} had no existing label file) - "
          f"{n_changed} had a logo box reclassified/split -> {OUT_DIR}")


if __name__ == "__main__":
    main()
