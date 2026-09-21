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
# YOLO logo detector
try:
    from ultralytics import YOLO
    _HAS_YOLO = True
except Exception:
    YOLO = None
    _HAS_YOLO = False

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

# Progress bar for extraction
try:
    from tqdm import tqdm
    _HAS_TQDM = True
except ImportError:
    _HAS_TQDM = False

try:
    from paddleocr import PaddleOCR
    _HAS_PADDLEOCR = True
except Exception:
    PaddleOCR = None
    _HAS_PADDLEOCR = False

_block_ocr_engine = None


def _get_block_ocr_engine():
    """Lazy PaddleOCR engine for the block-level OCR cross-validation
    check (see UltraRobustExtractor.validate_fields_with_ocr) - kept
    separate from similarity.py's engine (medium, already eval-validated
    for the Compare feature's font-mismatch guard) so this never risks
    that. Uses the TINY model: measured 32.5x faster than medium with
    byte-identical text output on every one of 16 real field crops tested
    - no accuracy tradeoff found for this kind of short-line/label read."""
    global _block_ocr_engine
    if _block_ocr_engine is None:
        if not _HAS_PADDLEOCR:
            _block_ocr_engine = False
        else:
            try:
                _block_ocr_engine = PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    enable_mkldnn=False,
                    text_detection_model_name="PP-OCRv6_tiny_det",
                    text_recognition_model_name="PP-OCRv6_tiny_rec",
                )
            except Exception:
                _block_ocr_engine = False
    return _block_ocr_engine


def _normalize_for_ocr_check(text):
    return re.sub(r'[^A-Z0-9]', '', (text or "").upper())


