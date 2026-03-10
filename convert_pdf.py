import os
import argparse
from pdf2image import convert_from_path, pdfinfo_from_path
import cv2
import numpy as np
from tqdm import tqdm

# Added 'prefix' parameter to the function
def convert(pdf_path, out_dir, dpi=300, start_page=1, prefix="page"): 
    os.makedirs(out_dir, exist_ok=True)
    
    poppler_path = r"C:\\poppler-25.12.0\\Library\\bin"

    info = pdfinfo_from_path(pdf_path, poppler_path=poppler_path)
    total_pages = info["Pages"]
    
    if start_page > total_pages:
        print(f"Error: Start page ({start_page}) is greater than total pages ({total_pages})")
        return 0

    print(f"Total pages in PDF: {total_pages}")
    print(f"Processing from page {start_page} to {total_pages}...")

    for i in tqdm(range(start_page, total_pages + 1), desc="Converting PDF", unit="page"):
        try:
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
                arr = np.array(page)
                img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                
                # --- UPDATED SAVING LOGIC ---
                # This constructs the name: journal_2024_05_page_0004.png
                filename = f"{prefix}_page_{i:04d}.png"
                save_path = os.path.join(out_dir, filename)
                cv2.imwrite(save_path, img)
                
        except Exception as e:
            print(f"\nError on page {i}: {e}")

    return (total_pages - start_page + 1)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--pdf", required=True)
    p.add_argument("--out", default="dataset/images/all")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--start", type=int, default=1, help="Page number to start from")
    
    # --- NEW ARGUMENT FOR PREFIX ---
    p.add_argument("--prefix", default="journal", help="Filename prefix (e.g. journal_2024_05)")
    
    args = p.parse_args()
    
    # Pass the prefix to the convert function
    n = convert(args.pdf, args.out, dpi=args.dpi, start_page=args.start, prefix=args.prefix)
    print(f"\n--- Process Complete ---")
    print(f"Successfully converted {n} pages to: {args.out}")