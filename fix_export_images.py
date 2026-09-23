# fix_export_images.py
# ─────────────────────────────────────────────────────────────
# Repairs a Label Studio "YOLO with Images" export where the images/ folder
# came back completely empty (Label Studio's local-storage export path
# failing to resolve /data/local-files/?d=... URLs into actual file bytes -
# see the labels/ + classes.txt + notes.json still being correct, just the
# image binaries missing).
#
# Since the export's labels reference images by filename only, and you
# still have the real, untouched images sitting in one or more local
# folders (e.g. to_review/images from pre_label.py, or dataset/images/all
# from an earlier build), this re-sources each missing image from whichever
# folder actually has it and writes a corrected zip ready for
# merge_dataset.py.
#
# Usage:
#   python fix_export_images.py --input project-3-....zip --output project-3-fixed.zip
#
# Optional (defaults shown):
#   python fix_export_images.py --input project-3-....zip --output project-3-fixed.zip \
#       --image_sources to_review/images dataset/images/all
# ─────────────────────────────────────────────────────────────

import argparse
import os
import zipfile

DEFAULT_SOURCES = ["to_review/images", "dataset/images/all"]
IMAGE_EXTS = (".png", ".jpg", ".jpeg")


def find_image(stem, sources):
    """Search each source folder in order, return the first match's path."""
    for folder in sources:
        for ext in IMAGE_EXTS:
            candidate = os.path.join(folder, stem + ext)
            if os.path.exists(candidate):
                return candidate
    return None


def fix_zip(input_path, output_path, sources):
    with zipfile.ZipFile(input_path, "r") as zin:
        names = zin.namelist()
        label_entries = [n for n in names if n.startswith("labels/") and n.endswith(".txt")]

        found, missing = [], []
        resolved = {}  # label stem -> local image path
        for n in label_entries:
            stem = os.path.splitext(os.path.basename(n))[0]
            path = find_image(stem, sources)
            if path:
                resolved[stem] = path
                found.append(stem)
            else:
                missing.append(stem)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
            # Copy every non-image entry through untouched (labels/, classes.txt, notes.json, ...)
            for n in names:
                if n.startswith("images/"):
                    continue
                zout.writestr(n, zin.read(n))
            # Add the real image bytes, read fresh from disk
            for stem, path in resolved.items():
                ext = os.path.splitext(path)[1]
                with open(path, "rb") as f:
                    zout.writestr(f"images/{stem}{ext}", f.read())

    print(f"Resolved {len(found)}/{len(label_entries)} images from {sources} -> {output_path}")
    if missing:
        print(f"MISSING ({len(missing)}), not found in any source folder:")
        for stem in missing:
            print(f"  {stem}")


def main():
    p = argparse.ArgumentParser(
        description="Re-source missing images for a Label Studio export whose images/ folder came back empty."
    )
    p.add_argument("--input", required=True, help="Path to the broken export zip")
    p.add_argument("--output", required=True, help="Path to write the fixed zip")
    p.add_argument(
        "--image_sources", nargs="+", default=DEFAULT_SOURCES,
        help=f"Folders to search for the real images, in priority order (default: {DEFAULT_SOURCES})",
    )
    args = p.parse_args()

    fix_zip(args.input, args.output, args.image_sources)


if __name__ == "__main__":
    main()
