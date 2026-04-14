================================================================================
  YOLO TRADEMARK DETECTOR — COMPLETE GUIDE
  From Labeling to Testing
================================================================================

────────────────────────────────────────────────────────────────────────────────
STEP 1 — LABEL IMAGES IN LABEL STUDIO
────────────────────────────────────────────────────────────────────────────────

1.1  Start Label Studio
     Open your terminal and run:
          label-studio

     It will open automatically in your browser.

1.2  Open your project
     Click on "Logo Detection Marklogic"

1.3  Import images
     - Click "Import" button
     - Upload your journal page images (PNG/JPG)
     - Click "Import" to confirm

1.4  Start labeling
     - Click on any image to open it
     - Use the labels at the bottom toolbar:
          1 = logo                           (red)
          2 = text_logo                      (pink)
          3 = serial_number                  (blue)
          4 = description                    (green)
          5 = agent                          (orange)
          6 = applicant                      (purple)
          7 = class                          (cyan)
          8 = date                           (dark brown)
          9 = international_registration_date (brown)

1.5  How to draw a box
     - Press the number key for the label you want (e.g. press 1 for logo)
     - Click and drag over the region on the image
     - Repeat for every field visible on that page

1.6  Submit and continue
     - When done with one image, click "Submit" (or press Ctrl+Enter)
     - It will automatically move to the next image
     - Repeat for at least 50 images

     KEYBOARD SHORTCUTS:
          R          = Draw rectangle
          Ctrl+Z     = Undo
          Ctrl+Enter = Submit and go to next image
          1–9        = Select label

1.7  Priority — focus on these classes first:
     - logo / text_logo         (most important)
     - serial_number
     - class
     - description, agent, applicant   (optional but helps)

     RULE:
     - Graphic / symbol / drawing     → label as "logo"
     - Plain text or stylized text    → label as "text_logo"
     - Mixed graphic + text together  → label as "logo"


────────────────────────────────────────────────────────────────────────────────
STEP 2 — EXPORT FROM LABEL STUDIO
────────────────────────────────────────────────────────────────────────────────

2.1  Go back to your project page
     Click "Logo Detection Marklogic" at the top

2.2  Click "Export"

2.3  Select format: "YOLO with Images"

2.4  Click Export and save the zip file
     Example: YOLO_Labelled.zip

     The zip will contain:
          images/       ← your labeled images
          labels/       ← .txt files with bounding boxes
          classes.txt   ← class names


────────────────────────────────────────────────────────────────────────────────
STEP 3 — FIRST TIME SETUP (skip if already done)
────────────────────────────────────────────────────────────────────────────────

     Only do this once when you have your very first export.

3.1  Place the zip in your MarkLogic folder:
          C:\Users\xxin5\MarkLogic\YOLO_Labelled.zip

3.2  Run the merge script:
          uv run merge_dataset.py --new_export YOLO_Labelled.zip

     This will:
     - Remap class IDs from Label Studio order to your yaml order
     - Create the final_dataset/ folder with train/ and val/ splits
     - Print a summary of how many images were added


────────────────────────────────────────────────────────────────────────────────
STEP 4 — ADDING MORE DATA (repeat this every time you label more)
────────────────────────────────────────────────────────────────────────────────

4.1  Finish labeling new images in Label Studio (Step 1)

4.2  Export again from Label Studio (Step 2)
     Save the new zip as: YOLO_Labelled.zip

4.3  Run the merge script:
          uv run merge_dataset.py --new_export YOLO_Labelled.zip

     The script will:
     - Skip images that are already in your dataset (no duplicates)
     - Add only the new images
     - Re-shuffle and re-split train/val across everything
     - Print what was added and skipped

4.4  Check the summary printed in the terminal:
          Added:   X images
          Skipped: X duplicates
          Train:   X images
          Val:     X images


────────────────────────────────────────────────────────────────────────────────
STEP 5 — TRAIN THE MODEL
────────────────────────────────────────────────────────────────────────────────

5.1  Make sure logo_dataset.yaml has the correct absolute path:
     Open  final_dataset/logo_dataset.yaml  and check:

          path: C:/Users/xxin5/MarkLogic/final_dataset

     If the path is wrong, update it to match your actual folder.

5.2  First time training (starting fresh):
     In train_logo.py make sure this line says:

          model = YOLO("yolov8s.pt")

5.3  Continuing from a previous model (after you add more data):
     Change that line to point to your last best model:

          model = YOLO(r"runs/detect/train11/weights/best.pt")

     Replace train11 with whatever your latest run folder is.

5.4  Run training:
          uv run train_logo.py

     Training will take roughly 10–20 minutes on your GPU (RTX 2060).
     You will see progress like:

          Epoch  1/100    GPU_mem   box_loss   cls_loss ...
          Epoch  2/100    ...

5.5  Training finishes automatically when:
     - It reaches 100 epochs, OR
     - Early stopping kicks in (no improvement for 20 epochs)

