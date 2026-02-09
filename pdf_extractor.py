import fitz  # PyMuPDF
import re
import os
from datetime import datetime
import io
from PIL import Image
from typing import List, Dict, Any, Optional

# --- REGEX PATTERNS (UNCHANGED) ---
CLASS_PATTERN = re.compile(r"^\s*CLASS\s*:\s*([\d,\s]+)", re.IGNORECASE)
SERIAL_AND_DATE_PATTERN = re.compile(r"^(TM\d{8,}|[A-Z]{2}\d{8,}|JV\d{8,}|\d{8,})\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})")
INT_REG_PATTERN = re.compile(r"International Registration Number\s*:\s*(\d+)", re.IGNORECASE)
AGENT_PATTERN = re.compile(r"^\s*AGENT\s*:", re.IGNORECASE)

def is_applicant_line(text: str) -> bool:
    """Heuristic to determine if a line of text is likely part of an applicant's name."""
    if len(text) < 3 or not text.isupper():
        return False
    if text.isdigit() or "CLASS" in text:
        return False
    return True

def parse_trademark_block_text(text_blocks: list) -> Dict[str, Any]:
    """Parses a list of text blocks to extract structured trademark information."""
    data = {
        'serial_number': None,
        'registration_date': None,
        'class_indices': None,
        'applicant_name': [],
        'description': [],
        'agent_details': []
    }

    lines = []
    for block in text_blocks:
        for line in block.get("lines", []):
            line_text = "".join(span['text'] for span in line['spans']).strip()
            if line_text:
                lines.append(line_text)

    agent_start_index = -1
    for i, line in enumerate(lines):
        if AGENT_PATTERN.search(line):
            agent_start_index = i
            break
            
    pre_agent_lines = lines[:agent_start_index] if agent_start_index != -1 else lines
    
    if agent_start_index != -1:
        data['agent_details'] = lines[agent_start_index:]

    current_class = None
    description_started = False
    
    for line in pre_agent_lines:
        class_match = CLASS_PATTERN.search(line)
        serial_date_match = SERIAL_AND_DATE_PATTERN.search(line)
        int_reg_match = INT_REG_PATTERN.search(line)

        if class_match:
            data['class_indices'] = class_match.group(1).replace(" ", "").strip()
            description_started = False
        
        elif serial_date_match:
            data['serial_number'] = serial_date_match.group(1)
            try:
                data['registration_date'] = datetime.strptime(serial_date_match.group(2), "%d %B %Y").date()
            except ValueError:
                data['registration_date'] = None
            description_started = True
        
        elif int_reg_match:
            data['international_registration_number'] = int_reg_match.group(1)

        elif is_applicant_line(line):
            data['applicant_name'].append(line)
            description_started = False
        
        elif description_started:
            if line.strip().upper().startswith('CLASS '):
                current_class = line.strip()
                data['description'][current_class] = []
            elif current_class:
                data['description'][current_class].append(line)
            else:
                if 'main' not in data['description']:
                    data['description']['main'] = []
                data['description']['main'].append(line)

    if pre_agent_lines:
        for line in pre_agent_lines:
            if not (CLASS_PATTERN.search(line) or SERIAL_AND_DATE_PATTERN.search(line) or "LIST OF" in line or line.isdigit()):
                data['trademark_name'] = line
                break

    data['applicant_name'] = " ".join(data['applicant_name']).split(';')[0].strip()
    data['agent_details'] = "\n".join(data['agent_details']).strip()
    
    for key, value in data['description'].items():
        data['description'][key] = "\n".join(value).strip()
    if len(data['description']) == 1 and 'main' in data['description']:
        data['description'] = data['description']['main']
        
    return data

def extract_logo(doc: fitz.Document, page: fitz.Page, block_rect: fitz.Rect) -> Optional[bytes]:
    """Extracts the logo from a given rectangular block on a page."""
    image_list = page.get_images(full=True)
    images_in_block = [img for img in image_list if page.get_image_bbox(img).intersects(block_rect)]

    if images_in_block:
        images_in_block.sort(key=lambda img: page.get_image_bbox(img).y0)
        xref, smask_xref = images_in_block[0][0], images_in_block[0][1]
        
        try:
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]

            if smask_xref > 0:
                mask_image = doc.extract_image(smask_xref)
                with Image.open(io.BytesIO(image_bytes)) as base_pil, \
                     Image.open(io.BytesIO(mask_image["image"])).convert("L") as mask_pil:
                    base_pil = base_pil.convert("RGBA")
                    if base_pil.size != mask_pil.size:
                        mask_pil = mask_pil.resize(base_pil.size, Image.Resampling.LANCZOS)
                    base_pil.putalpha(mask_pil)
                    with io.BytesIO() as output:
                        base_pil.save(output, format="PNG")
                        return output.getvalue()
            return image_bytes
        except Exception as e:
            print(f"Warning: Could not extract image with xref {xref}. Error: {e}")
            return None

    max_font_size = 0.0
    logo_bbox = None
    text_blocks_for_logo = page.get_text("dict", clip=block_rect)["blocks"]

    for block in text_blocks_for_logo[:3]:
        for line in block.get("lines", []):
            line_text = "".join(s['text'] for s in line['spans']).strip()
            if not line_text or "CLASS :" in line_text or "LIST OF" in line_text:
                continue

            if line['spans']:
                font_size = line['spans'][0]['size']
                if font_size > max_font_size:
                    max_font_size = font_size
                    logo_bbox = fitz.Rect(line['bbox'])
    
    if logo_bbox:
        margin = 5
        logo_bbox.x0 -= margin; logo_bbox.y0 -= margin
        logo_bbox.x1 += margin; logo_bbox.y1 += margin
        
        pix = page.get_pixmap(clip=logo_bbox, dpi=300)
        return pix.tobytes("png")
        
    return None

