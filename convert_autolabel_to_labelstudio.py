"""Converts the OCR auto-labeled output (final_dataset/labels_autolabel/all/*.txt,
YOLO format) into a Label Studio predictions JSON, matching the exact format
already used in to_review/label_studio_tasks.json - so this can be reviewed
visually in Label Studio before anything is merged into the real training
labels. Doesn't touch final_dataset/labels/ or to_review/ - writes a new file.

Class list mirrors final_dataset/classes.txt with "text_logo" appended at
index 9 (matching auto_label_text_logo.py's TEXT_LOGO_CLASS = 9).
"""
import json
from pathlib import Path

DATASET_ROOT = Path(__file__).resolve().parent / "final_dataset"
LABELS_DIR = DATASET_ROOT / "labels_autolabel" / "all"
IMAGES_DIR = DATASET_ROOT / "images" / "all"
OUT_PATH = Path(__file__).resolve().parent / "final_dataset" / "label_studio_tasks_text_logo_review.json"

CLASS_NAMES = [
    "logo", "serial_number", "description", "agent", "applicant",
    "class", "date", "international_registration_date", "international_registration_number",
    "text_logo",
]


def yolo_line_to_result(line: str):
    parts = line.split()
    cls_id = int(parts[0])
    xc, yc, w, h = map(float, parts[1:5])
    x_pct = (xc - w / 2) * 100
    y_pct = (yc - h / 2) * 100
    return {
        "from_name": "label",
        "to_name": "image",
        "type": "rectanglelabels",
        "value": {
            "x": x_pct,
            "y": y_pct,
            "width": w * 100,
            "height": h * 100,
            "rotation": 0,
            "rectanglelabels": [CLASS_NAMES[cls_id]],
        },
        "score": 1.0,
    }


def main():
    label_files = sorted(LABELS_DIR.glob("*.txt"))
    tasks = []
    n_missing_image = 0

    for label_path in label_files:
        stem = label_path.stem
        img_path = None
        for ext in (".png", ".jpg", ".jpeg"):
            candidate = IMAGES_DIR / f"{stem}{ext}"
            if candidate.exists():
                img_path = candidate
                break
        if img_path is None:
            n_missing_image += 1
            continue

        lines = [l for l in label_path.read_text(encoding="utf-8").strip().splitlines() if l.strip()]
        results = [yolo_line_to_result(l) for l in lines]

        rel_path = img_path.relative_to(Path(__file__).resolve().parent).as_posix()
        tasks.append({
            "data": {"image": f"/data/local-files/?d={rel_path}"},
            "predictions": [{
                "model_version": "auto_label_text_logo",
                "result": results,
            }],
        })

    OUT_PATH.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    print(f"Wrote {len(tasks)} tasks ({n_missing_image} skipped - no matching image) -> {OUT_PATH}")
    n_text_logo = sum(1 for t in tasks for r in t["predictions"][0]["result"] if r["value"]["rectanglelabels"] == ["text_logo"])
    print(f"Total text_logo boxes included: {n_text_logo}")


if __name__ == "__main__":
    main()
