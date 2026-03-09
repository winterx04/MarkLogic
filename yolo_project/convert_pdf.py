import os
import argparse
from pdf2image import convert_from_path, pdfinfo_from_path
import cv2
import numpy as np
from tqdm import tqdm

def convert(pdf_path, out_dir, dpi=300):
    os.makedirs(out_dir, exist_ok=True)
    
    # Path to your poppler bin folder
    poppler_path = r"C:\\poppler-25.12.0\\Library\\bin"

    # 1. Get total page count first
    print(f"Reading PDF info: {pdf_path}")
    info = pdfinfo_from_path(pdf_path, poppler_path=poppler_path)
    total_pages = info["Pages"]
    print(f"Total pages to process: {total_pages}")

    # 2. Loop through pages one by one to show progress
    # We use first_page and last_page to process only ONE page per loop
    for i in tqdm(range(1, total_pages + 1), desc="Converting PDF", unit="page"):
        try:
            # Convert a single page
            pages = convert_from_path(
                pdf_path, 
                dpi=dpi, 
                first_page=i, 
                last_page=i, 
                poppler_path=poppler_path,
                fmt="png"
            )
            
            if pages:
                page = pages[0]
                # Convert PIL image to OpenCV BGR format
                arr = np.array(page)
                img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                
                # Save the page
                save_path = os.path.join(out_dir, f"page_{i:04d}.png")
                cv2.imwrite(save_path, img)
                
        except Exception as e:
            print(f"\nError on page {i}: {e}")

    return total_pages

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--pdf", required=True)
    p.add_argument("--out", default="dataset/images/all")
    p.add_argument("--dpi", type=int, default=300)
    args = p.parse_args()
    
    n = convert(args.pdf, args.out, dpi=args.dpi)
    print(f"\n--- Process Complete ---")
    print(f"Successfully converted {n} pages to: {args.out}")