def _field_found_in_ocr(field_value, ocr_blob_normalized, min_word_len=3, min_fraction=0.6):
    """Fuzzy 'is this field's value actually present in the OCR'd block
    text' check - word-level containment rather than an exact substring
    match, since OCR line-wrapping/spacing differs from how pdfplumber
    joins lines. Only checks words of min_word_len+ characters (short
    tokens like "OF"/"NO" are too common to be meaningful evidence either
    way).

    Tokenize the ORIGINAL field value first, THEN normalize each token -
    not the other way around. Normalizing the whole string first strips
    every space, so re.findall on it returns one giant word instead of
    real tokens (verified: this exact bug produced a false-positive
    "not found" warning on a genuinely correct, cleanly-OCR'd agent field
    - the concatenated field-value "word" obviously never matched
    anything in the OCR blob)."""
    words = [w.upper() for w in re.findall(r'[A-Za-z0-9]{%d,}' % min_word_len, field_value or "")]
    if not words:
        return True  # nothing meaningful to check - don't flag it
    found = sum(1 for w in words if w in ocr_blob_normalized)
    return (found / len(words)) >= min_fraction

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
    def __init__(self, debug=False, yolo_model_path="models/best_colab2.pt", enable_ocr_validation=True):
        self.debug = debug
        self.ml = None
        # OCR cross-validation safety net (see validate_fields_with_ocr) -
        # cheap with the tiny model (measured ~0.2-0.3s/block worth of
        # text), on by default; pass False to skip it entirely.
        self.enable_ocr_validation = enable_ocr_validation

        # Prefix (TM, JV, etc.) is OPTIONAL - plenty of real serial numbers in
        # this journal are bare digits with no letter prefix at all (e.g.
        # "07025604", "2016062700"), and the old prefix-required version
        # silently dropped every one of those entries rather than just
        # mislabeling them. Bounded to the first 15 lines of a block (see
        # parse_fields) and to 8-12 digits, which keeps this from matching
        # shorter numbers like postal codes.
        self.serial_pattern = re.compile(r"\b(?:TM|JV|WM|MM|[A-Z]{2})?\d{8,12}\b")
        self.date_pattern = re.compile(
            r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
            r"September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b",
            re.IGNORECASE
        )
        # Capture group excludes \n/\r deliberately - [\d,\s]+ used to
        # match across the line break into the NEXT line's serial number
        # (e.g. real text "CLASS : 34\n2015002306 27 February 2015" was
        # captured as class_indices "34\n2015002306 27", silently
        # absorbing the serial number's leading digits). [ \t\d,]+ stays
        # on the CLASS line only.
        self.class_header_pattern = re.compile(r"CLASS\s*:\s*([ \t\d,]+)", re.IGNORECASE | re.MULTILINE)
        # Only present on Madrid Protocol / international-route filings -
        # absent on domestic filings, which is expected, not an error.
        self.intl_reg_number_pattern = re.compile(
            r"International\s+Registration\s+Number\s*:?\s*([\w./-]+)", re.IGNORECASE
        )
        self.intl_reg_date_pattern = re.compile(
            r"International\s+Registration\s+Date\s*:?\s*"
            r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
            r"September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})",
            re.IGNORECASE,
        )
        self.company_kw = ["SDN", "BHD", "LTD", "INC", "PTY", "CORP", "LLC", "PTE", "CO."]
        # -------------------------
        # YOLO LOGO DETECTOR
        # -------------------------
        self.yolo = None

        if _HAS_YOLO and os.path.exists(yolo_model_path):
            try:
                self.yolo = YOLO(yolo_model_path)
                print(f"[Extractor] YOLO model loaded: {yolo_model_path}")
            except Exception as e:
                print(f"[Extractor] YOLO failed to load: {e}")

    def log(self, msg):
        if self.debug:
            print(f"[Extractor] {msg}")

    def set_ml_model(self, ml):
        self.ml = ml

    def validate_fields_with_ocr(self, snapshot_bytes, fields):
        """Cross-checks the text-layer-extracted field VALUES against an
        independent OCR read of the same block image. The text layer
        (pdfplumber) is still authoritative - it reads exact embedded PDF
        text, no recognition risk - this exists purely to catch a
        DIFFERENT class of bug: find_blocks()'s boundary logic grabbing
        the wrong region entirely, which the text layer would then read
        perfectly accurately but for the WRONG field. Returns a list of
        warning strings (empty if everything checks out, OCR wasn't
        available, or validation is disabled)."""
        if not self.enable_ocr_validation or not (_HAS_CV2 and snapshot_bytes):
            return []
        engine = _get_block_ocr_engine()
        if not engine:
            return []

        try:
            img = cv2.imdecode(np.frombuffer(snapshot_bytes, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return []
            ocr_words = []
            for res in engine.predict(img):
                texts  = res.get('rec_texts')  or []
                scores = res.get('rec_scores') or []
                ocr_words.extend(t for t, s in zip(texts, scores) if s >= 0.5)
            ocr_blob = _normalize_for_ocr_check(" ".join(ocr_words))
        except Exception as e:
            self.log(f"OCR cross-validation failed: {e}")
            return []

        warnings = []
        checks = {
            "serial_number":  fields.get("serial_number"),
            "class_indices":  fields.get("class_indices"),
            "agent_details":  fields.get("agent_details"),
            "applicant_name": fields.get("applicant_name"),
        }
        for field_name, value in checks.items():
            if value and not _field_found_in_ocr(value, ocr_blob):
                warnings.append(f"{field_name} not found in block's own OCR text - possible block-boundary mismatch")
                self.log(f"WARNING: OCR cross-validation - {field_name}='{value[:40]}' not found in block OCR text")
        return warnings

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
        """Finds the trademark image by looking for ink on the left side of the block."""
        x0, y0, x1, y1 = block_bbox
        
        # Logos in MYIPO are almost always in the top-left of the entry.
        # We look at the top 60% of the block height and left 50% of the width.
        search_height = (y1 - y0) * 0.60
        logo_zone_bbox = (x0, y0, x0 + (x1 - x0) * 0.5, y0 + search_height)

        try:
            # Render at high resolution
            header_img = page.within_bbox(logo_zone_bbox).to_image(resolution=self.LOGO_RENDER_DPI)
            img = header_img.original.convert("RGB")
            arr = np.array(img)
            
            # Find any pixel that isn't white (ink)
            # Threshold 240 is safe for scans; for clean digital PDFs, 250 is better.
            mask = np.any(arr < 242, axis=2)
            if not mask.any(): 
                return None

            # Get the bounding box of ALL ink found in the left zone
            ys, xs = np.where(mask)
            left, top, right, bottom = xs.min(), ys.min(), xs.max(), ys.max()
            
            # Add a small 5-pixel padding
            cropped_logo = img.crop((max(0, left-5), max(0, top-5), min(img.width, right+5), min(img.height, bottom+5)))
            
            buf = io.BytesIO()
            cropped_logo.save(buf, format="PNG")
            logo_bytes = buf.getvalue()

            # Final cleanup
            return self.remove_white_bg_make_transparent(logo_bytes)
        except Exception as e:
            self.log(f"Heuristic extraction failed: {e}")
            return None
        
    # Class ID matching the current logo_dataset.yaml (9-class-v2): text_logo
    # was merged into logo, so this is just the one id now, not a pair.
    LOGO_CLASS_IDS = {0}  # 0=logo

    # DPI for rendering a record block before logo detection/cropping.
    # YOLO itself resizes to its own trained input size regardless, but the
    # final logo crop used for CLIP/phash/ORB embedding is cut straight
    # from this render - so this is the resolution the actual similarity
    # comparison runs on. Raised from 300 for accuracy per explicit
    # priority (logo/similarity accuracy over extraction speed) - measured
    # cost is only ~0.2s/block extra at 600 vs 300 (0.57s vs 0.36s avg on
    # a real page), i.e. ~3 minutes added across a ~1000-record batch.
    LOGO_RENDER_DPI = 600

    @staticmethod
    def _iou(a, b):
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        ix0, iy0 = max(ax0, bx0), max(ay0, by0)
        ix1, iy1 = min(ax1, bx1), min(ay1, by1)
        inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
        area_a = max(0, ax1 - ax0) * max(0, ay1 - ay0)
        area_b = max(0, bx1 - bx0) * max(0, by1 - by0)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def extract_logos_yolo(self, page, block_bbox):
            """Returns EVERY logo box found in this block (cropped + cleaned),
            not just the largest - a composite mark can have several sub-
            elements (see trademark_logos in database.py) that each deserve
            their own crop/embedding rather than averaging them into one."""
            if not self.yolo: return []
            try:
                img_obj = page.within_bbox(block_bbox).to_image(resolution=self.LOGO_RENDER_DPI)
                img     = img_obj.original.convert("RGB")
                img_w, img_h = img.size
                results = self.yolo(img, verbose=False, conf=0.15)

                if not results or len(results[0].boxes) == 0:
                    return []

                boxes    = results[0].boxes.xyxy.cpu().numpy()
                cls_ids  = results[0].boxes.cls.cpu().numpy().astype(int)
                confs    = results[0].boxes.conf.cpu().numpy()

                # YOLO's NMS only suppresses duplicates WITHIN a class, so a
                # text field (e.g. "CLASS : 35") can score as both its real
                # class AND logo for the same region. When a DIFFERENT class
                # scores higher there, that's what actually happened - drop
                # the logo candidate rather than treat it as a second logo.
                logo_candidates = []
                for box, cls_id, conf in zip(boxes, cls_ids, confs):
                    if cls_id not in self.LOGO_CLASS_IDS:
                        continue
                    if box[2] <= box[0] or box[3] <= box[1]:
                        continue  # degenerate/zero-area box
                    spurious = any(
                        other_cls not in self.LOGO_CLASS_IDS and other_conf > conf
                        and self._iou(box, other_box) > 0.5
                        for other_box, other_cls, other_conf in zip(boxes, cls_ids, confs)
                    )
                    if not spurious:
                        logo_candidates.append((box, conf))

                if not logo_candidates:
                    return []

                # Highest confidence first, not largest area - a small genuine
                # logo can legitimately have less pixel area than a spurious
                # detection, and confidence is the more direct signal of
                # which one the model actually believes is a logo. Callers
                # that only want "the" primary logo take crops[0].
                logo_candidates.sort(key=lambda bc: bc[1], reverse=True)

                crops = []
                for box, conf in logo_candidates:
                    x0 = max(0,     int(box[0]))
                    y0 = max(0,     int(box[1]))
                    x1 = min(img_w, int(box[2]))
                    y1 = min(img_h, int(box[3]))
                    logo_crop = img.crop((x0, y0, x1, y1))
                    buf = io.BytesIO()
                    logo_crop.save(buf, format="PNG")
                    crops.append(self.remove_white_bg_make_transparent(buf.getvalue()))
                return crops
            except Exception as e:
                self.log(f"YOLO extraction error: {e}")
                return []
            
    # def extract_logo_yolo(self, page, block_bbox):
    #     """
    #     Use YOLO model to detect the logo region and crop it.
    #     """
    #     if not self.yolo:
    #         return None
    #     try:
    #         x0, y0, x1, y1 = block_bbox

    #         block_page = page.within_bbox(block_bbox)
    #         img_obj = block_page.to_image(resolution=300)

    #         img = img_obj.original.convert("RGB")
    #         img_np = np.array(img)

    #         results = self.yolo(img_np, verbose=False)

    #         if not results or len(results[0].boxes) == 0:
    #             return None

    #         boxes = results[0].boxes.xyxy.cpu().numpy()

    #         # choose largest detection
    #         best_box = None
    #         best_area = 0

    #         for box in boxes:
    #             x1b, y1b, x2b, y2b = map(int, box)
    #             area = (x2b - x1b) * (y2b - y1b)

    #             if area > best_area:
    #                 best_area = area
    #                 best_box = (x1b, y1b, x2b, y2b)

    #         if not best_box:
    #             return None

    #         x1b, y1b, x2b, y2b = best_box

    #         logo_crop = img.crop((x1b, y1b, x2b, y2b))

    #         buf = io.BytesIO()
    #         logo_crop.save(buf, format="PNG")
    #         logo_bytes = buf.getvalue()

    #         # apply your existing cleanup
    #         logo_bytes = self.tight_crop_by_nonwhite(logo_bytes)
    #         logo_bytes = self.remove_white_bg_make_transparent(logo_bytes)

    #         return logo_bytes

    #     except Exception as e:
    #         self.log(f"YOLO logo detection failed: {e}")
    #         return None

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
            "international_registration_date": None,
            "international_registration_number": None,
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

        # Madrid Protocol / international-route filings only - absent on
        # domestic filings, which correctly leaves these fields empty.
        m = self.intl_reg_number_pattern.search(text)
        if m:
            fields["international_registration_number"] = m.group(1).strip()
        m = self.intl_reg_date_pattern.search(text)
        if m:
            fields["international_registration_date"] = m.group(1).strip()

        m = self.class_header_pattern.search(text)
        if m:
            fields["class_indices"] = m.group(1).strip()

        # trademark_name is deliberately NOT populated from "Mark
        # translation:"/"Mark transliteration:" lines - these journals have
        # no genuine "official trademark name" field at all, and a
        # translation is just the mark's English MEANING, not its actual
        # name (confirmed: "Mark translation: Duru means 'pure' in
        # english." was captured as trademark_name="pure", when the real
        # word on the mark is "Duru" - misleading either way). Leaving
        # trademark_name empty lets the UI's own `trademark_name or
        # applicant_name` fallback show the applicant name instead,
        # consistent with every other record.

        agent_idx = len(lines)
        for i, line in enumerate(lines):
            # startswith, not a bare substring check — goods descriptions
            # routinely contain words like "agents" (bleaching agents,
            # chelating agents, ...) which a substring match would wrongly
            # treat as the "AGENT :" section header.
            if line.strip().upper().startswith("AGENT"):
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

        # trademark_name is NOT populated from "Mark translation:"/"Mark
        # transliteration:" here either - see the comment where this used
        # to run earlier in this function for why. Still strip the
        # boilerplate out of the description text below, just don't use
        # it as a name source.
        #
        # Bound the match by "up to the next CAPITALIZED word", not "up to
        # the next period" - these notes (and the disclaimer below)
        # routinely run straight into the goods list with no period of
        # their own (real examples: 'Mark transliteration: "ye"; "mao";
        # "lu"; "lu" Cafe and...', and separately a disclaimer ending
        # "...word 'kanopi'" with no trailing period at all). A period-
        # bounded [^\.]+\. greedily matches through to the FIRST period it
        # can find - on a goods list with no internal punctuation before
        # its own closing period, that's the description's own final
        # period, so the entire real description gets deleted along with
        # the note (confirmed: reduced real descriptions from ~470/~700
        # chars down to 0-48 chars on 3 separate real records). Goods/
        # services lists always start with a capitalized word, so this
        # bound correctly stops right where the real content begins,
        # period or not. Also matches the real "Mark transaltion:" typo
        # seen in the source (\w+ covers translation/transliteration/any
        # misspelling), which the old literal "translation:" spelling
        # missed entirely.
        desc = re.sub(r"Mark\s+\w+\s*:[^A-Z]+", "", desc)

        desc = re.sub(r"Registration of this trademark[^A-Z]+", "", desc)

        if fields["serial_number"]:
            desc = desc.replace(fields["serial_number"], "")
        if fields["registration_date"]:
            desc = desc.replace(fields["registration_date"], "")

        # Strip the main "CLASS : 29,30" header (redundant with
        # class_indices) but deliberately KEEP bare "CLASS 29"/"CLASS 30"
        # sub-headers - a multi-class record prints each class's own goods
        # list under its own sub-header (see real DURU record: "CLASS 29
        # Meat, fish... CLASS 30 Coffee, cocoa..."). Stripping these (as
        # this used to do) merges both classes' goods into one
        # indistinguishable blob, losing exactly the class-to-goods
        # mapping a multi-class record needs.
        desc = re.sub(r"CLASS\s*:\s*[\d,\s]+", "", desc, flags=re.IGNORECASE)

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
    # Width of the thin rule this journal draws directly before/after each
    # entry — distinct from the wider page header/footer border rules.
    ENTRY_SEPARATOR_WIDTH_RANGE = (340, 400)

    def _entry_separator_ys(self, page):
        """Y-positions of the thin per-entry separator lines on this page."""
        by_y = {}
        for r in page.rects:
            if r["bottom"] - r["top"] < 1.0:
                by_y.setdefault(round(r["top"], 1), []).append((r["x0"], r["x1"]))
        lo, hi = self.ENTRY_SEPARATOR_WIDTH_RANGE
        seps = []
        for y, segs in by_y.items():
            width = max(s[1] for s in segs) - min(s[0] for s in segs)
            if lo <= width <= hi:
                seps.append(y)
        return sorted(seps)

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

        # Sorted so we can fall back to a neighboring entry's own class header
        # (or this journal's drawn separator rule, see below) as a block
        # boundary when there's no "AGENT" line to anchor on — international/
        # Madrid Protocol filings have no AGENT section at all, and without
        # this a block falls back to page-bottom/page-top and can swallow the
        # next/previous entry's content, including its logo.
        class_ys = sorted(class_ys)
        separator_ys = self._entry_separator_ys(page)

        blocks = []
        for idx, cy in enumerate(class_ys):
            prev_agent = None
            for ay in agent_ys:
                if ay < cy:
                    prev_agent = ay

            curr_agent = None
            for ay in agent_ys:
                if ay > cy:
                    curr_agent = ay
                    break

            prev_class_y = class_ys[idx - 1] if idx > 0 else None
            next_class_y = class_ys[idx + 1] if idx + 1 < len(class_ys) else None

            # This journal draws its own separator rule right before/after
            # each entry — prefer it over the coarser fallbacks when present.
            sep_before = max([sy for sy in separator_ys if sy < cy - 5], default=None)
            sep_after = next((sy for sy in separator_ys if sy > cy + 5), None)

            # Separator checked FIRST, matching the comment above (and its
            # actual intent) - curr_agent/prev_agent mark where an AGENT
            # LABEL starts, not where its (often multi-line, wrapped) address
            # actually ends, so "+15" past it routinely truncated real agent
            # text to just its first line. The drawn separator marks the
            # true end of an entry regardless of how many lines it wraps to.
            if sep_before:
                y0 = sep_before + 5
            elif prev_agent:
                y0 = prev_agent + 25
            elif prev_class_y:
                y0 = max(prev_class_y + 40, cy - 120, 50)
            else:
                y0 = max(cy - 120, 50)

            if sep_after:
                y1 = sep_after - 3
            elif curr_agent:
                y1 = curr_agent + 15
            elif next_class_y:
                y1 = next_class_y - 20
            else:
                y1 = h - 60

            if y1 - y0 > 100:
                # Truncated (continues onto the next page) only when NO
                # closing boundary was found at all on this page — a drawn
                # separator or a next entry's own header both count as proof
                # this entry is actually complete here.
                truncated = curr_agent is None and sep_after is None and next_class_y is None
                blocks.append({"bbox": (0, y0, w, y1), "class_y": cy, "truncated": truncated})

        return blocks

    def _first_class_y(self, page):
        """y-position of the first 'CLASS : ...' header line on this page, or None."""
        words = page.extract_words()
        lines = {}
        for word in words:
            y = round(word["top"], 1)
            lines.setdefault(y, []).append(word)
        for y, ws in sorted(lines.items()):
            txt = " ".join(w["text"] for w in ws)
            if re.match(r"^\s*CLASS\s*:\s*[\d,\s]+\s*$", txt, re.IGNORECASE):
                return y
        return None

    def _looks_like_applicant_name(self, name):
        """This journal's applicant names are ALL-CAPS company names. A goods-
        list fragment (e.g. "milk", "Cinnamon (spice)") reads as mixed/lower
        case instead — a cheap, effective tell that extraction grabbed the
        wrong thing (usually because the real name is on the next page)."""
        if not name or len(name.strip()) < 4:
            return False
        letters = [c for c in name if c.isalpha()]
        if not letters:
            return False
        return sum(1 for c in letters if c.isupper()) / len(letters) > 0.6

    SERIES_MARKER = re.compile(r"series of\s+\w+\s+trade\s*marks", re.IGNORECASE)
    MAX_LOOKAHEAD_PAGES = 3
    MAX_LOOKBACK_PAGES = 5
    PAGE_BOILERPLATE = re.compile(
        r"INTELLECTUAL PROPERTY OFFICIAL JOURNAL\s*\n?\s*BATCH\s+\d+/\d+\s+\w+\s+\d+,\s+\d+"
        r"|TRADEMARK\s+Page\s+\d+",
        re.IGNORECASE,
    )

    def _strip_page_boilerplate(self, text):
        """Cross-page stitching pulls in whole pages/leftover chunks — strip the
        fixed header/footer boilerplate so it doesn't leak into description text."""
        return self.PAGE_BOILERPLATE.sub(" ", text or "").strip()

    def _page_last_class_y(self, page):
        """y-position of the LAST 'CLASS : ...' header line on this page, or None."""
        words = page.extract_words()
        lines = {}
        for word in words:
            y = round(word["top"], 1)
            lines.setdefault(y, []).append(word)
        last = None
        for y, ws in sorted(lines.items()):
            txt = " ".join(w["text"] for w in ws)
            if re.match(r"^\s*CLASS\s*:\s*[\d,\s]+\s*$", txt, re.IGNORECASE):
                last = y
        return last

    def _render_composite_snapshot(self, block_page, lookback_regions, lookahead_regions, resolution=150):
        """Renders the FULL visual content actually used to build `fields`,
        including any pages pulled in by cross-page stitching (see the
        lookahead/lookback logic below) - stacked vertically in reading
        order. Without this, OCR cross-validation would check fields
        against only this page's own bbox and wrongly flag a record whose
        agent/applicant genuinely live on the NEXT page (confirmed: a
        record correctly stitched across pages 9->10 still got flagged
        because the snapshot only showed page 9)."""
        images = []
        for pg, bbox in lookback_regions:
            try:
                region = pg.crop(bbox) if bbox else pg
                images.append(region.to_image(resolution=resolution).original.convert("RGB"))
            except Exception:
                pass
        try:
            images.append(block_page.to_image(resolution=resolution).original.convert("RGB"))
        except Exception:
            pass
        for pg, bbox in lookahead_regions:
            try:
                region = pg.crop(bbox) if bbox else pg
                images.append(region.to_image(resolution=resolution).original.convert("RGB"))
            except Exception:
                pass

        if not images:
            return None
        if len(images) == 1:
            return images[0]

        width = max(im.width for im in images)
        total_height = sum(im.height for im in images)
        composite = Image.new("RGB", (width, total_height), "white")
        y = 0
        for im in images:
            composite.paste(im, (0, y))
            y += im.height
        return composite

    def extract_from_block(self, page, block_info, page_num, pages_to_process=None, page_index=None):
        bbox = block_info["bbox"]

        # crop(), not within_bbox() - within_bbox requires a text line's
        # FULL bounding box (top and bottom) to fit inside bbox, so a line
        # whose top sits just before the boundary but whose bottom edge
        # (top + line height) extends past it gets silently dropped whole.
        # crop() keeps anything overlapping the box, clipped to it instead.
        block_page = page.crop(bbox)
        text = block_page.extract_text()
        if not text:
            return None

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        fields, completeness = self.parse_fields(text, lines)

        def page_at(offset):
            if pages_to_process is None or page_index is None:
                return None
            idx = page_index + offset
            return pages_to_process[idx] if 0 <= idx < len(pages_to_process) else None

        # Tracks which extra page regions (if any) got stitched into `text`
        # below, so the OCR cross-validation snapshot can be built from the
        # SAME regions the text-layer extraction actually used - not just
        # this page's own bbox.
        lookback_regions  = []
        lookahead_regions = []

        # The applicant name doesn't look like a real company name — this
        # journal draws a closing separator per PAGE, not per logical entry,
        # so an entry's own content can still spill onto later pages even
        # though this page's portion looks visually "closed." Retry with each
        # following page's leading continuation stitched in (stopping as soon
        # as one actually yields a plausible name, or a genuine next entry is
        # found — meaning the real name just isn't there to be found).
        if not self._looks_like_applicant_name(fields["applicant_name"]):
            for offset in range(1, self.MAX_LOOKAHEAD_PAGES + 1):
                nxt = page_at(offset)
                if nxt is None:
                    break
                next_cy = self._first_class_y(nxt)
                cutoff = (next_cy - 20) if next_cy else nxt.height
                if cutoff > 20:
                    try:
                        # crop(), not within_bbox() - see the comment on the
                        # same substitution in extract_from_block above. This
                        # is exactly what silently dropped the last line of a
                        # multi-page agent address (its bottom edge landed a
                        # few points past `cutoff` even though its top - and
                        # all its actual text - sat well before it).
                        continuation = self._strip_page_boilerplate(nxt.crop((0, 0, nxt.width, cutoff)).extract_text())
                    except Exception:
                        continuation = None
                    if continuation:
                        stitched_text = text + "\n" + continuation
                        stitched_lines = [l.strip() for l in stitched_text.split("\n") if l.strip()]
                        stitched_fields, stitched_completeness = self.parse_fields(stitched_text, stitched_lines)
                        if self._looks_like_applicant_name(stitched_fields["applicant_name"]):
                            text, lines, fields, completeness = stitched_text, stitched_lines, stitched_fields, stitched_completeness
                            lookahead_regions = [(nxt, (0, 0, nxt.width, cutoff))]
                            break
                if next_cy is not None:
                    break  # a genuine next entry starts here — nothing more of ours to find

        # "Series of N trademarks" filings print their combined class summary
        # and applicant/agent block in the MIDDLE of their own content, with a
        # large — sometimes multi-page — run of goods-list text before it that
        # find_blocks() has no way to know belongs to this entry. Detect the
        # marker and walk backward, reusing find_blocks() on each earlier page
        # to find that page's own last (genuinely different) entry, so we only
        # absorb text that comes AFTER it — never another entry's own content.
        if self.SERIES_MARKER.search(text):
            prefix = ""
            new_lookback_regions = []
            for offset in range(1, self.MAX_LOOKBACK_PAGES + 1):
                prev = page_at(-offset)
                if prev is None:
                    break
                prev_blocks = self.find_blocks(prev)
                if prev_blocks:
                    prev_last_y1 = prev_blocks[-1]["bbox"][3]
                    prev_bbox = (0, prev_last_y1, prev.width, prev.height)
                    try:
                        # crop(), not within_bbox() - same reasoning as above.
                        chunk = prev.crop(prev_bbox).extract_text()
                    except Exception:
                        chunk = None
                    prefix = self._strip_page_boilerplate(chunk) + "\n" + prefix
                    new_lookback_regions.insert(0, (prev, prev_bbox))
                    break  # found the true previous entry's own end — stop here
                else:
                    try:
                        chunk = prev.extract_text()
                    except Exception:
                        chunk = None
                    prefix = self._strip_page_boilerplate(chunk) + "\n" + prefix
                    new_lookback_regions.insert(0, (prev, None))
            if prefix.strip():
                lookback_regions = new_lookback_regions
                stitched_text = prefix + "\n" + text
                stitched_lines = [l.strip() for l in stitched_text.split("\n") if l.strip()]
                stitched_fields, stitched_completeness = self.parse_fields(stitched_text, stitched_lines)
                # Keep this pass's own serial/applicant (already correct — they
                # sit after the goods lists we're prefixing in), just recover
                # the now-complete description.
                if stitched_fields["description"]:
                    fields["description"] = stitched_fields["description"]
                completeness = max(completeness, stitched_completeness)

        if not fields["serial_number"]:
            self.log("❌ No serial number - skipping")
            return None
#
        # Try YOLO first - may find zero, one, or several logo sub-elements.
        logo_crops = self.extract_logos_yolo(page, bbox) if self.yolo else []

        # fallback to heuristic method only if YOLO found nothing at all
        if not logo_crops:
            self.log(f"YOLO found no logo on page {page_num}, falling back to heuristic")
            heuristic_logo = self.extract_logo_only(page, bbox)
            if heuristic_logo:
                logo_crops = [heuristic_logo]

        logos = []
        for crop_bytes in logo_crops:
            emb = None
            if self.ml:
                try:
                    emb = self.ml.generate_image_embedding(io.BytesIO(crop_bytes))
                except Exception as e:
                    self.log(f"Logo embedding failed: {e}")
            logos.append({"logo_data": crop_bytes, "logo_embedding": emb})

        # Primary logo (largest) kept in the old single-value fields too, for
        # any code still reading logo_data/logo_embedding directly.
        logo_data = logos[0]["logo_data"] if logos else None
        logo_emb = logos[0]["logo_embedding"] if logos else None

        try:
            composite_img = self._render_composite_snapshot(block_page, lookback_regions, lookahead_regions, resolution=150)
            buf = io.BytesIO()
            composite_img.save(buf, format="PNG")
            snapshot = buf.getvalue()
        except Exception:
            snapshot = None

        validation_warnings = self.validate_fields_with_ocr(snapshot, fields)

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
            "international_registration_date": fields["international_registration_date"],
            "international_registration_number": fields["international_registration_number"],
            "trademark_name": fields["trademark_name"],
            "class_indices": fields["class_indices"],
            "applicant_name": fields["applicant_name"],
            "applicant_address": fields["applicant_address"],
            "agent_details": fields["agent_details"],
            "description": fields["description"],
            "logo_data": logo_data,
            "logo_embedding": logo_emb,
            "logos": logos,
            "text_embedding": text_emb,
            "block_snapshot": snapshot,
            "completeness": completeness,
            "validation_warnings": validation_warnings
        }

        return result

    # def extract_all(self, pdf_stream, start_page=4):
    #     results = []
    #     with pdfplumber.open(pdf_stream) as pdf:
    #         total_pdf_pages = len(pdf.pages)
    #         pages_to_process = pdf.pages[start_page - 1:]
            
    #         print(f"--- Starting Extraction ---")
    #         print(f"Total Pages in PDF: {total_pdf_pages}")
    #         print(f"Processing from page {start_page} to {total_pdf_pages}...")

    #         # Wrap the loop with tqdm for a visual progress bar
    #         # If tqdm isn't installed, it falls back to a basic range
    #         iterator = enumerate(pages_to_process, start=start_page)
    #         if _HAS_TQDM:
    #             iterator = tqdm(iterator, total=len(pages_to_process), desc="Extracting", unit="pg")

    #         for pnum, page in iterator:
    #             try:
    #                 blocks = self.find_blocks(page)
    #                 for block in blocks:
    #                     data = self.extract_from_block(page, block, pnum)
    #                     if data:
    #                         results.append(data)
                    
    #                 # If not using tqdm, print a simple status line
    #                 if not _HAS_TQDM and pnum % 5 == 0:
    #                     print(f"Currently on page {pnum}...")

    #             except Exception as e:
    #                 self.log(f"❌ Page {pnum} failed: {e}")
            
    #         print(f"\n--- Extraction Complete ---")
    #         print(f"Total Records Found: {len(results)}")
    #     return results
    
    def extract_all(self, pdf_stream, start_page=4):
        results = []
        with pdfplumber.open(pdf_stream) as pdf:
            total_pdf_pages = len(pdf.pages)
            pages_to_process = pdf.pages[start_page - 1:]
            total_to_process = len(pages_to_process)

            print(f"--- Starting Extraction ---")
            print(f"Total Pages in PDF: {total_pdf_pages}")
            print(f"Processing from page {start_page} to {total_pdf_pages}...")

            # We use a standard 0-based enumerate to get the index 'i'
            iterator = enumerate(pages_to_process)
            
            if _HAS_TQDM:
                iterator = tqdm(iterator, total=total_to_process, desc="Extracting", unit="pg")

            # i = 0-based index for progress, page = the PDF page object
            for i, page in iterator:
                # Calculate the actual page number for display
                pnum = i + start_page 
                
                try:
                    # Calculate progress percentage (i+1 because i starts at 0)
                    progress = int(((i + 1) / total_to_process) * 100)
                    
                    # YIELD progress update to the caller (Flask/JS)
                    yield {"status": "extracting", "percentage": progress, "current_page": pnum}

                    # NOTE: batching a page's blocks into one YOLO call, and
                    # reusing that render for the evidence snapshot, were both
                    # tried as speed optimizations and reverted - batching
                    # measurably LOST real detections on CPU (blocks of
                    # different sizes get resized differently once batched,
                    # confirmed: 2 of 9 test records lost a logo) while also
                    # being slower, and the render-reuse alone turned out to
                    # be a wash once actually measured. Neither survived
                    # profiling, so this stays as originally written: each
                    # block renders and infers independently.
                    blocks = self.find_blocks(page)
                    for block in blocks:
                        data = self.extract_from_block(page, block, pnum, pages_to_process=pages_to_process, page_index=i)
                        if data:
                            results.append(data)
                    
                    if not _HAS_TQDM and pnum % 5 == 0:
                        print(f"Currently on page {pnum}...")

                except Exception as e:
                    self.log(f"❌ Page {pnum} failed: {e}")
                    
        # Final yield with total results
        yield {"status": "extraction_complete", "results": results}

# -------------------------
# Convenience function for Flask
# -------------------------
def extract_all(pdf_stream, debug=False):
    extractor = UltraRobustExtractor(debug=debug)
    # Ensure it starts from page 1 or the standard MYIPO journal start page
    return extractor.extract_all(pdf_stream, start_page=4)