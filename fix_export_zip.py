# fix_export_zip.py
# ─────────────────────────────────────────────────────────────
# Repairs a Label Studio YOLO-with-images export where image entries are
# missing their file extension (a bug in label-studio-sdk's filename
# extraction when the task's image URL is absolute rather than relative -
# see yolo_to_labelstudio.py's local_files_prefix note).
#
# Confirms every images/ entry is really PNG (via magic bytes) before
# renaming, then writes a corrected zip ready for merge_dataset.py.
#
# Usage:
#   python fix_export_zip.py --input image_MkLogic.zip --output image_MkLogic_fixed.zip
# ─────────────────────────────────────────────────────────────

import argparse
import zipfile

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def fix_zip(input_path, output_path):
    with zipfile.ZipFile(input_path, "r") as zin:
        names = zin.namelist()
        img_entries = [n for n in names if n.startswith("images/") and n != "images/"]

        bad = []
        for n in img_entries:
            data = zin.read(n)
            if data[:8] != PNG_MAGIC:
                bad.append(n)
        if bad:
            raise ValueError(f"{len(bad)} image entries are not PNG, aborting: {bad[:5]}")

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for n in names:
                data = zin.read(n)
                if n.startswith("images/") and n != "images/" and not n.lower().endswith(".png"):
                    new_name = n + ".png"
                else:
                    new_name = n
                zout.writestr(new_name, data)

    print(f"Fixed {len(img_entries)} image entries -> {output_path}")


def main():
    p = argparse.ArgumentParser(description="Fix missing .png extensions in a Label Studio YOLO export zip.")
    p.add_argument("--input", required=True, help="Path to the broken export zip")
    p.add_argument("--output", required=True, help="Path to write the fixed zip")
    args = p.parse_args()

    fix_zip(args.input, args.output)


if __name__ == "__main__":
    main()
