import os
import argparse
from pdf2image import convert_from_path, pdfinfo_from_path
import cv2
import numpy as np
from tqdm import tqdm

# Added 'prefix' parameter to the function
def convert(pdf_path, out_dir, dpi=300, start_page=1, end_page=None, prefix="page"): 
    os.makedirs(out_dir, exist_ok=True)
    
    poppler_path = r"C:\\poppler-25.12.0\\Library\\bin"

    info = pdfinfo_from_path(pdf_path, poppler_path=poppler_path)
    total_pages = info["Pages"]
    
    if start_page > total_pages:
        print(f"Error: Start page ({start_page}) is greater than total pages ({total_pages})")
        return 0

    if end_page is None:
        end_page = total_pages
    elif end_page > total_pages:
        print(f"Error: End page ({end_page}) is greater than total pages ({total_pages})")
        return 0

    print(f"Total pages in PDF: {total_pages}")
    print(f"Processing from page {start_page} to {end_page}...")

    for i in tqdm(range(start_page, end_page + 1), desc="Converting PDF", unit="page"):
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

    return (end_page - start_page + 1)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--pdf", required=True)
    p.add_argument("--out", default="dataset/images/all")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--start", type=int, default=1, help="Page number to start from")
    p.add_argument("--end", type=int, default=None, help="Page number to end at (optional)")

    # Required, no default - a shared default (e.g. "journal") lets two
    # different source PDFs both produce "journal_page_0100.png", which
    # merge_dataset.py's filename-only duplicate check then silently treats
    # as "already merged" even when the actual page content is completely
    # different (confirmed: 264 genuinely new labeled images were dropped
    # this way before the mismatch was caught). Forcing a unique prefix per
    # batch (e.g. batch30_2026, index2) prevents that collision outright.
    p.add_argument("--prefix", required=True, help="Unique filename prefix per batch/PDF (e.g. batch30_2026)")
    
    args = p.parse_args()
    
    # Pass the prefix to the convert function
    n = convert(args.pdf, args.out, dpi=args.dpi, start_page=args.start, end_page=args.end, prefix=args.prefix)
    print(f"\n--- Process Complete ---")
    print(f"Successfully converted {n} pages to: {args.out}")