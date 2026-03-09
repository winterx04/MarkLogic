# auto_label.py
import os
import argparse
import cv2
import numpy as np

def make_dirs(path):
    os.makedirs(path, exist_ok=True)

def propose_boxes_for_image(img_path, header_frac=0.25, min_area=400):
    img = cv2.imread(img_path)
    h, w = img.shape[:2]

    # crop top header region
    hh = int(h * header_frac)
    header = img[0:hh, :]

    gray = cv2.cvtColor(header, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY_INV)

    # morphological close to join logo parts
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5,5))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in contours:
        x,y,ww,hh = cv2.boundingRect(c)
        area = ww * hh
        aspect = ww / max(1, hh)
        # heuristics for logo-like shapes
        if area < min_area:
            continue
        if aspect < 0.3 or aspect > 12:
            continue
        # reject very wide lines (likely separators)
        if hh <= 3:
            continue
        boxes.append((x, y, ww, hh))

    # map boxes back to full-image coords
    boxes_full = [(x, y, w0, h0) for (x, y, w0, h0) in boxes]
    return boxes_full, (w, h)

def save_yolo_label(label_path, boxes, img_size):
    iw, ih = img_size
    lines = []
    for (x,y,w,h) in boxes:
        # center normalized coordinates
        cx = (x + w/2) / iw
        cy = (y + h/2) / ih
        nw = w / iw
        nh = h / ih
        lines.append(f"0 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n")
    with open(label_path, "w") as f:
        f.writelines(lines)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", required=True, help="folder with images (jpg)")
    parser.add_argument("--out", required=True, help="folder to write label .txt files")
    parser.add_argument("--header_frac", type=float, default=0.25)
    parser.add_argument("--min_area", type=int, default=400)
    args = parser.parse_args()

    make_dirs(args.out)
    img_files = sorted([p for p in os.listdir(args.images) if p.lower().endswith((".png",".jpg",".jpeg"))])

    for img_name in img_files:
        img_path = os.path.join(args.images, img_name)
        boxes, (w,h) = propose_boxes_for_image(img_path, header_frac=args.header_frac, min_area=args.min_area)
        label_file = os.path.join(args.out, os.path.splitext(img_name)[0] + ".txt")
        if boxes:
            # boxes coords are relative to header crop — map to full image (y offset = 0)
            save_yolo_label(label_file, boxes, (w, h))
            print("Wrote label:", label_file, "boxes:", len(boxes))
        else:
            # write empty label file YOLO expects empty file when no objects
            open(label_file, "w").close()
            print("Wrote empty label:", label_file)