5.6  Your trained model is saved at:
          runs/detect/trainXX/weights/best.pt
          runs/detect/trainXX/weights/last.pt

     Where XX is the run number (e.g. train11, train12...)


────────────────────────────────────────────────────────────────────────────────
STEP 6 — SAVE YOUR TRAINED MODEL
────────────────────────────────────────────────────────────────────────────────

6.1  Run export_model.py to copy best.pt into your models/ folder:

          python export_model.py

     Edit export_model.py first to set the correct run folder, e.g:
          run_dir = "runs/detect/train11"
          dest    = "models/best_t11.pt"

6.2  Your model is now saved at:
          models/best_t11.pt


────────────────────────────────────────────────────────────────────────────────
STEP 7 — TEST YOUR MODEL
────────────────────────────────────────────────────────────────────────────────

7.1  Test on a single image:
          uv run test_model.py --input image.png

7.2  Test on a PDF (processes first 10 pages by default):
          uv run test_model.py --input journal.pdf

7.3  Test with custom settings:
          uv run test_model.py --input journal.pdf --conf 0.3 --max_pages 20

          --conf       Confidence threshold (lower = more detections, default: 0.25)
          --max_pages  How many PDF pages to scan (default: 10)
          --dpi        PDF render quality (150=fast, 300=sharp, default: 150)
          --model      Path to model (default: runs/detect/train11/weights/best.pt)
          --out        Output folder (default: test_results/)

7.4  Results are saved in:
          test_results/image_result.jpg
          test_results/image_result1.jpg   ← auto-increments if same name
          test_results/image_result2.jpg

7.5  Reading the results in terminal:
          Found 5 detection(s):
          • logo               conf: 0.91    ← high confidence, reliable
          • text_logo          conf: 0.85    ← high confidence, reliable
          • serial_number      conf: 0.42    ← lower, may need more training data
          • description        conf: 0.38    ← lower, may need more training data

     General confidence guide:
          0.80 and above  = very reliable
          0.50 – 0.79     = good, acceptable
          0.25 – 0.49     = detected but uncertain — label more of this class
          below 0.25      = not shown (filtered out)


────────────────────────────────────────────────────────────────────────────────
STEP 8 — IMPROVING THE MODEL OVER TIME
────────────────────────────────────────────────────────────────────────────────

8.1  Check which classes are weak after training
     Look at the output after training finishes:

          Class                            mAP50
          logo                             0.905   ← great
          text_logo                        0.813   ← great
          serial_number                    0.394   ← needs more data
          agent                            0.362   ← needs more data
          international_registration_date  0.249   ← needs more data

8.2  Go back to Label Studio and label 20–30 more pages
     Focus on pages that clearly show the weak classes.

8.3  Export → run merge_dataset.py → retrain
     That's the full loop. Repeat until all classes reach 0.70+ mAP50.

8.4  Target scores:
          0.90+   Excellent — production ready
          0.70+   Good — usable
          0.50+   Acceptable — keep adding data
          below 0.50  — needs significantly more labeled examples


────────────────────────────────────────────────────────────────────────────────
QUICK REFERENCE — COMMON COMMANDS
────────────────────────────────────────────────────────────────────────────────

  Start Label Studio:
       label-studio

  Merge new labeled data:
       uv run merge_dataset.py --new_export YOLO_Labelled.zip

  Train model:
       uv run train_logo.py

  Test on image:
       uv run test_model.py --input image.png

  Test on PDF:
       uv run test_model.py --input journal.pdf --max_pages 20

  Convert PDF to images:
       python convert_pdf.py --pdf journal.pdf --out dataset/images/all --start 4 --prefix journal_A


────────────────────────────────────────────────────────────────────────────────
FILE STRUCTURE REFERENCE
────────────────────────────────────────────────────────────────────────────────

  MarkLogic/
  │
  ├── final_dataset/              ← your training dataset
  │   ├── images/
  │   │   ├── train/              ← 80% of labeled images
  │   │   └── val/                ← 20% of labeled images
  │   ├── labels/
  │   │   ├── train/              ← .txt label files for train images
  │   │   └── val/                ← .txt label files for val images
  │   └── logo_dataset.yaml       ← dataset config for YOLO
  │
  ├── models/                     ← exported trained models
  │   └── best_t11.pt
  │
  ├── runs/detect/                ← auto-created by YOLO during training
  │   └── train11/
  │       └── weights/
  │           ├── best.pt         ← best model from this run
  │           └── last.pt         ← last epoch model
  │
  ├── test_results/               ← output from test_model.py
  │
  ├── merge_dataset.py            ← merge new Label Studio exports
  ├── train_logo.py               ← run training
  ├── test_model.py               ← test your model
  ├── export_model.py             ← save best.pt to models/
  ├── convert_pdf.py              ← convert PDF pages to images
  └── logo_dataset.yaml           ← class definitions

================================================================================