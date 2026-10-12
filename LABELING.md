# Labeling a new dataset (MyIPO journal -> trained YOLO model)

Pipeline: PDF -> page images -> pre-label with current model -> Label Studio review -> export -> merge -> train -> use in the app.

## Where the scripts live

- `main` already has: `pre_label.py` (fixed for the 10-class model), `auto_label_text_logo.py`, `final_dataset/`, `models/`, `export_fixed/`, `to_review/`.
- The `YOLO_Model` branch has the rest: `convert_pdf.py`, `yolo_to_labelstudio.py`, `merge_dataset.py`, `train_logo.py`, `export_model.py`, `test_model.py`, `fix_export_images.py`, `fix_export_zip.py`, `colab_train_logo.ipynb`. Copy what you need, without switching branches:
  `git show YOLO_Model:convert_pdf.py > convert_pdf.py` (same for the others).
- Check hardcoded paths after copying (e.g. Poppler in `convert_pdf.py`, dataset path in `train_logo.py`).

## Classes (fixed order - never change it)

`0 logo, 1 text_logo, 2 serial_number, 3 description, 4 agent, 5 applicant, 6 class, 7 date, 8 international_registration_date, 9 international_registration_number`

This order must match `final_dataset/logo_dataset.yaml`, `merge_dataset.py` (`DESIRED_CLASSES`), `pre_label.py` (`CLASS_NAMES`), `test_model.py` and the model itself. `pre_label.py` now refuses to run if the model's classes differ.

## Steps

1. **Download the journal PDF** from MyIPO into the repo folder.

2. **Convert pages to images** (use a UNIQUE prefix per journal - the merge skips filenames it has already seen):
   `python convert_pdf.py --pdf journal_B.pdf --out new_pages --start 4 --prefix journal_B`

3. **Pre-label with the current model:**
   `python pre_label.py --images new_pages --out to_review_B --model models/best_text_logo_v2.pt --conf 0.25`
   Lower `--conf` = more boxes to review.

4. **Convert to Label Studio JSON:**
   `python yolo_to_labelstudio.py --review_dir to_review_B --local_files_prefix "/data/local-files/?d=to_review_B/images"`
   The prefix must start with `/data/`, not `http://...`, or the later export may come back without images.

5. **Label Studio setup (one time):** run `label-studio`, open the "Logo Detection Marklogic" project, enable local files (`LOCAL_FILES_SERVING_ENABLED=true`, `LOCAL_FILES_DOCUMENT_ROOT` = the repo folder, add a Local Files storage). Make sure the label config has all 10 labels, including `text_logo` and `international_registration_number`.

6. **Import** `to_review_B/label_studio_tasks.json` (Import button).

7. **Review and fix the boxes**, submit each page with Ctrl+Enter.
   - Graphic only = `logo`. Text only = `text_logo`. Graphic + text together = `logo`.
   - Spend extra time on the logo / text_logo boundary - that is the model's weakest area.

8. **Export** as "YOLO with Images" (zip). Repair only if broken:
   - empty `images/` folder: `python fix_export_images.py --input X.zip --output X_fixed.zip`
   - image files without `.png` extension: `python fix_export_zip.py --input X.zip --output X_fixed.zip`

9. **Merge into the dataset:**
   `python merge_dataset.py --new_export YOLO_Labelled_B.zip`
   Check the summary (added / skipped duplicates / train / val). It re-splits train/val across the whole dataset every run.

10. **Train:** in `train_logo.py` point `YOLO(...)` at the latest model (e.g. `models/best_text_logo_v2.pt`), check `final_dataset/logo_dataset.yaml`'s `path:`, then `uv run train_logo.py`. Or use `colab_train_logo.ipynb` (update its old `best_colab2.pt` / 9-class references first, and zip `final_dataset` for upload).

11. **Save the model:** edit `run_dir` and `dest` in `export_model.py` (e.g. `models/best_text_logo_v3.pt`), then run it.

12. **Evaluate:** `uv run test_model.py --input journal.pdf --model models/best_text_logo_v3.pt`
    Check per-class mAP50 (target 0.70+). Weak class = label more pages of it and repeat from step 7.

13. **Use it in the app (`main`):**
    - set the default `yolo_model_path` in `pdf_extractor.py` to the new model
    - keep `LOGO_CLASS_IDS = {0, 1}` (`logo`, `text_logo`) and confirm the class order is unchanged
    - re-extract the journals you want updated. New logo detections also get component tiles automatically; for older records run `python backfill_logo_tiles.py`.
