# pdf_extractor.py
"""
FIXED VERSION: Proper field extraction + logo-only cropping (no left-side text)
+ Logo output: tight crop + transparent bg (PNG)
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
    def __init__(self, image_model_name="clip-ViT-B-32", text_model_name="all-MiniLM-L6-v2"):
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
            return emb.astype("float32")
        except Exception as e:
            print(f"[MLModel] Error generating image embedding: {e}")
            return None

    def generate_text_embedding(self, text):
        try:
            if not text:
                dim = self.text_model.get_sentence_embedding_dimension()
                return np.zeros(dim, dtype="float32")
            emb = self.text_model.encode(text, convert_to_numpy=True, show_progress_bar=False)
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm
            return emb.astype("float32")
        except Exception as e:
            print(f"[MLModel] Error generating text embedding: {e}")
            try:
                dim = self.text_model.get_sentence_embedding_dimension()
                return np.zeros(dim, dtype="float32")
            except Exception:
                return np.zeros(384, dtype="float32")

    def build_logo_index(self, db_fetch_fn):
        if not _HAS_FAISS:
            print("[MLModel] FAISS not installed, skipping index build.")
            return

        db_data = db_fetch_fn()
        ids = db_data.get("ids", [])
        logos = db_data.get("logo", [])

        entries = []
        id_map = []
        for db_id, emb in zip(ids, logos):
            if emb is None:
                continue
            arr = np.asarray(emb, dtype="float32")
            if arr.ndim != 1 or arr.size == 0:
                continue
            faiss.normalize_L2(arr.reshape(1, -1))
            entries.append(arr)
            id_map.append(int(db_id))

        if not entries:
            print("[MLModel] No logo embeddings to index.")
            return

        emb_np = np.vstack(entries).astype("float32")
        dim = emb_np.shape[1]
        index = faiss.IndexFlatIP(dim)
        idmap = faiss.IndexIDMap(index)
        idmap.add_with_ids(emb_np, np.array(id_map).astype("int64"))
        self.logo_index = idmap
        self.id_map = id_map
        print(f"[MLModel] FAISS logo index built with {self.logo_index.ntotal} vectors.")

    def search_logo_index(self, query_embedding, top_k=10):
        if not _HAS_FAISS:
            return [], []
        if self.logo_index is None or self.logo_index.ntotal == 0:
            return [], []

        q = np.asarray(query_embedding, dtype="float32").reshape(1, -1)
        faiss.normalize_L2(q)
        D, I = self.logo_index.search(q, top_k)
        sims = D[0].tolist()
        ids = [int(i) for i in I[0] if i != -1]
        return sims, ids


# -------------------------
# UltraRobustExtractor
# -------------------------
class UltraRobustExtractor:
    def __init__(self, debug=False):
        self.debug = debug
        self.ml = None

        self.serial_pattern = re.compile(r"\b(?:TM|JV|WM|MM|[A-Z]{2})\d{8,12}\b")
        self.date_pattern = re.compile(
            r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
            r"September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b",
            re.IGNORECASE
        )
        self.class_header_pattern = re.compile(r"CLASS\s*:\s*([\d,\s]+)", re.IGNORECASE | re.MULTILINE)
        self.company_kw = ["SDN", "BHD", "LTD", "INC", "PTY", "CORP", "LLC", "PTE", "CO."]

    def log(self, msg):
        if self.debug:
            print(f"[Extractor] {msg}")

    def set_ml_model(self, ml):
        self.ml = ml

    # =====================================================
    # LOGO HELPERS (MUST be inside class)
    # =====================================================
    def tight_crop_by_nonwhite(self, img_bytes: bytes, white_thresh=250, pad=2) -> bytes:
        """Crop to minimal bounding box of non-white pixels."""
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        arr = np.array(img)

        mask = np.any(arr < white_thresh, axis=2)
        if not mask.any():
            return img_bytes

        ys, xs = np.where(mask)
        y0, y1 = ys.min(), ys.max() + 1
        x0, x1 = xs.min(), xs.max() + 1

        x0 = max(0, x0 - pad)
        y0 = max(0, y0 - pad)
        x1 = min(arr.shape[1], x1 + pad)
        y1 = min(arr.shape[0], y1 + pad)

        cropped = img.crop((x0, y0, x1, y1))
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        return buf.getvalue()

    def remove_white_bg_make_transparent(self, png_bytes: bytes, white_thresh=245, soft=15) -> bytes:
        """Make near-white pixels transparent and crop using alpha bbox."""
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        px = img.load()
        w, h = img.size

        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                m = min(r, g, b)

                if m >= white_thresh:
                    px[x, y] = (r, g, b, 0)
                elif m >= white_thresh - soft:
                    alpha = int(255 * (white_thresh - m) / soft)
                    alpha = max(0, min(255, alpha))
                    px[x, y] = (r, g, b, alpha)

        alpha = img.split()[-1]
        bbox = alpha.getbbox()
        if bbox:
            img = img.crop(bbox)

        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()

    # =====================================================
    # LOGO EXTRACTION - ONLY LOGO (tight + transparent)
    # =====================================================
    def extract_logo_only(self, page, block_bbox):
        x0, y0, x1, y1 = block_bbox

        # 1. Targeted Header Area
        # We look at the top 45% of the block. 
        # We capture the left 50% of the page width (where logos live in MYIPO)
        header_height = (y1 - y0) * 0.45
        logo_zone_bbox = (x0, y0, x0 + (x1 - x0) * 0.5, y0 + header_height)

        try:
            # Render at high res to see small details
            header_img = page.within_bbox(logo_zone_bbox).to_image(resolution=300)
            img = header_img.original.convert("RGB")
            arr = np.array(img)
            
            # Find all "ink" pixels
            mask = np.any(arr < 240, axis=2)
            if not mask.any(): return None

            # 2. Grouping Logic
            # Instead of picking one 'blob', find the bounding box of ALL blobs 
            # on the left side. This ensures "LOUIS" and "VUITTON" stay together.
            ys, xs = np.where(mask)
            
            # Crop the original image to the total bounding box of all ink found
            cropped_logo = img.crop((xs.min(), ys.min(), xs.max(), ys.max()))
            
            # Convert to bytes
            buf = io.BytesIO()
            cropped_logo.save(buf, format="PNG")
            logo_bytes = buf.getvalue()

            # Clean background and return
            logo_bytes = self.remove_white_bg_make_transparent(logo_bytes)
            return logo_bytes

        except Exception as e:
            self.log(f"Logo extraction failed: {e}")
            return None

    def get_visual_components(self, img_bytes, white_thresh=250, min_area=120):
        """Find separate visual components. Ignore lines / empty boxes. Prefer dense ink."""
        try:
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        except Exception as e:
            self.log(f"get_visual_components: open failed: {e}")
            return []

        arr = np.array(img)
        mask = np.any(arr < white_thresh, axis=2)
        if not mask.any():
            return []

        components = []

        def accept_component(x, y, w, h, area):
            if area < min_area:
                return False
            if w <= 6 or h <= 6:
                return False
            aspect = w / max(1, h)
            if aspect > 12 or aspect < 0.12:  # ignore horizontal rules / weird tall spikes
                return False
            region = mask[y:y+h, x:x+w]
            ink_ratio = float(region.sum() / max(1, region.size))
            if ink_ratio < 0.02:
                return False
            return True

        if _HAS_CV2:
            try:
                num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
                    (mask.astype("uint8") * 255),
                    connectivity=8
                )
                for i in range(1, num_labels):
                    x, y, w, h, area = stats[i]
                    if not accept_component(x, y, w, h, area):
                        continue

                    region = mask[y:y+h, x:x+w]
                    ink_ratio = float(region.sum() / max(1, region.size))

                    component_img = img.crop((x, y, x + w, y + h))
                    buf = io.BytesIO()
                    component_img.save(buf, format="PNG")

                    components.append({
                        "png": buf.getvalue(),
                        "bbox": (x, y, x + w, y + h),
                        "area": int(area),
                        "ink_ratio": ink_ratio
                    })
            except Exception as e:
                self.log(f"cv2 component detection failed: {e}")

        elif _HAS_NDI:
            try:
                labeled, n = ndi.label(mask)
                for lab in range(1, n + 1):
                    ys, xs = np.where(labeled == lab)
                    if ys.size == 0:
                        continue
                    y0, y1 = ys.min(), ys.max() + 1
                    x0, x1 = xs.min(), xs.max() + 1
                    h = y1 - y0
                    w = x1 - x0
                    area = h * w

                    if not accept_component(x0, y0, w, h, area):
                        continue

                    region = mask[y0:y1, x0:x1]
                    ink_ratio = float(region.sum() / max(1, region.size))

                    component_img = img.crop((x0, y0, x1, y1))
                    buf = io.BytesIO()
                    component_img.save(buf, format="PNG")

                    components.append({
                        "png": buf.getvalue(),
                        "bbox": (x0, y0, x1, y1),
                        "area": int(area),
                        "ink_ratio": ink_ratio
                    })
            except Exception as e:
                self.log(f"scipy component detection failed: {e}")

        if not components:
            # fallback full bbox of all ink
            ys, xs = np.where(mask)
            x0, y0 = xs.min(), ys.min()
            x1, y1 = xs.max() + 1, ys.max() + 1
            component_img = img.crop((x0, y0, x1, y1))
            buf = io.BytesIO()
            component_img.save(buf, format="PNG")
            components.append({
                "png": buf.getvalue(),
                "bbox": (x0, y0, x1, y1),
                "area": int((y1 - y0) * (x1 - x0)),
                "ink_ratio": 1.0
            })

        # Prefer dense ink first, then area
        components.sort(key=lambda c: (c.get("ink_ratio", 0.0), c["area"]), reverse=True)
        return components

    def choose_logo_candidate_BY_AREA(self, components):
        """
        New Logic: Filters out vertical lines and tiny letters.
        Selects the largest remaining visual component.
        """
        valid_candidates = []

        for comp in components:
            # Calculate width and height of this specific component
            bbox = comp["bbox"] # (x0, y0, x1, y1)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            aspect_ratio = w / max(1, h)

            # FILTER 1: Ignore vertical margin lines (extremely tall and thin)
            if aspect_ratio < 0.1 or aspect_ratio > 10:
                continue
            
            # FILTER 2: Ignore tiny noise/letters (Area threshold)
            if comp["area"] < 400:
                continue

            valid_candidates.append(comp)

        if not valid_candidates:
            # Fallback to the first component if nothing matches filters
            return components[0]["png"], None

        # SORT BY AREA: The actual logo is almost always the largest visual item
        valid_candidates.sort(key=lambda x: x["area"], reverse=True)
        
        best_comp = valid_candidates[0]
        
        # Optional: If you still want CLIP, generate embedding for the best one
        best_emb = None
        if self.ml:
            best_emb = self.ml.generate_image_embedding(io.BytesIO(best_comp["png"]))

        return best_comp["png"], best_emb

    # =====================================================
    # FIELD EXTRACTION (same as your current logic)
    # =====================================================
    def parse_fields(self, text, lines):
        fields = {
            "serial_number": None,
            "registration_date": None,
            "trademark_name": "",
            "class_indices": "",
            "applicant_name": "",
            "applicant_address": "",
            "agent_details": "",
            "description": ""
        }

        for line in lines[:15]:
            m = self.serial_pattern.search(line)
            if m:
                fields["serial_number"] = m.group(0)
                dm = self.date_pattern.search(line)
                if dm:
                    fields["registration_date"] = dm.group(0)
                break

        m = self.class_header_pattern.search(text)
        if m:
            fields["class_indices"] = m.group(1).strip()

        for line in lines[:20]:
            if "translation" in line.lower():
                quote_match = re.search(r'["\'](.*?)["\']', line)
                if quote_match:
                    fields["trademark_name"] = quote_match.group(1).strip()
                    break
            elif "transliteration" in line.lower():
                trans_match = re.search(r"transliteration:\s*(.+)", line, re.IGNORECASE)
                if trans_match:
                    name_part = trans_match.group(1)
                    name_part = re.split(r"\s+(?:Registration|The|This|Class)", name_part)[0]
                    fields["trademark_name"] = name_part.strip()
                    break

        agent_idx = len(lines)
        for i, line in enumerate(lines):
            if "AGENT" in line.upper():
                fields["agent_details"] = " ".join(lines[i:]).replace("AGENT :", "").replace("AGENT:", "").strip()
                agent_idx = i
                break

        content_start = 0
        for i, line in enumerate(lines):
            if fields["serial_number"] and fields["serial_number"] in line:
                content_start = i + 1
                break

        body_lines = lines[content_start:agent_idx]
        clean_body = []
        
        for line in body_lines:
            # STOP if we hit a new Serial Number or a new Class header 
            # (This prevents the LV description from including the next company)
            if self.serial_pattern.search(line) and line != fields["serial_number"]:
                break
            if "CLASS :" in line.upper():
                break
            clean_body.append(line)
            
        # Now process clean_body instead of body_lines
        fields["description"] = " ".join(clean_body).strip()

        # Look for applicant in the CLEANED body only
        app_idx = -1
        for j in range(len(clean_body) - 1, -1, -1):
            if ";" in clean_body[j]:
                app_idx = j
                # Applicant names are usually all uppercase in these journals
                while app_idx > 0 and clean_body[app_idx - 1].isupper():
                    app_idx -= 1
                break

        if app_idx == -1:
            for j in range(len(body_lines) - 1, max(0, len(body_lines) - 15), -1):
                if any(kw in body_lines[j].upper() for kw in self.company_kw):
                    app_idx = j
                    if app_idx > 0 and body_lines[app_idx - 1].isupper():
                        app_idx -= 1
                    break

        if app_idx != -1:
            fields["description"] = " ".join(body_lines[:app_idx]).strip()
            applicant_block = " ".join(body_lines[app_idx:]).strip()
            if ";" in applicant_block:
                parts = applicant_block.split(";", 1)
                fields["applicant_name"] = parts[0].strip()
                fields["applicant_address"] = parts[1].strip() if len(parts) > 1 else ""
            else:
                fields["applicant_name"] = applicant_block
        else:
            fields["description"] = " ".join(body_lines).strip()

        desc = fields["description"]

        if not fields["trademark_name"] and desc:
            match = re.search(r'Mark\s+translation:\s*["\']([^"\']+)["\']', desc)
            if match:
                fields["trademark_name"] = match.group(1).strip()
            else:
                match = re.search(r"Mark\s+transliteration:\s*([A-Za-z\s]+?)(?=\s*[A-Z]|\.|$)", desc)
                if match:
                    fields["trademark_name"] = match.group(1).strip()

        desc = re.sub(r"Mark\s+translation:[^\.]+\.\s*", "", desc)
        desc = re.sub(r"Mark\s+transliteration:[^\.]+\.\s*", "", desc)
        desc = re.sub(r"Mark\s+translation:[^A-Z]+", "", desc)
        desc = re.sub(r"Mark\s+transliteration:[^A-Z]+", "", desc)

        desc = re.sub(r"Registration of this trademark[^\.]+\.", "", desc, flags=re.IGNORECASE)

        if fields["serial_number"]:
            desc = desc.replace(fields["serial_number"], "")
        if fields["registration_date"]:
            desc = desc.replace(fields["registration_date"], "")

        desc = re.sub(r"CLASS\s*:\s*[\d,\s]+", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\bCLASS\s+\d+\b", "", desc)

        desc = re.sub(r"\s+", " ", desc).strip()
        desc = desc.lstrip(";:,. ")
        fields["description"] = desc

        score = 0.0
        if fields["serial_number"]:
            score += 0.25
        if fields["registration_date"]:
            score += 0.10
        if fields["class_indices"]:
            score += 0.15
        if fields["applicant_name"]:
            score += 0.20
        if fields["agent_details"]:
            score += 0.10
        if len(fields["description"]) > 50:
            score += 0.20

        return fields, score

    # =====================================================
    # BLOCK DETECTION
    # =====================================================
    def find_blocks(self, page):
        words = page.extract_words()
        h = page.height
        w = page.width

        lines = {}
        for word in words:
            y = round(word["top"], 1)
            lines.setdefault(y, []).append(word)

        class_ys = []
        for y, ws in sorted(lines.items()):
            txt = " ".join(w["text"] for w in ws)
            if re.match(r"^\s*CLASS\s*:\s*[\d,\s]+\s*$", txt, re.IGNORECASE):
                class_ys.append(y)

        agent_ys = []
        for y, ws in sorted(lines.items()):
            txt = " ".join(w["text"] for w in ws)
            if txt.strip().upper().startswith("AGENT"):
                agent_ys.append(y)

        if not class_ys:
            return []

        blocks = []
        for cy in class_ys:
            prev_agent = None
            for ay in agent_ys:
                if ay < cy:
                    prev_agent = ay

            curr_agent = None
            for ay in agent_ys:
                if ay > cy:
                    curr_agent = ay
                    break

            y0 = (prev_agent + 25) if prev_agent else max(cy - 120, 50)
            y1 = (curr_agent + 15) if curr_agent else h - 60

            if y1 - y0 > 100:
                blocks.append({"bbox": (0, y0, w, y1), "class_y": cy})

        return blocks

    def extract_from_block(self, page, block_info, page_num):
        bbox = block_info["bbox"]

        block_page = page.within_bbox(bbox)
        text = block_page.extract_text()
        if not text:
            return None

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        fields, completeness = self.parse_fields(text, lines)

        if not fields["serial_number"]:
            self.log("❌ No serial number - skipping")
            return None

        logo_data = self.extract_logo_only(page, bbox)

        logo_emb = None
        if logo_data and self.ml:
            try:
                logo_emb = self.ml.generate_image_embedding(io.BytesIO(logo_data))
            except Exception as e:
                self.log(f"Logo embedding failed: {e}")

        try:
            block_img = block_page.to_image(resolution=150)
            buf = io.BytesIO()
            block_img.original.save(buf, format="PNG")
            snapshot = buf.getvalue()
        except Exception:
            snapshot = None

        text_emb = None
        if self.ml:
            try:
                combined_text = f"{fields['trademark_name']} {fields['description']}"
                text_emb = self.ml.generate_text_embedding(combined_text)
            except Exception as e:
                self.log(f"Text embedding failed: {e}")

        result = {
            "page_number": page_num,
            "serial_number": fields["serial_number"],
            "registration_date": fields["registration_date"],
            "trademark_name": fields["trademark_name"],
            "class_indices": fields["class_indices"],
            "applicant_name": fields["applicant_name"],
            "applicant_address": fields["applicant_address"],
            "agent_details": fields["agent_details"],
            "description": fields["description"],
            "logo_data": logo_data,
            "logo_embedding": logo_emb,
            "text_embedding": text_emb,
            "block_snapshot": snapshot,
            "completeness": completeness
        }

        return result

    def extract_all(self, pdf_stream, start_page=9):
        results = []
        with pdfplumber.open(pdf_stream) as pdf:
            for pnum, page in enumerate(pdf.pages[start_page - 1:], start=start_page):
                try:
                    blocks = self.find_blocks(page)
                    for block in blocks:
                        data = self.extract_from_block(page, block, pnum)
                        if data:
                            results.append(data)
                except Exception as e:
                    self.log(f"❌ Page {pnum} failed: {e}")
        return results


# -------------------------
# Convenience function for Flask
# -------------------------
def extract_all(pdf_stream, debug=False):
    extractor = UltraRobustExtractor(debug=debug)
    # Ensure it starts from page 1 or the standard MYIPO journal start page
    return extractor.extract_all(pdf_stream, start_page=4)