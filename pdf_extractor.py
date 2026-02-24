# ultra_robust_extractor_fixed.py
"""
FIXED VERSION: Proper field extraction + logo-only cropping (no left-side text)
"""

import io
import os
import re
import numpy as np
from PIL import Image
import pdfplumber

# Optional dependencies
try:
    import cv2
    _HAS_CV2 = True
except Exception:
    cv2 = None
    _HAS_CV2 = False

try:
    import scipy.ndimage as ndi
    _HAS_NDI = True
except Exception:
    ndi = None
    _HAS_NDI = False

try:
    import faiss
    _HAS_FAISS = True
except Exception:
    faiss = None
    _HAS_FAISS = False

try:
    from sentence_transformers import SentenceTransformer
    _HAS_SENTE_TRANS = True
except Exception:
    SentenceTransformer = None
    _HAS_SENTE_TRANS = False

# -------------------------
# MLModel
# -------------------------
class MLModel:
    def __init__(self, image_model_name='clip-ViT-B-32', text_model_name='all-MiniLM-L6-v2'):
        print("Loading ML models...")
        if not _HAS_SENTE_TRANS:
            raise RuntimeError("sentence_transformers not installed")
        self.image_model = SentenceTransformer(image_model_name)
        self.text_model = SentenceTransformer(text_model_name)
        self.logo_index = None
        self.id_map = []
        print("ML models loaded successfully.")

    def generate_image_embedding(self, image_file_stream):
        try:
            if isinstance(image_file_stream, (bytes, bytearray)):
                image = Image.open(io.BytesIO(image_file_stream)).convert("RGB")
            elif hasattr(image_file_stream, "read"):
                image = Image.open(image_file_stream).convert("RGB")
            else:
                image = Image.open(image_file_stream).convert("RGB")

            emb = self.image_model.encode([image], convert_to_numpy=True, show_progress_bar=False)[0]
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm
            return emb.astype('float32')
        except Exception as e:
            print(f"[MLModel] Error generating image embedding: {e}")
            return None

    def generate_text_embedding(self, text):
        try:
            if not text:
                dim = self.text_model.get_sentence_embedding_dimension()
                return np.zeros(dim, dtype='float32')
            emb = self.text_model.encode(text, convert_to_numpy=True, show_progress_bar=False)
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm
            return emb.astype('float32')
        except Exception as e:
            print(f"[MLModel] Error generating text embedding: {e}")
            try:
                dim = self.text_model.get_sentence_embedding_dimension()
                return np.zeros(dim, dtype='float32')
            except Exception:
                return np.zeros(384, dtype='float32')

    def build_logo_index(self, db_fetch_fn):
        if not _HAS_FAISS:
            print("[MLModel] FAISS not installed, skipping index build.")
            return

        db_data = db_fetch_fn()
        ids = db_data.get('ids', [])
        logos = db_data.get('logo', [])

        entries = []
        id_map = []
        for db_id, emb in zip(ids, logos):
            if emb is None:
                continue
            arr = np.asarray(emb, dtype='float32')
            if arr.ndim != 1 or arr.size == 0:
                continue
            faiss.normalize_L2(arr.reshape(1, -1))
            entries.append(arr)
            id_map.append(int(db_id))

        if not entries:
            print("[MLModel] No logo embeddings to index.")
            return

        emb_np = np.vstack(entries).astype('float32')
        dim = emb_np.shape[1]
        index = faiss.IndexFlatIP(dim)
        idmap = faiss.IndexIDMap(index)
        idmap.add_with_ids(emb_np, np.array(id_map).astype('int64'))
        self.logo_index = idmap
        self.id_map = id_map
        print(f"[MLModel] FAISS logo index built with {self.logo_index.ntotal} vectors.")

    def search_logo_index(self, query_embedding, top_k=10):
        if not _HAS_FAISS:
            return [], []
        if self.logo_index is None or self.logo_index.ntotal == 0:
            return [], []

        q = np.asarray(query_embedding, dtype='float32').reshape(1, -1)
        faiss.normalize_L2(q)
        D, I = self.logo_index.search(q, top_k)
        sims = D[0].tolist()
        ids = [int(i) for i in I[0] if i != -1]
        return sims, ids