# (BACKUP 8/2/2026)
# def extract_trademarks_from_pdf(pdf_path: str, logo_dir: str = "logos") -> List[Dict[str, Any]]:
#     """Main function to extract all trademark information from a PDF file."""
#     if not os.path.exists(logo_dir):
#         os.makedirs(logo_dir)

#     doc = fitz.open(pdf_path)
#     all_trademarks = []
    
#     print(f"Processing {len(doc)} pages...")

#     for page_num, page in enumerate(doc):
#         class_instances = sorted(page.search_for("CLASS :"), key=lambda r: r.y0)
        
#         if not class_instances:
#             continue
        
#         first_content_y = class_instances[0].y0 - 150
#         if first_content_y < 50: first_content_y = 50
        
#         block_start_y = first_content_y

#         for i in range(len(class_instances)):
#             try:
#                 block_end_y = class_instances[i + 1].y0 - 5 if i + 1 < len(class_instances) else page.rect.height
                
#                 trademark_block_rect = fitz.Rect(0, block_start_y, page.rect.width, block_end_y)
                
#                 text_blocks = page.get_text("dict", clip=trademark_block_rect).get("blocks", [])
#                 if not text_blocks:
#                     block_start_y = block_end_y
#                     continue
                
#                 data = parse_trademark_block_text(text_blocks)
                
#                 logo_bytes = extract_logo(doc, page, trademark_block_rect)

#                 if logo_bytes:
#                     # --- THIS IS THE FIX ---
#                     # Use a fallback filename if serial_number is None to prevent a crash.
#                     serial_for_filename = data.get('serial_number') or f'unknown_p{page_num+1}_b{i+1}'
                    
#                     # Sanitize the filename string (it's now guaranteed to be a string).
#                     safe_filename_part = re.sub(r'[^\w\-.]', '_', serial_for_filename)
#                     img_filename = f"logo_{safe_filename_part}.png"
#                     # --- END OF FIX ---
                    
#                     logo_path = os.path.join(logo_dir, img_filename)
#                     with open(logo_path, "wb") as img_file:
#                         img_file.write(logo_bytes)
#                     data['logo_path'] = logo_path
#                 else:
#                     data['logo_path'] = None
                
#                 # We still only want to save entries that have a valid serial number.
#                 # The fallback filename is just to prevent a crash during logo saving.
#                 if data['serial_number']:
#                     all_trademarks.append(data)

#                 block_start_y = block_end_y

#             except Exception as e:
#                 import traceback
#                 print(f"--- Critical Error processing a block on Page {page_num+1}. ---")
#                 traceback.print_exc() # Print full traceback for better debugging
#                 if i + 1 < len(class_instances):
#                     block_start_y = class_instances[i + 1].y0 - 5
                
#     doc.close()
#     return all_trademarks

## Modified on 8/2/2026 to accept stream input for Flask compatibility
def extract_trademarks_from_pdf(stream):
    """Modified to take a stream (file.read()) for Flask compatibility"""
    doc = fitz.open(stream=stream, filetype="pdf")
    all_trademarks = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        class_instances = sorted(page.search_for("CLASS :"), key=lambda r: r.y0)
        
        block_start_y = 50
        for i in range(len(class_instances)):
            block_end_y = class_instances[i + 1].y0 - 5 if i + 1 < len(class_instances) else page.rect.height
            rect = fitz.Rect(0, block_start_y, page.rect.width, block_end_y)
            
            # 1. Get Text
            text_dict = page.get_text("dict", clip=rect)
            tm_data = parse_trademark_block_text(text_dict.get("blocks", []))
            
            # 2. Get Logo (Directly as bytes)
            # Use your previous extract_logo logic here but return bytes
            pix = page.get_pixmap(clip=rect, dpi=150)
            tm_data['logo_data'] = pix.tobytes("png")
            
            if tm_data['serial_number']:
                all_trademarks.append(tm_data)
            block_start_y = block_end_y
            
    doc.close()
    return all_trademarks

# --- Main Execution Block (for direct testing) ---
if __name__ == '__main__':
    # ... (the testing block remains the same) ...
    pdf_file_path = 'Malaysia Intellectual Property Official Journal.pdf' 
    output_logo_directory = 'extracted_logos'
    
    print(f"Starting trademark extraction from '{pdf_file_path}'...")
    
    extracted_data = extract_trademarks_from_pdf(pdf_file_path, logo_dir=output_logo_directory)
    
    print(f"\nSuccessfully extracted {len(extracted_data)} trademarks.")
    
    # --- Print a few examples to verify the output ---
    for i, tm in enumerate(extracted_data[:5]): # Print the first 5 for verification
        print("\n" + "="*20 + f" TRADEMARK {i+1} " + "="*20)
        print(f"Serial Number: {tm.get('serial_number')}")
        print(f"Registration Date: {tm.get('registration_date')}")
        print(f"Applicant Name: {tm.get('applicant_name')}")
        print(f"Agent Details: {tm.get('agent_details', '')[:100]}...")
        print(f"Logo Filename: {tm.get('logo_filename', 'N/A')}")
        
        if tm.get('classes'):
            print("Classes:")
            for class_info in tm['classes']:
                print(f"  - Class Indices: {class_info['class_indices']}")
                print(f"    Description: {class_info['description'][:100]}...")
        print("="*55)