# yolo_to_labelstudio.py
# ─────────────────────────────────────────────────────────────
# Converts a pre_label.py output folder (images/ + labels/ + classes.txt)
# into a Label Studio task-import JSON, with the YOLO boxes attached as
# PREDICTIONS - so they show up pre-drawn when you import, instead of you
# drawing every box from scratch.
#
# Doesn't depend on label-studio-converter (which pulls in an nltk/audio
# dependency chain that can get blocked by endpoint security on some
# machines) - this is plain stdlib.
#
# Usage:
#   python yolo_to_labelstudio.py --review_dir to_review --local_files_prefix "/data/local-files/?d=to_review/images"
# ─────────────────────────────────────────────────────────────

import os
import json
import argparse


def load_classes(classes_path):
    with open(classes_path) as f:
        return [line.strip() for line in f if line.strip()]


def yolo_box_to_percent(cx, cy, w, h):
    """YOLO center-based normalized box -> Label Studio's top-left percent box."""
    x = (cx - w / 2) * 100
    y = (cy - h / 2) * 100
    return x, y, w * 100, h * 100


def build_tasks(images_dir, labels_dir, classes, local_files_prefix):
    tasks = []
    img_files = sorted(
        f for f in os.listdir(images_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    )

    for fname in img_files:
        stem = os.path.splitext(fname)[0]
        lbl_path = os.path.join(labels_dir, stem + ".txt")
        results = []

        if os.path.exists(lbl_path):
            with open(lbl_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    cls_id = int(parts[0])
                    cx, cy, w, h = map(float, parts[1:5])
                    x, y, wp, hp = yolo_box_to_percent(cx, cy, w, h)
                    label = classes[cls_id] if cls_id < len(classes) else f"class_{cls_id}"
                    results.append({
                        "from_name": "label",
                        "to_name": "image",
                        "type": "rectanglelabels",
                        "value": {
                            "x": x, "y": y, "width": wp, "height": hp,
                            "rotation": 0,
                            "rectanglelabels": [label],
                        },
                        "score": 1.0,
                    })

        prefix = local_files_prefix.rstrip("/")
        task = {
            "data": {"image": f"{prefix}/{fname}"},
            "predictions": [{"model_version": "pre_label", "result": results}] if results else [],
        }
        tasks.append(task)

    return tasks


def main():
    p = argparse.ArgumentParser(description="Convert pre_label.py output into Label Studio import JSON.")
    p.add_argument("--review_dir", required=True, help="Folder from pre_label.py, e.g. to_review_index2")
    p.add_argument("--out", default=None, help="Output JSON path (default: <review_dir>/label_studio_tasks.json)")
    p.add_argument(
        "--local_files_prefix", required=True,
        help="Label Studio local-files URL prefix for the images folder - must be "
             "RELATIVE (starting with /data/), not a full http://host URL, so Label "
             "Studio's export takes the fast direct-disk-read path instead of an "
             "authenticated HTTP round-trip that fails without an API token. "
             "e.g. '/data/local-files/?d=to_review_index2/images'",
    )
    args = p.parse_args()

    images_dir = os.path.join(args.review_dir, "images")
    labels_dir = os.path.join(args.review_dir, "labels")
    classes_path = os.path.join(args.review_dir, "classes.txt")

    for path in (images_dir, labels_dir, classes_path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Expected {path} - did you run pre_label.py first?")

    classes = load_classes(classes_path)
    tasks = build_tasks(images_dir, labels_dir, classes, args.local_files_prefix)

    out_path = args.out or os.path.join(args.review_dir, "label_studio_tasks.json")
    with open(out_path, "w") as f:
        json.dump(tasks, f)

    total_predictions = sum(len(t["predictions"][0]["result"]) if t["predictions"] else 0 for t in tasks)
    print(f"Wrote {len(tasks)} tasks ({total_predictions} pre-drawn boxes total) -> {out_path}")


if __name__ == "__main__":
    main()
