import fitz
import re
import io

class PerfectExtractor:
    def __init__(self):
        self.pending_tm = None
        self.serial_pattern = re.compile(r"(TM|JV|[A-Z]{2})\d{8,}|^\d{8}$")
        self.class_pattern = re.compile(r"CLASS\s*:\s*([\d,\s]+)", re.IGNORECASE)

    def extract_from_block(self, page, rect):
        doc_dict = page.get_text("dict", clip=rect)
        
        data = {
            'serial_number': None,
            'registration_date': None, 
            'trademark_name': "",      
            'class_indices': "",
            'applicant_name': "",      
            'applicant_address': "",
            'agent_details': "",       
            'description': "",         
            'logo_data': None,
            'evidence_snapshot': None,
            'is_split': False
        }

        data['evidence_snapshot'] = page.get_pixmap(clip=rect, dpi=150).tobytes("png")

        all_spans = []
        for b in doc_dict["blocks"]:
            if "lines" in b:
                for l in b["lines"]:
                    for s in l["spans"]:
                        all_spans.append(s)
        if not all_spans: return None

        # 1. TRADEMARK_NAME - Filter out the "CLASS :" label spans
        header_limit = rect.y0 + (rect.height * 0.45)
        name_spans = [s for s in all_spans if s['bbox'][1] < header_limit and "CLASS" not in s['text'].upper()]
        if name_spans:
            max_font = max(s['size'] for s in name_spans)
            name_parts = [s['text'] for s in name_spans if s['size'] >= (max_font - 0.5)]
            data['trademark_name'] = " ".join(name_parts).strip()

        # 2. IDENTIFY ANCHORS (Serial and Agent)
        all_lines = [s['text'].strip() for s in all_spans if s['text'].strip()]
        
        serial_idx = -1
        agent_idx = -1

        for i, line in enumerate(all_lines):
            # Find Serial Line (Matches your correct date logic)
            if self.serial_pattern.search(line):
                parts = line.split()
                data['serial_number'] = parts[0]
                if len(parts) > 1:
                    data['registration_date'] = " ".join(parts[1:])
                serial_idx = i
            
            # Find Agent Line (Matches your correct agent logic)
            if "AGENT :" in line:
                data['agent_details'] = " ".join(all_lines[i:]).replace("AGENT :", "").strip()
                agent_idx = i
                break # Agent is always the end

        # 3. FIX: APPLICANT NAME & DESCRIPTION
        if serial_idx != -1 and agent_idx != -1:
            # These are the lines that contain Description + Applicant
            body_content = all_lines[serial_idx + 1 : agent_idx]
            
            # WORK BACKWARDS FROM AGENT TO FIND APPLICANT
            # The Applicant block always has a semicolon ';'
            app_start_idx = -1
            for j in range(len(body_content)-1, -1, -1):
                if ";" in body_content[j]:
                    # Found the line with the address/semicolon. 
                    # Now check if the line ABOVE it is also part of the name (usually ALL CAPS)
                    app_start_idx = j
                    while app_start_idx > 0 and body_content[app_start_idx - 1].isupper():
                        app_start_idx -= 1
                    break
            
            if app_start_idx != -1:
                # Extract Applicant info
                applicant_full = " ".join(body_content[app_start_idx:])
                app_split = applicant_full.split(";")
                data['applicant_name'] = app_split[0].strip()
                data['applicant_address'] = app_split[1].strip() if len(app_split) > 1 else ""
                
                # Description is everything BEFORE the applicant start
                data['description'] = " ".join(body_content[:app_start_idx]).strip()
            else:
                # Fallback: if no semicolon, put everything in description
                data['description'] = " ".join(body_content).strip()

        # Final cleanup for description (remove stray serial/date if they repeated)
        if data['serial_number'] and data['serial_number'] in data['description']:
             data['description'] = data['description'].replace(data['serial_number'], "").strip()

        # Preserve Class Index
        class_match = self.class_pattern.search(" ".join(all_lines))
        if class_match:
            data['class_indices'] = class_match.group(1)

        # Logo Crop (Keep as is)
        logo_rect = fitz.Rect(rect.x0, rect.y0, rect.x0 + (rect.width * 0.35), rect.y1)
        data['logo_data'] = page.get_pixmap(clip=logo_rect, dpi=150).tobytes("png")

        return data

    def extract_all(self, pdf_stream):
        doc = fitz.open(stream=pdf_stream, filetype="pdf")
        final_results = []
        for page in doc:
            anchors = sorted(page.search_for("CLASS :"), key=lambda r: r.y0)
            for i in range(len(anchors)):
                start_y = anchors[i].y0 - 15
                end_y = anchors[i+1].y0 - 10 if i+1 < len(anchors) else page.rect.height - 60
                tm_rect = fitz.Rect(0, start_y, page.rect.width, end_y)
                if tm_rect.height < 50: continue
                extracted = self.extract_from_block(page, tm_rect)
                if extracted and extracted['serial_number']:
                    final_results.append(extracted)
        doc.close()
        return final_results

def extract_all(pdf_stream):
    extractor = PerfectExtractor()
    return extractor.extract_all(pdf_stream)


