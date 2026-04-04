# merge_dataset.py
# ─────────────────────────────────────────────────────────────
# Merges a new Label Studio YOLO export into your existing
# final_dataset/, remaps class IDs, and re-splits train/val.
#
# Usage:
#   python merge_dataset.py --new_export path/to/YOLO_Labelled.zip
#
# Optional:
#   python merge_dataset.py --new_export YOLO_Labelled.zip --dataset final_dataset --val_ratio 0.2
# ─────────────────────────────────────────────────────────────

import os
import re
import shutil
import random
import zipfile
import argparse
import tempfile

# ── Your desired class order (must match logo_dataset.yaml) ──
DESIRED_CLASSES = [
    "logo",                           # 0
    "text_logo",                      # 1
    "serial_number",                  # 2
    "description",                    # 3
    "agent",                          # 4
    "applicant",                      # 5
    "class",                          # 6
    "date",                           # 7
    "international_registration_date" # 8
]


def read_classes(classes_txt_path):
    """Read classes.txt from Label Studio export (alphabetically sorted)."""
    with open(classes_txt_path, "r") as f:
        return [line.strip().replace("\r", "") for line in f if line.strip()]


def build_remap(ls_classes):
    """Build a dict: label_studio_id -> your_desired_id."""
    remap = {}
    for old_id, name in enumerate(ls_classes):
        if name in DESIRED_CLASSES:
            remap[old_id] = DESIRED_CLASSES.index(name)
        else:
            print(f"  ⚠ Unknown class '{name}' in export — will be skipped!")
    return remap


def remap_label_file(src_path, remap):
    """Read a YOLO .txt label file, remap class IDs, return new lines."""
    new_lines = []
    with open(src_path, "r") as f:
        for line in f:
            line = line.strip().replace("\r", "")
            if not line:
                continue
            parts  = line.split()
            old_id = int(parts[0])
            if old_id not in remap:
                continue  # skip unknown classes
            new_id = remap[old_id]
            new_lines.append(f"{new_id} {' '.join(parts[1:])}")
    return new_lines


def extract_export(zip_path, tmp_dir):
    """Extract Label Studio zip, return (images_dir, labels_dir, classes_txt)."""
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(tmp_dir)

    images_dir  = os.path.join(tmp_dir, "images")
    labels_dir  = os.path.join(tmp_dir, "labels")
    classes_txt = os.path.join(tmp_dir, "classes.txt")

    if not os.path.exists(images_dir):
        raise FileNotFoundError("No 'images/' folder found in the export zip.")
    if not os.path.exists(labels_dir):
        raise FileNotFoundError("No 'labels/' folder found in the export zip.")
    if not os.path.exists(classes_txt):
        raise FileNotFoundError("No 'classes.txt' found in the export zip.")

    return images_dir, labels_dir, classes_txt


def collect_existing(dataset_dir):
    """Collect all stems already present in the dataset (train + val)."""
    existing = set()
    for split in ["train", "val"]:
        img_dir = os.path.join(dataset_dir, "images", split)
        if os.path.exists(img_dir):
            for f in os.listdir(img_dir):
                existing.add(os.path.splitext(f)[0])
    return existing


def collect_all_stems(dataset_dir):
    """Return list of all image stems across train + val."""
    stems = []
    for split in ["train", "val"]:
        img_dir = os.path.join(dataset_dir, "images", split)
        lbl_dir = os.path.join(dataset_dir, "labels", split)
        if not os.path.exists(img_dir):
            continue
        for fname in os.listdir(img_dir):
            stem     = os.path.splitext(fname)[0]
            img_path = os.path.join(img_dir, fname)
            lbl_path = os.path.join(lbl_dir, stem + ".txt")
            if os.path.exists(lbl_path):
                stems.append((stem, img_path, lbl_path))
    return stems