# -------------------------
# UltraRobustExtractor - FIXED VERSION
# -------------------------
class UltraRobustExtractor:
    def __init__(self, debug=False):
        self.debug = debug
        self.ml = None
        
        # Patterns
        self.serial_pattern = re.compile(r'\b(?:TM|JV|WM|MM|[A-Z]{2})\d{8,12}\b')
        self.date_pattern = re.compile(
            r'\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|'
            r'September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b',
            re.IGNORECASE
        )
        self.class_header_pattern = re.compile(r'CLASS\s*:\s*([\d,\s]+)', re.IGNORECASE | re.MULTILINE)
        self.company_kw = ['SDN', 'BHD', 'LTD', 'INC', 'PTY', 'CORP', 'LLC', 'PTE', 'CO.']

    def log(self, msg):
        if self.debug:
            print(f"[Extractor] {msg}")

    def set_ml_model(self, ml):
        self.ml = ml

    # =====================================================
    # LOGO EXTRACTION - ONLY LOGO, NO TEXT
    # =====================================================
    
    def extract_logo_only(self, page, block_bbox):
        """
        Extract ONLY the logo graphic, excluding all text.
        Uses visual component detection + ML scoring.
        """
        x0, y0, x1, y1 = block_bbox
        
        # Render the header area (top 40% of block)
        header_height = (y1 - y0) * 0.4
        header_bbox = (x0, y0, x1, y0 + header_height)
        
        try:
            header_img = page.within_bbox(header_bbox).to_image(resolution=200)
            buf = io.BytesIO()
            header_img.original.save(buf, format='PNG')
            raw_img_bytes = buf.getvalue()
        except Exception as e:
            self.log(f"Logo render failed: {e}")
            return None
        
        # Get visual components
        components = self.get_visual_components(raw_img_bytes, white_thresh=250, min_area=200)
        
        if not components:
            self.log("No visual components found")
            return None
        
        # Choose best logo candidate
        logo_bytes, logo_emb = self.choose_logo_candidate(components, top_n=3)
        
        return logo_bytes
    
    def get_visual_components(self, img_bytes, white_thresh=250, min_area=200):
        """Find separate visual components (logo parts) in image"""
        try:
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        except Exception as e:
            self.log(f"get_visual_components: open failed: {e}")
            return []

        arr = np.array(img)
        # Mask of non-white pixels
        mask = np.any(arr < white_thresh, axis=2)
        
        if not mask.any():
            return []

        components = []
        
        # Try OpenCV first (fastest)
        if _HAS_CV2:
            try:
                num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
                    (mask.astype('uint8') * 255), connectivity=8
                )
                for i in range(1, num_labels):  # Skip background (label 0)
                    x, y, w, h, area = stats[i]
                    if area < min_area:
                        continue
                    
                    # Crop this component
                    component_img = img.crop((x, y, x+w, y+h))
                    buf = io.BytesIO()
                    component_img.save(buf, format='PNG')
                    
                    components.append({
                        'png': buf.getvalue(),
                        'bbox': (x, y, x+w, y+h),
                        'area': int(area)
                    })
            except Exception as e:
                self.log(f"cv2 component detection failed: {e}")
        
        # Fallback: scipy
        elif _HAS_NDI:
            try:
                labeled, n = ndi.label(mask)
                for lab in range(1, n+1):
                    ys, xs = np.where(labeled == lab)
                    if ys.size == 0:
                        continue
                    
                    y0, y1 = ys.min(), ys.max()+1
                    x0, x1 = xs.min(), xs.max()+1
                    area = (y1-y0) * (x1-x0)
                    
                    if area < min_area:
                        continue
                    
                    component_img = img.crop((x0, y0, x1, y1))
                    buf = io.BytesIO()
                    component_img.save(buf, format='PNG')
                    
                    components.append({
                        'png': buf.getvalue(),
                        'bbox': (x0, y0, x1, y1),
                        'area': int(area)
                    })
            except Exception as e:
                self.log(f"scipy component detection failed: {e}")
        
        # Last resort: use entire non-white area
        if not components:
            ys, xs = np.where(mask)
            if ys.size > 0:
                x0, y0 = xs.min(), ys.min()
                x1, y1 = xs.max()+1, ys.max()+1
                component_img = img.crop((x0, y0, x1, y1))
                buf = io.BytesIO()
                component_img.save(buf, format='PNG')
                components.append({
                    'png': buf.getvalue(),
                    'bbox': (x0, y0, x1, y1),
                    'area': int((y1-y0) * (x1-x0))
                })
        
        # Sort by area (largest first)
        components.sort(key=lambda c: c['area'], reverse=True)
        return components
    
    def choose_logo_candidate(self, components, top_n=3):
        """
        Choose best logo from components using ML embedding comparison.
        Returns (png_bytes, embedding)
        """
        if not components:
            return None, None
        
        # If no ML model, return largest component
        if not self.ml:
            largest = components[0]
            trimmed = self.trim_whitespace(largest['png'])
            return trimmed, None
        
        # Test top N components
        candidates = components[:min(top_n, len(components))]
        
        # Logo anchor text
        logo_anchor_text = "logo emblem trademark symbol wordmark brand mark"
        anchor_emb = self.ml.generate_text_embedding(logo_anchor_text)
        
        best_png = None
        best_emb = None
        best_score = -1.0
        
        for comp in candidates:
            # Trim this component
            trimmed_png = self.trim_whitespace(comp['png'])
            
            # Generate image embedding
            comp_emb = self.ml.generate_image_embedding(io.BytesIO(trimmed_png))
            
            if comp_emb is None or anchor_emb is None:
                continue
            
            # Score: similarity to "logo" concept
            score = float(np.dot(comp_emb, anchor_emb))
            
            if score > best_score:
                best_score = score
                best_png = trimmed_png
                best_emb = comp_emb
        
        # Fallback: largest component
        if best_png is None:
            best_png = self.trim_whitespace(candidates[0]['png'])
            if self.ml:
                best_emb = self.ml.generate_image_embedding(io.BytesIO(best_png))
        
        return best_png, best_emb
    
    def trim_whitespace(self, img_bytes, white_thresh=250, pad=5):
        """Remove all whitespace, keeping only content with minimal padding"""
        try:
            img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
            arr = np.array(img)
            
            # Find non-white pixels
            mask = np.any(arr < white_thresh, axis=2)
            
            if not mask.any():
                return img_bytes
            
            coords = np.argwhere(mask)
            y0, x0 = coords.min(axis=0)
            y1, x1 = coords.max(axis=0)
            
            # Add minimal padding
            y0 = max(0, y0 - pad)
            x0 = max(0, x0 - pad)
            y1 = min(arr.shape[0], y1 + pad + 1)
            x1 = min(arr.shape[1], x1 + pad + 1)
            
            # Crop
            cropped = img.crop((x0, y0, x1, y1))
            
            # Make white transparent
            cropped_rgba = cropped.convert('RGBA')
            data = np.array(cropped_rgba)
            
            # Set white pixels to transparent
            white_mask = (data[:,:,0] >= white_thresh) & \
                        (data[:,:,1] >= white_thresh) & \
                        (data[:,:,2] >= white_thresh)
            data[white_mask, 3] = 0
            
            result = Image.fromarray(data, 'RGBA')
            buf = io.BytesIO()
            result.save(buf, format='PNG')
            
            return buf.getvalue()
            
        except Exception as e:
            self.log(f"trim_whitespace failed: {e}")
            return img_bytes

    # =====================================================
    # FIELD EXTRACTION - PROPER SEPARATION
    # =====================================================
    
    def parse_fields(self, text, lines):
        """
        Parse fields correctly - don't put everything in trademark_name!
        """
        fields = {
            'serial_number': None,
            'registration_date': None,
            'trademark_name': "",
            'class_indices': "",
            'applicant_name': "",
            'applicant_address': "",
            'agent_details': "",
            'description': ""
        }

        # === 1. SERIAL NUMBER & DATE ===
        for line in lines[:15]:
            m = self.serial_pattern.search(line)
            if m:
                fields['serial_number'] = m.group(0)
                # Date is often on same line as serial
                dm = self.date_pattern.search(line)
                if dm:
                    fields['registration_date'] = dm.group(0)
                break
        
        # === 2. CLASS INDICES ===
        m = self.class_header_pattern.search(text)
        if m:
            fields['class_indices'] = m.group(1).strip()

        # === 3. TRADEMARK NAME (from translation/transliteration) ===
        # First try: quoted text in translation lines
        for line in lines[:20]:
            if 'translation' in line.lower():
                # Look for quoted text
                quote_match = re.search(r'["\'](.*?)["\']', line)
                if quote_match:
                    fields['trademark_name'] = quote_match.group(1).strip()
                    break
            elif 'transliteration' in line.lower():
                # Transliteration usually follows "transliteration:"
                trans_match = re.search(r'transliteration:\s*(.+)', line, re.IGNORECASE)
                if trans_match:
                    # Take text until we hit "Registration" or similar
                    name_part = trans_match.group(1)
                    name_part = re.split(r'\s+(?:Registration|The|This|Class)', name_part)[0]
                    fields['trademark_name'] = name_part.strip()
                    break

        # === 4. AGENT (always at the end) ===
        agent_idx = len(lines)
        for i, line in enumerate(lines):
            if 'AGENT' in line.upper():
                fields['agent_details'] = ' '.join(lines[i:]).replace('AGENT :', '').replace('AGENT:', '').strip()
                agent_idx = i
                break

        # === 5. FIND CONTENT START (after serial line) ===
        content_start = 0
        for i, line in enumerate(lines):
            if fields['serial_number'] and fields['serial_number'] in line:
                content_start = i + 1
                break

        # === 6. BODY CONTENT (between serial and agent) ===
        body_lines = lines[content_start:agent_idx]

        if not body_lines:
            return fields, 0.4

        # === 7. SEPARATE APPLICANT FROM DESCRIPTION ===
        # Look for company keywords or semicolon (address separator)
        app_idx = -1
        
        # Search backwards for applicant
        for j in range(len(body_lines)-1, -1, -1):
            line = body_lines[j]
            
            # Check for semicolon (address separator)
            if ';' in line:
                app_idx = j
                # Include previous ALL CAPS lines (company name)
                while app_idx > 0 and body_lines[app_idx-1].isupper():
                    app_idx -= 1
                break
        
        # Fallback: look for company keywords
        if app_idx == -1:
            for j in range(len(body_lines)-1, max(0, len(body_lines)-15), -1):
                if any(kw in body_lines[j].upper() for kw in self.company_kw):
                    app_idx = j
                    if app_idx > 0 and body_lines[app_idx-1].isupper():
                        app_idx -= 1
                    break

        # Extract based on found applicant position
        if app_idx != -1:
            # DESCRIPTION is everything BEFORE applicant
            fields['description'] = ' '.join(body_lines[:app_idx]).strip()
            
            # APPLICANT is from app_idx to end
            applicant_block = ' '.join(body_lines[app_idx:]).strip()
            
            if ';' in applicant_block:
                parts = applicant_block.split(';', 1)
                fields['applicant_name'] = parts[0].strip()
                fields['applicant_address'] = parts[1].strip() if len(parts) > 1 else ""
            else:
                fields['applicant_name'] = applicant_block
        else:
            # Couldn't separate - put everything in description
            fields['description'] = ' '.join(body_lines).strip()

        # === 8. CLEAN DESCRIPTION AND EXTRACT NAME IF NEEDED ===
        desc = fields['description']
        
        # Extract trademark name from description if not already found
        # PREFER translation over transliteration
        if not fields['trademark_name'] and desc:
            # Pattern 1: Mark translation: "text" (HIGHEST PRIORITY)
            match = re.search(r'Mark\s+translation:\s*["\']([^"\']+)["\']', desc)
            if match:
                fields['trademark_name'] = match.group(1).strip()
            else:
                # Pattern 2: Mark transliteration: text (fallback)
                match = re.search(r'Mark\s+transliteration:\s*([A-Za-z\s]+?)(?=\s*[A-Z]|\.|$)', desc)
                if match:
                    fields['trademark_name'] = match.group(1).strip()
        
        # Remove ALL translation/transliteration content
        # This regex removes everything from "Mark translation" until the next capital letter word
        desc = re.sub(r'Mark\s+translation:[^\.]+\.\s*', '', desc)
        desc = re.sub(r'Mark\s+transliteration:[^\.]+\.\s*', '', desc)
        # Also remove partial matches without periods
        desc = re.sub(r'Mark\s+translation:[^A-Z]+', '', desc)
        desc = re.sub(r'Mark\s+transliteration:[^A-Z]+', '', desc)
        
        # Remove registration notice lines
        desc = re.sub(r'Registration of this trademark[^\.]+\.', '', desc, flags=re.IGNORECASE)
        
        # Remove any stray serial numbers and dates
        if fields['serial_number']:
            desc = desc.replace(fields['serial_number'], '')
        if fields['registration_date']:
            desc = desc.replace(fields['registration_date'], '')
        
        # Remove CLASS headers
        desc = re.sub(r'CLASS\s*:\s*[\d,\s]+', '', desc, flags=re.IGNORECASE)
        desc = re.sub(r'\bCLASS\s+\d+\b', '', desc)
        
        # Clean up excessive whitespace
        desc = re.sub(r'\s+', ' ', desc).strip()
        # Remove leading punctuation and whitespace
        desc = desc.lstrip(';:,. ')
        
        fields['description'] = desc

        # === 9. COMPLETENESS SCORE ===
        score = 0.0
        if fields['serial_number']: score += 0.25
        if fields['registration_date']: score += 0.10
        if fields['class_indices']: score += 0.15
        if fields['applicant_name']: score += 0.20
        if fields['agent_details']: score += 0.10
        if len(fields['description']) > 50: score += 0.20

        return fields, score

    # =====================================================
    # BLOCK DETECTION & EXTRACTION
    # =====================================================
    
    def find_blocks(self, page):
        """Find trademark blocks using CLASS and AGENT markers"""
        words = page.extract_words()
        h = page.height
        w = page.width
        
        lines = {}
        for word in words:
            y = round(word['top'], 1)
            lines.setdefault(y, []).append(word)

        # Find CLASS : headers
        class_ys = []
        for y, ws in sorted(lines.items()):
            txt = ' '.join(w['text'] for w in ws)
            if re.match(r'^\s*CLASS\s*:\s*[\d,\s]+\s*$', txt, re.IGNORECASE):
                class_ys.append(y)

        # Find AGENT : lines
        agent_ys = []
        for y, ws in sorted(lines.items()):
            txt = ' '.join(w['text'] for w in ws)
            if txt.strip().upper().startswith('AGENT'):
                agent_ys.append(y)

        if not class_ys:
            return []

        blocks = []
        for i, cy in enumerate(class_ys):
            # Find previous AGENT
            prev_agent = None
            for ay in agent_ys:
                if ay < cy:
                    prev_agent = ay
            
            # Find current AGENT
            curr_agent = None
            for ay in agent_ys:
                if ay > cy:
                    curr_agent = ay
                    break
            
            y0 = (prev_agent + 25) if prev_agent else max(cy - 120, 50)
            y1 = (curr_agent + 15) if curr_agent else h - 60
            
            if y1 - y0 > 100:
                blocks.append({'bbox': (0, y0, w, y1), 'class_y': cy})
        
        return blocks

    def extract_from_block(self, page, block_info, page_num):
        """Extract trademark data from a single block"""
        bbox = block_info['bbox']
        
        # Extract text
        block_page = page.within_bbox(bbox)
        text = block_page.extract_text()
        
        if not text:
            return None
        
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Parse all fields
        fields, completeness = self.parse_fields(text, lines)
        
        # Must have serial number
        if not fields['serial_number']:
            self.log("❌ No serial number - skipping")
            return None
        
        # Extract logo (ONLY the graphic, no text)
        logo_data = self.extract_logo_only(page, bbox)
        
        # Generate embedding if ML model available
        logo_emb = None
        if logo_data and self.ml:
            try:
                logo_emb = self.ml.generate_image_embedding(io.BytesIO(logo_data))
            except Exception as e:
                self.log(f"Logo embedding failed: {e}")
        
        # Block snapshot
        try:
            block_img = block_page.to_image(resolution=150)
            buf = io.BytesIO()
            block_img.original.save(buf, format='PNG')
            snapshot = buf.getvalue()
        except:
            snapshot = None
        
        # Generate text embedding
        text_emb = None
        if self.ml:
            try:
                combined_text = f"{fields['trademark_name']} {fields['description']}"
                text_emb = self.ml.generate_text_embedding(combined_text)
            except Exception as e:
                self.log(f"Text embedding failed: {e}")
        
        result = {
            'page_number': page_num,
            'serial_number': fields['serial_number'],
            'registration_date': fields['registration_date'],
            'trademark_name': fields['trademark_name'],
            'class_indices': fields['class_indices'],
            'applicant_name': fields['applicant_name'],
            'applicant_address': fields['applicant_address'],
            'agent_details': fields['agent_details'],
            'description': fields['description'],
            'logo_data': logo_data,
            'logo_embedding': logo_emb,
            'text_embedding': text_emb,
            'block_snapshot': snapshot,
            'completeness': completeness
        }
        
        if completeness < 0.7:
            self.log(f"⚠️  {fields['serial_number']}: {completeness*100:.0f}% complete")
        else:
            self.log(f"✅ {fields['serial_number']}: {completeness*100:.0f}% complete")
        
        return result

    def extract_all(self, pdf_stream, start_page=9):
        """Extract all trademarks from PDF"""
        results = []
        
        with pdfplumber.open(pdf_stream) as pdf:
            total = len(pdf.pages)
            self.log(f"📚 Processing {total} pages starting from page {start_page}")
            
            for pnum, page in enumerate(pdf.pages[start_page-1:], start=start_page):
                self.log(f"\n{'='*60}\n📄 Page {pnum}\n{'='*60}")
                
                try:
                    blocks = self.find_blocks(page)
                    
                    for block in blocks:
                        try:
                            data = self.extract_from_block(page, block, pnum)
                            if data:
                                results.append(data)
                        except Exception as e:
                            self.log(f"❌ Block extraction failed: {e}")
                            
                except Exception as e:
                    self.log(f"❌ Page {pnum} failed: {e}")
        
        self.log(f"\n{'='*60}")
        self.log(f"✅ Extracted {len(results)} trademarks")
        
        incomplete = [r for r in results if r['completeness'] < 0.7]
        if incomplete:
            self.log(f"⚠️  {len(incomplete)} incomplete records")
        
        return results


