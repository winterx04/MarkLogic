# detect_logo.py
import os
import argparse
from ultralytics import YOLO
import cv2
import numpy as np
from pdf2image import convert_from_path
from PIL import Image
from utils import tight_crop_by_nonwhite, remove_white_bg_make_transparent

def pages_from_pdf(pdf_path, dpi=300):
    pages = convert_from_path(pdf_path, dpi=dpi)
    imgs = []
    for p in pages:
        arr = np.array(p)
        img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        imgs.append(img)
    return imgs

def model_detect_and_save(model_path, imgs, out_dir, conf=0.25):
    model = YOLO(model_path)
    os.makedirs(out_dir, exist_ok=True)
    saved = 0
    for pi, img in enumerate(imgs):
        # Ultralytics accepts path or numpy array
        results = model(img, conf=conf)
        r = results[0]
        if hasattr(r, "boxes") and len(r.boxes) > 0:
            for bi, box in enumerate(r.boxes.xyxy.cpu().numpy()):
                x1, y1, x2, y2 = [int(round(v)) for v in box]
                crop = img[y1:y2, x1:x2]
                # to PNG bytes
                crop_pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
                buf = io = None
                import io as _io
                buf = _io.BytesIO()
                crop_pil.save(buf, format="PNG")
                bytes_png = buf.getvalue()
                # tight crop + transparent
                try:
                    bytes_png = tight_crop_by_nonwhite(bytes_png, white_thresh=245, pad=2)
                    bytes_png = remove_white_bg_make_transparent(bytes_png, white_thresh=245, soft=12)
                except Exception:
                    pass
                fname = os.path.join(out_dir, f"page{pi+1:03d}_box{bi+1}.png")
                with open(fname, "wb") as f:
                    f.write(bytes_png)
                saved += 1
                print("Saved", fname)
    print("Total logos saved:", saved)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--pdf", required=True)
    p.add_argument("--model", default="models/logo_detector.pt")
    p.add_argument("--out", default="extracted_logos")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--conf", type=float, default=0.35)
    args = p.parse_args()

    imgs = pages_from_pdf(args.pdf, dpi=args.dpi)
    model_detect_and_save(args.model, imgs, args.out, conf=args.conf)