"""
build_dataset.py  —  Run this ONCE locally to build your full training dataset.

Usage:
    python build_dataset.py --pdf1 index.cfm.pdf --pdf2 index.cfm_1.pdf

It will:
  1. Convert both PDFs to images (pages 4+)
  2. Auto-label logos (left-side region, large blobs only)
  3. Split 80/20 into train / val
  4. Write dataset/logo_dataset.yaml

After running, open LabelImg and adjust any bad boxes, then run train_logo.py.
"""

import os
import argparse
import random
import shutil

import cv2
import numpy as np
from pdf2image import convert_from_path, pdfinfo_from_path

POPPLER_PATH = r"C:\poppler-25.12.0\Library\bin"   # ← update if needed

# ─────────────────────────────────────────────
# 1. PDF → PNG images
# ─────────────────────────────────────────────
def convert_pdf(pdf_path, out_dir, dpi=150, start_page=4, prefix="journal"):
    os.makedirs(out_dir, exist_ok=True)
    total = pdfinfo_from_path(pdf_path, poppler_path=POPPLER_PATH)["Pages"]
    print(f"[Convert] {prefix}: {total} pages, starting at page {start_page} ...")
    saved = 0
    batch = 30
    for start in range(start_page, total + 1, batch):
        end = min(start + batch - 1, total)
        try:
            pages = convert_from_path(
                pdf_path, dpi=dpi,
                first_page=start, last_page=end,
                poppler_path=POPPLER_PATH, fmt="png"
            )
            for offset, page in enumerate(pages):
                arr = np.array(page)
                img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                fname = f"{prefix}_page_{start + offset:04d}.png"
                cv2.imwrite(os.path.join(out_dir, fname), img)
                saved += 1
            print(f"  pages {start}–{end} done ({saved} total)")
        except Exception as e:
            print(f"  ⚠ batch {start}–{end} failed: {e}")
    print(f"  ✅ {saved} images saved → {out_dir}")
    return saved


# ─────────────────────────────────────────────
# 2. Auto-label (logo region heuristic)
# ─────────────────────────────────────────────
def propose_logo_boxes(img_path, min_w=40, min_h=40, min_area=2000, max_aspect=4.0):
    img = cv2.imread(img_path)
    if img is None:
        return [], (0, 0)
    h, w = img.shape[:2]

    # Logos live in the left ~45% of the page, top ~80% height
    roi = img[0:int(h * 0.80), 0:int(w * 0.45)]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY_INV)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (8, 8))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < min_w or bh < min_h:                        continue
        if bw * bh < min_area:                               continue
        if not (1/max_aspect <= bw/max(1, bh) <= max_aspect): continue
        boxes.append((x, y, bw, bh))
    return boxes, (w, h)


def save_label(path, boxes, img_size):
    iw, ih = img_size
    with open(path, "w") as f:
        for (x, y, bw, bh) in boxes:
            cx = (x + bw / 2) / iw
            cy = (y + bh / 2) / ih
            f.write(f"0 {cx:.6f} {cy:.6f} {bw/iw:.6f} {bh/ih:.6f}\n")


def label_all(img_dir, lbl_dir):
    os.makedirs(lbl_dir, exist_ok=True)
    files = sorted(f for f in os.listdir(img_dir) if f.endswith(".png"))
    print(f"[Label] Labeling {len(files)} images ...")
    with_logo = empty = 0
    for fname in files:
        boxes, size = propose_logo_boxes(os.path.join(img_dir, fname))
        lbl = os.path.join(lbl_dir, fname.replace(".png", ".txt"))
        if boxes:
            save_label(lbl, boxes, size)
            with_logo += 1
        else:
            open(lbl, "w").close()
            empty += 1
    print(f"  ✅ {with_logo} with logos, {empty} empty")


# ─────────────────────────────────────────────
# 3. 80/20 train/val split
# ─────────────────────────────────────────────
def split_dataset(all_img_dir, all_lbl_dir, base_dir, seed=42):
    files = sorted(f for f in os.listdir(all_img_dir) if f.endswith(".png"))
    random.seed(seed)
    random.shuffle(files)
    split = int(len(files) * 0.8)
    sets  = {"train": files[:split], "val": files[split:]}

    for name, flist in sets.items():
        img_dst = os.path.join(base_dir, "images", name)
        lbl_dst = os.path.join(base_dir, "labels", name)
        os.makedirs(img_dst, exist_ok=True)
        os.makedirs(lbl_dst, exist_ok=True)
        for fname in flist:
            shutil.copy(os.path.join(all_img_dir, fname), os.path.join(img_dst, fname))
            lbl = fname.replace(".png", ".txt")
            shutil.copy(os.path.join(all_lbl_dir, lbl),  os.path.join(lbl_dst, lbl))
        print(f"  {name}: {len(flist)} images")

    print("  ✅ Split complete")


# ─────────────────────────────────────────────
# 4. Write logo_dataset.yaml
# ─────────────────────────────────────────────
def write_yaml(base_dir):
    abs_path = os.path.abspath(base_dir).replace("\\", "/")
    yaml_path = os.path.join(base_dir, "logo_dataset.yaml")
    with open(yaml_path, "w") as f:
        f.write(f"path: {abs_path}\n")
        f.write("train: images/train\n")
        f.write("val:   images/val\n\n")
        f.write("nc: 1\n")
        f.write("names:\n  0: logo\n")
    print(f"  ✅ Written: {yaml_path}")
    return yaml_path


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pdf1",    required=True,  help="First journal PDF")
    p.add_argument("--pdf2",    default=None,   help="Second journal PDF (optional)")
    p.add_argument("--out",     default="dataset", help="Output base folder")
    p.add_argument("--dpi",     type=int, default=150)
    p.add_argument("--start",   type=int, default=4,  help="First page to extract")
    args = p.parse_args()

    all_img = os.path.join(args.out, "images", "all")
    all_lbl = os.path.join(args.out, "labels", "all")

    # Step 1 — Convert PDFs
    convert_pdf(args.pdf1, all_img, dpi=args.dpi, start_page=args.start, prefix="journal_A")
    if args.pdf2:
        convert_pdf(args.pdf2, all_img, dpi=args.dpi, start_page=args.start, prefix="journal_B")

    # Step 2 — Auto-label
    label_all(all_img, all_lbl)

    # Step 3 — Split
    print("[Split] Creating train/val split (80/20) ...")
    split_dataset(all_img, all_lbl, args.out)

    # Step 4 — YAML
    print("[YAML] Writing dataset config ...")
    yaml_path = write_yaml(args.out)

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅  Dataset ready!
   Train / Val YAML : {yaml_path}
   Next: open LabelImg and verify/fix boxes,
   then run:  python train_logo.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")

if __name__ == "__main__":
    main()