# make_merged_dataset.py
# ─────────────────────────────────────────────────────────────
# Builds final_dataset_merged/ from final_dataset/: identical, except every
# "text_logo" box (class 1) is relabelled "logo" (class 0).
#
# - Your original final_dataset/ is never modified (labels, images, yaml).
# - Images are HARD LINKS to the originals: no extra disk space (5.9 GB), and
#   the two folders can never drift apart on image content.
# - Class numbering stays the 10-class scheme, so pdf_extractor.py,
#   pre_label.py and test_model.py need no changes. Class 1 (text_logo) stays
#   defined but has no labels in the merged copy, so a model trained on it
#   simply never predicts it (the extractor already treats ids {0, 1} alike).
#
# Usage:
#   python make_merged_dataset.py --dry_run     (report only, writes nothing)
#   python make_merged_dataset.py               (build final_dataset_merged/)
# ─────────────────────────────────────────────────────────────
import argparse
import os
import shutil
from collections import Counter

SRC_DEFAULT = "final_dataset"
DST_DEFAULT = "final_dataset_merged"
SPLITS = ("train", "val")
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def box_key(parts):
    """Rounded geometry of a label line - to spot two boxes that became identical after the merge."""
    return tuple(round(float(v), 4) for v in parts[1:5])


def main():
    ap = argparse.ArgumentParser(description="Merge text_logo into logo in a COPY of the dataset.")
    ap.add_argument("--src", default=SRC_DEFAULT)
    ap.add_argument("--dst", default=DST_DEFAULT)
    ap.add_argument("--dry_run", action="store_true")
    args = ap.parse_args()

    src, dst = os.path.abspath(args.src), os.path.abspath(args.dst)
    if not os.path.isdir(src):
        raise SystemExit(f"Source dataset not found: {src}")
    if os.path.exists(dst) and not args.dry_run:
        raise SystemExit(f"{dst} already exists - delete it first (it only holds links and relabelled copies).")

    before, after = Counter(), Counter()
    merged_boxes = dup_boxes = files = images = no_label = 0

    for split in SPLITS:
        img_dir = os.path.join(src, "images", split)
        lbl_dir = os.path.join(src, "labels", split)
        out_img = os.path.join(dst, "images", split)
        out_lbl = os.path.join(dst, "labels", split)
        if not args.dry_run:
            os.makedirs(out_img, exist_ok=True)
            os.makedirs(out_lbl, exist_ok=True)

        for name in sorted(os.listdir(img_dir)):
            stem, ext = os.path.splitext(name)
            if ext.lower() not in IMG_EXT:
                continue
            images += 1
            if not args.dry_run:
                try:
                    os.link(os.path.join(img_dir, name), os.path.join(out_img, name))   # hard link: no copy
                except OSError:
                    shutil.copy2(os.path.join(img_dir, name), os.path.join(out_img, name))   # other drive / no link support

            lbl_path = os.path.join(lbl_dir, stem + ".txt")
            if not os.path.exists(lbl_path):
                no_label += 1
                if not args.dry_run:
                    open(os.path.join(out_lbl, stem + ".txt"), "w").close()   # a background-only image
                continue

            new_lines, seen_logo_boxes = [], set()
            with open(lbl_path) as f:
                for line in f:
                    parts = line.split()
                    if len(parts) < 5:
                        continue
                    cls = int(parts[0])
                    before[cls] += 1
                    if cls == 1:
                        cls = 0
                        merged_boxes += 1
                    if cls == 0:                                   # identical logo boxes (same place) would be duplicates
                        key = box_key(parts)
                        if key in seen_logo_boxes:
                            dup_boxes += 1
                            continue
                        seen_logo_boxes.add(key)
                    after[cls] += 1
                    new_lines.append(" ".join([str(cls)] + parts[1:]))
            files += 1
            if not args.dry_run:
                with open(os.path.join(out_lbl, stem + ".txt"), "w") as f:
                    f.write("\n".join(new_lines) + ("\n" if new_lines else ""))

    if not args.dry_run:
        yaml_src = os.path.join(src, "logo_dataset.yaml")
        with open(yaml_src) as f:
            text = f.read()
        lines = []
        for line in text.splitlines():
            if line.startswith("path:"):
                line = "path: " + dst.replace("\\", "/")
            lines.append(line)
        with open(os.path.join(dst, "logo_dataset.yaml"), "w") as f:
            f.write("\n".join(lines) + "\n")

    print(("DRY RUN - nothing written\n" if args.dry_run else "") + f"images: {images} | label files read: {files} | images without a label file: {no_label}")
    print(f"text_logo boxes relabelled as logo: {merged_boxes} | exact-duplicate logo boxes dropped after merge: {dup_boxes}")
    print("boxes per class   before -> after")
    for c in sorted(before):
        print(f"  class {c}: {before[c]:>6} -> {after.get(c, 0):>6}")
    print(f"total boxes: {sum(before.values())} -> {sum(after.values())}  (difference = duplicates dropped = {dup_boxes})")
    if not args.dry_run:
        print(f"\nBuilt {dst}\nTrain with data={os.path.join(dst, 'logo_dataset.yaml')!r}")


if __name__ == "__main__":
    main()