def merge(new_export_zip, dataset_dir, val_ratio, seed):
    print("\n" + "="*55)
    print("  Dataset Merger")
    print("="*55)

    # ── Step 1: Extract new export ─────────────────────────
    print(f"\n[1/4] Extracting: {new_export_zip}")
    tmp_dir = tempfile.mkdtemp()
    try:
        images_dir, labels_dir, classes_txt = extract_export(new_export_zip, tmp_dir)
    except FileNotFoundError as e:
        print(f"  ❌ {e}")
        shutil.rmtree(tmp_dir)
        return

    # ── Step 2: Build class remap ──────────────────────────
    ls_classes = read_classes(classes_txt)
    remap      = build_remap(ls_classes)
    print(f"\n[2/4] Class remap from export:")
    for old_id, name in enumerate(ls_classes):
        new_id = remap.get(old_id, "SKIP")
        print(f"  LS:{old_id} ({name}) → YOLO:{new_id}")

    # ── Step 3: Copy new files into dataset/all ────────────
    all_img_dir = os.path.join(dataset_dir, "images", "all")
    all_lbl_dir = os.path.join(dataset_dir, "labels", "all")
    os.makedirs(all_img_dir, exist_ok=True)
    os.makedirs(all_lbl_dir, exist_ok=True)

    existing_stems = collect_existing(dataset_dir)
    new_img_dir    = images_dir
    new_lbl_dir    = labels_dir

    added    = 0
    skipped  = 0
    new_imgs = sorted(f for f in os.listdir(new_img_dir)
                      if f.lower().endswith((".png", ".jpg", ".jpeg")))

    print(f"\n[3/4] Merging {len(new_imgs)} new images into dataset...")

    for img_fname in new_imgs:
        stem = os.path.splitext(img_fname)[0]

        # Skip duplicates
        if stem in existing_stems:
            print(f"  ⏭ Skip (already exists): {stem}")
            skipped += 1
            continue

        lbl_fname = stem + ".txt"
        lbl_src   = os.path.join(new_lbl_dir, lbl_fname)
        img_src   = os.path.join(new_img_dir, img_fname)

        if not os.path.exists(lbl_src):
            print(f"  ⚠ No label for {img_fname}, skipping.")
            skipped += 1
            continue

        # Remap and write label
        new_lines = remap_label_file(lbl_src, remap)
        lbl_dst   = os.path.join(all_lbl_dir, lbl_fname)
        with open(lbl_dst, "w") as f:
            f.write("\n".join(new_lines))

        # Copy image
        shutil.copy(img_src, os.path.join(all_img_dir, img_fname))

        existing_stems.add(stem)
        added += 1
        print(f"  ✅ Added: {stem}  ({len(new_lines)} boxes)")

    print(f"\n  Added: {added} | Skipped/duplicate: {skipped}")

    # ── Step 4: Re-split all data train/val ───────────────
    print(f"\n[4/4] Re-splitting all data (val={int(val_ratio*100)}%) ...")

    # Gather everything: existing train/val + newly added all/
    all_entries = []  # list of (stem, img_path, lbl_path)

    for split in ["train", "val"]:
        img_dir = os.path.join(dataset_dir, "images", split)
        lbl_dir = os.path.join(dataset_dir, "labels", split)
        if not os.path.exists(img_dir):
            continue
        for fname in os.listdir(img_dir):
            stem     = os.path.splitext(fname)[0]
            img_path = os.path.join(img_dir, fname)
            lbl_path = os.path.join(lbl_dir, stem + ".txt")
            if os.path.exists(img_path) and os.path.exists(lbl_path):
                all_entries.append((stem, img_path, lbl_path, fname))

    # Add newly merged entries from all/
    for fname in os.listdir(all_img_dir):
        stem     = os.path.splitext(fname)[0]
        img_path = os.path.join(all_img_dir, fname)
        lbl_path = os.path.join(all_lbl_dir, stem + ".txt")
        # Avoid duplicates already in train/val
        if not any(e[0] == stem for e in all_entries):
            if os.path.exists(img_path) and os.path.exists(lbl_path):
                all_entries.append((stem, img_path, lbl_path, fname))

    # Shuffle and split
    random.seed(seed)
    random.shuffle(all_entries)
    split_idx   = int(len(all_entries) * (1 - val_ratio))
    train_set   = all_entries[:split_idx]
    val_set     = all_entries[split_idx:]

    # Clear old train/val
    for split in ["train", "val"]:
        for sub in ["images", "labels"]:
            d = os.path.join(dataset_dir, sub, split)
            if os.path.exists(d):
                shutil.rmtree(d)
            os.makedirs(d)

    # Write new train/val
    def write_split(entries, split):
        img_dst = os.path.join(dataset_dir, "images", split)
        lbl_dst = os.path.join(dataset_dir, "labels", split)
        for stem, img_src, lbl_src, fname in entries:
            shutil.copy(img_src, os.path.join(img_dst, fname))
            shutil.copy(lbl_src, os.path.join(lbl_dst, stem + ".txt"))

    write_split(train_set, "train")
    write_split(val_set,   "val")

    # ── Summary ────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"  ✅ Merge complete!")
    print(f"  Total images : {len(all_entries)}")
    print(f"  Train        : {len(train_set)}")
    print(f"  Val          : {len(val_set)}")
    print(f"  Dataset dir  : {os.path.abspath(dataset_dir)}")
    print(f"{'='*55}")
    print(f"\n  Next: run train_logo.py to retrain 🚀")

    shutil.rmtree(tmp_dir)


def main():
    parser = argparse.ArgumentParser(description="Merge new Label Studio export into existing dataset.")
    parser.add_argument("--new_export", required=True,          help="Path to new YOLO_Labelled.zip from Label Studio")
    parser.add_argument("--dataset",    default="final_dataset", help="Path to your existing dataset folder")
    parser.add_argument("--val_ratio",  type=float, default=0.2, help="Fraction of data for validation (default: 0.2)")
    parser.add_argument("--seed",       type=int,   default=42,  help="Random seed for reproducible splits")
    args = parser.parse_args()

    if not os.path.exists(args.new_export):
        print(f"❌ Export zip not found: {args.new_export}")
        return

    # First time — create the dataset folder structure automatically
    if not os.path.exists(args.dataset):
        print(f"📁 Dataset folder not found — creating fresh dataset at: {args.dataset}")
        for split in ["train", "val", "all"]:
            os.makedirs(os.path.join(args.dataset, "images", split), exist_ok=True)
            os.makedirs(os.path.join(args.dataset, "labels", split), exist_ok=True)

    merge(args.new_export, args.dataset, args.val_ratio, args.seed)


if __name__ == "__main__":
    main()