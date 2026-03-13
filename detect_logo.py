# detect_logo.py
import os
import argparse
import io
from ultralytics import YOLO
import cv2
import numpy as np
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image
from tqdm import tqdm
from utils import tight_crop_by_nonwhite, remove_white_bg_make_transparent

POPPLER_PATH = r"C:\poppler-25.12.0\Library\bin"

def pages_from_pdf(pdf_path, dpi=150, max_pages=10):
    abs_pdf_path = os.path.abspath(pdf_path)
    if not os.path.exists(abs_pdf_path):
        print(f"❌ ERROR: File not found at {abs_pdf_path}")
        return []

    # Get total info to see how many pages exist
    info = pdfinfo_from_path(abs_pdf_path, poppler_path=POPPLER_PATH)
    actual_total = info["Pages"]
    
    # Decide how many pages to actually render
    end_page = min(actual_total, max_pages)

    print(f"--- Step 1: Converting PDF to Images ---")
    print(f"PDF has {actual_total} pages. Converting first {end_page} pages at {dpi} DPI...")
    
    try:
        # last_page is the key to making this fast!
        pages = convert_from_path(
            abs_pdf_path, 
            dpi=dpi, 
            poppler_path=POPPLER_PATH,
            first_page=4,
            last_page=50,
            thread_count=4
        )
    except Exception as e:
        print(f"❌ ERROR: pdf2image failed. Details: {e}")
        return []

    imgs = []
    for p in tqdm(pages, desc="Finalizing Images", unit="page"):
        arr = np.array(p)
        img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        imgs.append(img)
    return imgs

def model_detect_and_save(model_path, imgs, out_dir, conf=0.25, limit=50):
    if not imgs:
        print("No images to process.")
        return

    model = YOLO(model_path)
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n--- Step 2: Detecting Logos (Max Logos: {limit}) ---")
    saved = 0
    pbar = tqdm(total=len(imgs), desc="AI Scanning", unit="img")

    for pi, img in enumerate(imgs):
        if saved >= limit:
            break
            
        results = model(img, conf=conf, verbose=False)
        r = results[0]
        
        if hasattr(r, "boxes") and len(r.boxes) > 0:
            for bi, box in enumerate(r.boxes.xyxy.cpu().numpy()):
                if saved >= limit:
                    break
                
                x1, y1, x2, y2 = [int(round(v)) for v in box]
                crop = img[y1:y2, x1:x2]
                crop_pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
                
                buf = io.BytesIO()
                crop_pil.save(buf, format="PNG")
                bytes_png = buf.getvalue()
                
                try:
                    bytes_png = tight_crop_by_nonwhite(bytes_png, white_thresh=245, pad=2)
                    bytes_png = remove_white_bg_make_transparent(bytes_png, white_thresh=245, soft=12)
                except Exception:
                    pass
                
                fname = os.path.join(out_dir, f"page{pi+1:03d}_box{bi+1}.png")
                with open(fname, "wb") as f:
                    f.write(bytes_png)
                saved += 1
        
        pbar.update(1)
        pbar.set_postfix({"logos": saved})

    pbar.close()
    print(f"\n✅ Extraction finished. Total logos saved: {saved}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="models/best_t9.pt")
    p.add_argument("--out", default="extracted_logos")
    p.add_argument("--dpi", type=int, default=300) # Lowered to 150 for speed
    p.add_argument("--conf", type=float, default=0.35)
    p.add_argument("--pdf", default="index.cfm.pdf")
    p.add_argument("--limit", type=int, default=50, help="Stop after finding X logos")
    p.add_argument("--max_pages", type=int, default=20, help="Only render the first X pages")
    args = p.parse_args()

    # Pass the max_pages limit to the converter
    imgs = pages_from_pdf(args.pdf, dpi=args.dpi, max_pages=args.max_pages)
    
    model_detect_and_save(args.model, imgs, args.out, conf=args.conf, limit=args.limit)