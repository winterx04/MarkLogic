# test_model.py
# ─────────────────────────────────────────────────────────────
# Interactive tester for your trained YOLO trademark model.
# Supports single image OR PDF input.
#
# Usage:
#   python test_model.py                          ← prompts you for input
#   python test_model.py --input page.png         ← single image
#   python test_model.py --input journal.pdf      ← PDF
#   python test_model.py --input page.png --conf 0.3 --model models/best_t10.pt
# ─────────────────────────────────────────────────────────────

import os
import argparse
import cv2
import numpy as np
from ultralytics import YOLO
from PIL import Image
from pdf2image import convert_from_path, pdfinfo_from_path

POPPLER_PATH = r"C:\poppler-25.12.0\Library\bin"   # ← update if needed

# Class names must match your logo_dataset.yaml order
CLASS_NAMES = [
    "logo",
    "text_logo",
    "serial_number",
    "description",
    "agent",
    "applicant",
    "class",
    "date",
    "international_registration_date"
]

# Color per class (BGR) — shown on the output image
CLASS_COLORS = {
    "logo":                           (0,   0,   255),  # Red
    "text_logo":                      (180, 0,   255),  # Pink
    "serial_number":                  (255, 0,   0  ),  # Blue
    "description":                    (0,   170, 0  ),  # Green
    "agent":                          (0,   136, 255),  # Orange
    "applicant":                      (255, 0,   170),  # Purple
    "class":                          (255, 170, 0  ),  # Cyan
    "date":                           (47,  52,  74 ),  # Dark brown
    "international_registration_date":(19,  69,  139),  # Brown
}


def load_model(model_path):
    if not os.path.exists(model_path):
        print(f"❌ Model not found: {model_path}")
        print("   Make sure you ran export_model.py first, or pass --model with the correct path.")
        exit(1)
    print(f"✅ Loading model: {model_path}")
    return YOLO(model_path)


def draw_results(img, results, conf_threshold):
    """Draw bounding boxes + labels on image. Returns annotated image."""
    annotated = img.copy()
    boxes     = results[0].boxes

    if boxes is None or len(boxes) == 0:
        return annotated, []

    detections = []
    for box in boxes:
        conf  = float(box.conf[0])
        if conf < conf_threshold:
            continue

        cls_id    = int(box.cls[0])
        cls_name  = CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else f"class_{cls_id}"
        color     = CLASS_COLORS.get(cls_name, (200, 200, 200))
        x1, y1, x2, y2 = map(int, box.xyxy[0])

        # Draw box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        # Label background
        label     = f"{cls_name} {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(annotated, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        detections.append({"class": cls_name, "conf": round(conf, 3),
                            "box": (x1, y1, x2, y2)})

    return annotated, detections


def test_image(model, img_path, conf, out_dir):
    """Run detection on a single image file."""
    img = cv2.imread(img_path)
    if img is None:
        print(f"❌ Could not read image: {img_path}")
        return

    print(f"\n🔍 Running detection on: {img_path}")
    results            = model(img, conf=conf, verbose=False)
    annotated, detections = draw_results(img, results, conf)

    # Print results to terminal
    if detections:
        print(f"\n{'─'*50}")
        print(f"  Found {len(detections)} detection(s):")
        for d in detections:
            print(f"  • {d['class']:<35} conf: {d['conf']}")
        print(f"{'─'*50}")
    else:
        print("  ⚠ No detections above confidence threshold.")

    # Save annotated image
    os.makedirs(out_dir, exist_ok=True)
    stem     = os.path.splitext(os.path.basename(img_path))[0]
    out_path = os.path.join(out_dir, f"{stem}_result.jpg")
    cv2.imwrite(out_path, annotated)
    print(f"\n💾 Saved result → {out_path}")

    # Show in window
    print("   Press any key to close the preview window...")
    cv2.imshow("YOLO Detection Result", annotated)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def test_pdf(model, pdf_path, conf, out_dir, start_page=4, max_pages=10, dpi=150):
    """Run detection on each page of a PDF."""
    if not os.path.exists(pdf_path):
        print(f"❌ PDF not found: {pdf_path}")
        return

    info        = pdfinfo_from_path(pdf_path, poppler_path=POPPLER_PATH)
    total_pages = info["Pages"]
    end_page    = min(start_page + max_pages - 1, total_pages)

    print(f"\n📄 PDF: {pdf_path}")
    print(f"   Pages {start_page}–{end_page} of {total_pages} (DPI={dpi})")
    print(f"   Converting pages...")

    pages = convert_from_path(
        pdf_path, dpi=dpi,
        first_page=start_page, last_page=end_page,
        poppler_path=POPPLER_PATH
    )

    os.makedirs(out_dir, exist_ok=True)
    total_detections = 0

    for i, page in enumerate(pages):
        page_num = start_page + i
        img      = cv2.cvtColor(np.array(page), cv2.COLOR_RGB2BGR)

        results               = model(img, conf=conf, verbose=False)
        annotated, detections = draw_results(img, results, conf)
        total_detections     += len(detections)

        out_path = os.path.join(out_dir, f"page_{page_num:04d}_result.jpg")
        cv2.imwrite(out_path, annotated)

        print(f"  Page {page_num:>4}: {len(detections)} detection(s) → {out_path}")
        for d in detections:
            print(f"           • {d['class']:<35} conf: {d['conf']}")

    print(f"\n✅ Done — {total_detections} total detections across {len(pages)} pages")
    print(f"💾 Results saved to: {out_dir}")


def prompt_input():
    """Interactive prompt if no --input argument given."""
    print("=" * 55)
    print("  YOLO Trademark Model Tester")
    print("=" * 55)
    path = input("\nEnter path to image or PDF: ").strip().strip('"')
    return path


def main():
    parser = argparse.ArgumentParser(description="Test your trained YOLO trademark model.")
    parser.add_argument("--input",      default=None,                              help="Path to image (.png/.jpg) or PDF")
    parser.add_argument("--model",      default="runs/detect/train11/weights/best.pt", help="Path to trained model .pt file")
    parser.add_argument("--conf",       type=float, default=0.25,                 help="Confidence threshold (default: 0.25)")
    parser.add_argument("--out",        default="test_results",                   help="Output folder for annotated images")
    parser.add_argument("--start_page", type=int,   default=4,                    help="PDF: first page to process")
    parser.add_argument("--max_pages",  type=int,   default=10,                   help="PDF: max pages to process")
    parser.add_argument("--dpi",        type=int,   default=150,                  help="PDF: render DPI (150=fast, 300=sharp)")
    args = parser.parse_args()

    # Get input path
    input_path = args.input or prompt_input()
    if not input_path:
        print("❌ No input provided.")
        return

    input_path = os.path.abspath(input_path)
    if not os.path.exists(input_path):
        print(f"❌ File not found: {input_path}")
        return

    model = load_model(args.model)
    ext   = os.path.splitext(input_path)[1].lower()

    if ext == ".pdf":
        test_pdf(model, input_path, args.conf, args.out,
                 start_page=args.start_page,
                 max_pages=args.max_pages,
                 dpi=args.dpi)
    elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
        test_image(model, input_path, args.conf, args.out)
    else:
        print(f"❌ Unsupported file type: {ext}")
        print("   Supported: .png .jpg .jpeg .pdf")


if __name__ == "__main__":
    main() 