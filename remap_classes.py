# remap_classes.py
# ─────────────────────────────────────────────────────────────
# One-time migration: merges the "text_logo" class into "logo" and
# renumbers the remaining classes, across final_dataset/labels/{train,val,all}.
#
# Old (9 classes) -> New (8 classes):
#   0 logo                              -> 0 logo
#   1 text_logo                         -> 0 logo   (merged)
#   2 serial_number                     -> 1 serial_number
#   3 description                       -> 2 description
#   4 agent                             -> 3 agent
#   5 applicant                         -> 4 applicant
#   6 class                             -> 5 class
#   7 date                              -> 6 date
#   8 international_registration_date   -> 7 international_registration_date
#
# Run once, then re-run T_ci.py-style sanity checks / spot-check a few labels
# before retraining. Prints a per-file backup path so nothing is silently lost.
#
# Usage:
#   python remap_classes.py --dataset final_dataset
#   python remap_classes.py --dataset final_dataset --dry_run   (preview only, no writes)
# ─────────────────────────────────────────────────────────────

import os
import glob
import shutil
import argparse

REMAP = {0: 0, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7}


def remap_labels(dataset_dir, dry_run):
    pattern = os.path.join(dataset_dir, "labels", "**", "*.txt")
    label_files = glob.glob(pattern, recursive=True)

    backup_dir = os.path.join(dataset_dir, "labels_backup_9class")
    changed = 0
    merged_boxes = 0

    for path in label_files:
        with open(path) as f:
            lines = [line.strip() for line in f if line.strip()]

        new_lines = []
        file_modified = False
        for line in lines:
            parts = line.split()
            old_id = int(parts[0])
            new_id = REMAP[old_id]
            if old_id == 1:
                merged_boxes += 1
            if new_id != old_id:
                file_modified = True
            new_lines.append(f"{new_id} {' '.join(parts[1:])}")

        if not file_modified:
            continue

        changed += 1
        if dry_run:
            continue

        # Back up the original 9-class label before overwriting.
        rel_path = os.path.relpath(path, os.path.join(dataset_dir, "labels"))
        backup_path = os.path.join(backup_dir, rel_path)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copy(path, backup_path)

        with open(path, "w") as f:
            f.write("\n".join(new_lines) + ("\n" if new_lines else ""))

    print(f"Label files scanned : {len(label_files)}")
    print(f"Label files changed : {changed}")
    print(f"'text_logo' boxes merged into 'logo' : {merged_boxes}")
    if dry_run:
        print("\n(dry run - no files were written)")
    else:
        print(f"\nOriginal 9-class labels backed up to: {backup_dir}")


def main():
    p = argparse.ArgumentParser(description="Merge text_logo into logo and renumber classes.")
    p.add_argument("--dataset", default="final_dataset", help="Dataset folder (default: final_dataset)")
    p.add_argument("--dry_run", action="store_true", help="Preview counts without writing any files")
    args = p.parse_args()

    remap_labels(args.dataset, args.dry_run)


if __name__ == "__main__":
    main()
