# pre_label.py
# ─────────────────────────────────────────────────────────────
# Runs your current best YOLO model over a folder of NEW, unlabeled
# page images and writes out YOLO-format predictions (images/ + labels/
# + classes.txt) — the same shape merge_dataset.py already expects from
# a Label Studio export.
#
# Import the result into Label Studio as pre-labeled tasks: instead of
# drawing every box from scratch, you only fix what the model got wrong.
#
# Usage:
#   python pre_label.py --images path/to/new_pages --out to_review
#
# Optional:
#   python pre_label.py --images new_pages --out to_review \
#       --model runs/detect/train-2/weights/best.pt --conf 0.25
# ─────────────────────────────────────────────────────────────

import os
import shutil
import argparse

from ultralytics import YOLO

# Class names for the model trained on the CURRENT final_dataset/logo_dataset.yaml
# scheme (text_logo merged into logo, international_registration_number added).
# Does NOT match models/best_colab.pt (the old model) - that's why the --model
# default below points at a not-yet-downloaded file, so running this without
# --model before the retrain finishes fails loudly instead of silently
# shifting every predicted label (see test_model.py for the same note).
CLASS_NAMES = [
    "logo",                             # 0
    "serial_number",                    # 1
    "description",                      # 2
    "agent",                            # 3
    "applicant",                        # 4
    "class",                            # 5
    "date",                             # 6
    "international_registration_date",  # 7
    "international_registration_number",# 8
]


def write_classes_txt(out_dir):
    path = os.path.join(out_dir, "classes.txt")
    with open(path, "w") as f:
        f.write("\n".join(CLASS_NAMES) + "\n")
    return path


def pre_label(images_dir, out_dir, model_path, conf):
    if not os.path.exists(images_dir):
        raise FileNotFoundError(f"Images folder not found: {images_dir}")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}")

    img_out = os.path.join(out_dir, "images")
    lbl_out = os.path.join(out_dir, "labels")
    os.makedirs(img_out, exist_ok=True)
    os.makedirs(lbl_out, exist_ok=True)

    print(f"[Model] Loading {model_path}")
    model = YOLO(model_path)

    img_files = sorted(
        f for f in os.listdir(images_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    )
    print(f"[Scan] Found {len(img_files)} images in {images_dir}")

    total_boxes = 0
    per_class = {name: 0 for name in CLASS_NAMES}
    empty_count = 0

    for i, fname in enumerate(img_files, 1):
        src_path = os.path.join(images_dir, fname)
        shutil.copy(src_path, os.path.join(img_out, fname))

        results = model(src_path, conf=conf, verbose=False)
        r = results[0]

        stem = os.path.splitext(fname)[0]
        lbl_path = os.path.join(lbl_out, stem + ".txt")

        if r.boxes is not None and len(r.boxes) > 0:
            lines = []
            xywhn = r.boxes.xywhn.cpu().numpy()
            cls_ids = r.boxes.cls.cpu().numpy().astype(int)
            for (cx, cy, w, h), cls_id in zip(xywhn, cls_ids):
                lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
                total_boxes += 1
                if 0 <= cls_id < len(CLASS_NAMES):
                    per_class[CLASS_NAMES[cls_id]] += 1
            with open(lbl_path, "w") as f:
                f.write("\n".join(lines) + "\n")
        else:
            open(lbl_path, "w").close()
            empty_count += 1

        if i % 10 == 0 or i == len(img_files):
            print(f"  [{i}/{len(img_files)}] processed")

    classes_path = write_classes_txt(out_dir)

    print("\n" + "=" * 55)
    print("  Pre-labeling complete")
    print("=" * 55)
    print(f"  Images        : {len(img_files)}")
    print(f"  Boxes drawn   : {total_boxes}")
    print(f"  Empty images  : {empty_count} (no detections above conf={conf})")
    print("  Per-class counts:")
    for name, count in per_class.items():
        print(f"    {name:35s} {count}")
    print(f"\n  Output folder : {os.path.abspath(out_dir)}")
    print(f"  classes.txt   : {classes_path}")
    print("\n  Next: import this folder into Label Studio (YOLO format),")
    print("  review/fix the pre-drawn boxes, export, then run:")
    print(f"    python merge_dataset.py --new_export <your_export.zip>")


def main():
    p = argparse.ArgumentParser(description="Pre-label new images with the current best model.")
    p.add_argument("--images", required=True, help="Folder of new, unlabeled page images")
    p.add_argument("--out", default="to_review", help="Output folder (default: to_review)")
    p.add_argument("--model", default="models/best_colab3.pt",
                    help="Path to trained model weights (default: the not-yet-downloaded "
                         "9-class-v2 retrain; pass --model models/best_colab.pt explicitly "
                         "if you intentionally want to pre-label with the old model)")
    p.add_argument("--conf", type=float, default=0.25,
                    help="Confidence threshold; lower = more (noisier) boxes to review")
    args = p.parse_args()

    pre_label(args.images, args.out, args.model, args.conf)


if __name__ == "__main__":
    main()
