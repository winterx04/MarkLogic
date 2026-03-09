1️⃣ Where to put your journal PDF

After extracting the zip, your folder will look like this:

logo_yolo_project/
│
├── convert_pdf.py
├── auto_label.py
├── train_logo.py
├── detect_logo.py
├── export_model.py
├── requirements.txt
│
├── dataset/
│   ├── images/
│   │   ├── all/
│   │   ├── train/
│   │   └── val/
│   └── labels/
│       ├── train/
│       └── val/
│
└── models/

Place your journal PDF in the root folder like this:

logo_yolo_project/
│
├── your_journal.pdf   ← PUT IT HERE
├── convert_pdf.py
├── train_logo.py

Example:

logo_yolo_project/
   index.cfm.pdf
2️⃣ Install dependencies

Open terminal inside the folder:

cd logo_yolo_project

Then run:

pip install -r requirements.txt
3️⃣ Convert the PDF into training images

Run:

python convert_pdf.py --pdf index.cfm.pdf

Output images will appear in:

dataset/images/all/

Example:

dataset/images/all/page_0001.jpg
dataset/images/all/page_0002.jpg
dataset/images/all/page_0003.jpg
4️⃣ Split the images (important)

Move about 80% to train and 20% to val

Example:

dataset/images/train/page_0001.jpg
dataset/images/train/page_0002.jpg
dataset/images/train/page_0003.jpg

dataset/images/val/page_0020.jpg
dataset/images/val/page_0021.jpg
5️⃣ Auto-create initial logo labels

Run:

python auto_label.py --images dataset/images/train --out dataset/labels/train

and

python auto_label.py --images dataset/images/val --out dataset/labels/val

This tries to detect the logo automatically so you don't start labeling from scratch.

6️⃣ Fix labels (5–10 minutes)

Open the images with LabelImg and adjust the boxes around the logos.

Each image should have:

page_0001.jpg
page_0001.txt

Example label file:

0 0.42 0.07 0.22 0.05
7️⃣ Train YOLO

Run:

python train_logo.py

Training takes roughly:

5–20 minutes

depending on your GPU/CPU.

Your trained model will appear here:

runs/detect/train/weights/best.pt
8️⃣ Move the trained model into your project

Run:

python export_model.py

Now you have:

models/logo_detector.pt
9️⃣ Detect logos from PDFs

Run:

python detect_logo.py

Extracted logos will appear in:

extracted_logos/

Example output:

extracted_logos/logo_0_0.png
extracted_logos/logo_1_0.png
⚡ Important tip (for best results)

Label about 30–50 pages with logos.

Because logos are very consistent, YOLO learns extremely quickly.