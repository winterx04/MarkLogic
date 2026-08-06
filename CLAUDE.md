# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This is the **`YOLO_Model`** branch of the MarkLogic repo. It contains a YOLO object-detection
training pipeline that locates and classifies fields on Malaysian MyIPO trademark journal pages
(scanned PDF pages) — logos, text-logos, serial numbers, applicant/agent names, classes, dates, etc.
The full workflow (label → merge → train → export → test) is documented in detail in `README.md`;
read that file first for the step-by-step operator instructions — this file focuses on things not
already obvious from the README.

**Important:** `app.py` and `utils.py` are also present on this branch, but they are leftovers from
a much larger Flask trademark-search web app. `app.py` imports `database`, `ml_utils`, and
`pdf_extractor` modules, plus a `templates/`/`static/` directory tree — none of which exist on this
branch (they were removed from tracking in commit `f8a2353`, "new branch", and live instead on
`main` / `PDF_Extraction` / `interface` / `develop`). Don't try to run or fix `app.py` here; it is
dead code on this branch. `utils.py` (image crop/transparency helpers) *is* live — it's imported by
`detect_logo.py`.

## Environment setup

- Python 3.12 (`.python-version`), managed with `uv` (`pyproject.toml` + `uv.lock`). `requirements.txt`
  is a looser/alternate list for plain pip use — prefer `uv` for anything reproducible.
- `torch`/`torchvision` are pulled from the `pytorch-cu130` CUDA wheel index (see
  `[tool.uv.sources]` in `pyproject.toml`) for Windows/Linux — do not `pip install torch` directly,
  use `uv sync` / `uv add`.
- PDF rasterization (`pdf2image`) depends on a local **Poppler** install. The path is hardcoded per
  script as `POPPLER_PATH` (e.g. `test_model.py:21`, `build_dataset.py:25`, `detect_logo.py:13`,
  `convert_pdf.py:12`) — update these if Poppler is installed elsewhere on the machine.
- Label Studio (`label-studio` CLI) is used for annotation and is a project dependency
  (`uv add label-studio`).

## Common commands

```bash
# Start the annotation tool
label-studio

# First-time dataset build from raw journal PDFs (auto-labels logo boxes heuristically)
uv run build_dataset.py --pdf1 index.cfm.pdf --pdf2 index.cfm_1.pdf

# Merge a new Label Studio "YOLO with Images" export into final_dataset/ (remaps class IDs,
# skips duplicate images by filename stem, re-shuffles the train/val split every time)
uv run merge_dataset.py --new_export YOLO_Labelled.zip

# Train (edit train_logo.py to point at yolov8s.pt for a fresh run, or a prior
# runs/detect/trainXX/weights/best.pt to continue)
uv run train_logo.py

# Copy the best checkpoint from a run into models/
python export_model.py           # edit run_dir/dest inside the file first

# Test a trained model on an image or PDF
uv run test_model.py --input image.png
uv run test_model.py --input journal.pdf --conf 0.3 --max_pages 20 --model runs/detect/train13/weights/best.pt

# GPU sanity check
uv run test.py
```

There is no lint/test suite in this project — no pytest/ruff config exists.

## Architecture / pipeline structure

The scripts form a linear pipeline, each stage reading the previous stage's output. There is no
shared entry point; each `.py` file is invoked directly.

1. **Raw input**: MyIPO journal PDFs (e.g. `index.cfm.pdf`) — scanned pages, one trademark
   record layout per region of the page.
2. **`convert_pdf.py`** — generic PDF→PNG page rasterizer (used standalone or by other scripts).
3. **`build_dataset.py`** — one-shot bootstrap: converts PDFs to images, proposes rough logo
   bounding boxes with an OpenCV contour heuristic (left ~45% of page, top ~80% height, filtered by
   size/aspect ratio), splits 80/20 train/val, writes `dataset/logo_dataset.yaml` (single-class
   `logo` schema, `nc: 1`). Meant to give you a rough starting point to correct in Label Studio.
4. **`auto_label.py`** — an older/alternate heuristic labeler (header-region contour detection) —
   not part of the main documented flow but kept around.
5. **Label Studio** — human labeling/correction against the current 9-class schema (see
   `DESIRED_CLASSES` in `merge_dataset.py`): `logo, text_logo, serial_number, description, agent,
   applicant, class, date, international_registration_date`. Exported as "YOLO with Images" zips.
6. **`merge_dataset.py`** — the real dataset-of-record builder. Remaps Label Studio's alphabetical
   class order to `DESIRED_CLASSES` order, merges new export into `final_dataset/`, deduplicates by
   image filename stem, and re-splits train/val across the *entire* accumulated dataset (not just
   the new batch) on every run. `final_dataset/` is gitignored — it's a local build artifact, always
   regenerate it via this script rather than hand-editing it.
7. **`train_logo.py`** — thin wrapper around `ultralytics.YOLO.train()`. Dataset path, class count,
   and hyperparameters (epochs, augmentation, LR) are hardcoded in the file — edit directly rather
   than adding CLI args, per the existing style. Outputs land in `runs/detect/trainXX/` (auto
   incrementing; some historical `trainXX` runs are checked into git for reference/comparison —
   these directories can get large, be mindful before adding new ones to VCS).
8. **`export_model.py`** — copies a run's `weights/best.pt` into `models/` (gitignored) under a
   name you choose; also hardcoded (`run_dir`, `dest`), edit before running.
9. **`test_model.py`** — the main inference/eval entry point. Accepts a single image or a PDF
   (rasterizes + runs detection per page), draws labeled boxes color-coded per class, prints a
   confidence report, and writes annotated results to `test_results/`. `CLASS_NAMES` here must stay
   in sync with `DESIRED_CLASSES` in `merge_dataset.py` — they encode the same fixed class-index
   contract as the trained model's output head.
10. **`detect_logo.py`** — a narrower, standalone tool: runs a trained model over a PDF and dumps
    cropped, background-removed logo images (via `utils.py`'s `tight_crop_by_nonwhite` /
    `remove_white_bg_make_transparent`) to a folder, capped by a logo count limit. Useful for
    building a clean logo image corpus independent of the full annotation pipeline.

Class-index consistency is the main cross-cutting invariant: `DESIRED_CLASSES`
(`merge_dataset.py`), `CLASS_NAMES`/`CLASS_COLORS` (`test_model.py`), and whatever `nc`/`names` end
up in the generated `logo_dataset.yaml` must all agree on the same 9-class ordering, or a trained
model's predictions will be mislabeled.
