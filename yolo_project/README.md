# Logo YOLO Project

Quick steps:

1. Install dependencies:
pip install -r requirements.txt


2. Convert your journal PDF to images:

python convert_pdf.py --pdf /path/to/index.cfm.pdf --out dataset/images --dpi 300

This writes images into `dataset/images/` which you should split into `train/` and `val/`.

3. Use `auto_label.py` to generate *proposal* bounding boxes (optional but speeds labeling):

python auto_label.py --images dataset/images/train --out dataset/labels/train

The script writes YOLO-format `.txt` label files. Open these in an annotation tool like LabelImg to fix any boxes.

4. Label / correct boxes:
- Use :contentReference[oaicite:6]{index=6} or :contentReference[oaicite:7]{index=7}.
- Save labels in YOLO format (`.txt` next to each image inside dataset/labels/`train` and `val`).

5. Train:

python train_logo.py

Trained weights end up under `runs/detect/train/weights/best.pt`.

6. Copy best weights to `models/logo_detector.pt` (or use `export_model.py`).

7. Detect:

python detect_logo.py --pdf /path/to/index.cfm.pdf --model models/logo_detector.pt --out extracted_logos


Notes:
- `auto_label.py` proposes boxes from top-of-page connected-components to speed up annotation.
- The detection script crops each detected logo and makes background transparent (tries best-effort)