# -------------------------
# Convenience function for Flask
# -------------------------
def extract_all(pdf_stream, debug=False):
    """Main entry point for Flask integration"""
    extractor = UltraRobustExtractor(debug=debug)
    return extractor.extract_all(pdf_stream)


# -------------------------
# CLI usage
# -------------------------
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python ultra_robust_extractor_fixed.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    
    # Optional: Initialize ML model
    try:
        print("Initializing ML model...")
        ml = MLModel()
        
        extractor = UltraRobustExtractor(debug=True)
        extractor.set_ml_model(ml)
    except Exception as e:
        print(f"ML model init failed: {e}, continuing without ML")
        extractor = UltraRobustExtractor(debug=True)

    results = extractor.extract_all(pdf_path, start_page=9)
    
    print(f"\n{'='*60}")
    print(f"📊 SUMMARY")
    print(f"{'='*60}")
    print(f"Total extracted: {len(results)}")
    
    if results:
        avg_completeness = sum(r['completeness'] for r in results) / len(results)
        print(f"Avg completeness: {avg_completeness*100:.1f}%")
        
        with_logos = sum(1 for r in results if r['logo_data'])
        print(f"With logos: {with_logos}/{len(results)}")
        
        # Save logos for inspection
        outdir = "extracted_logos"
        os.makedirs(outdir, exist_ok=True)
        for i, r in enumerate(results[:5]):  # Save first 5
            if r.get('logo_data'):
                fname = os.path.join(outdir, f"logo_{r['serial_number']}.png")
                try:
                    with open(fname, 'wb') as f:
                        f.write(r['logo_data'])
                    print(f"✓ Saved {fname}")
                except Exception as e:
                    print(f"✗ Error saving {fname}: {e}")