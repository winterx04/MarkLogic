# test_model.py
# ─────────────────────────────────────────────────────────────
# Interactive tester for your trained YOLO trademark model, with an
# OCR-based post-detection correction layer: after YOLO proposes a class
# for a box, this reads the box's actual text and corrects the label when
# the text clearly disagrees:
#   1. 2+ semicolons -> description (the NICE goods/services list
#      convention; agent/applicant blocks use exactly ONE semicolon to
#      separate "NAME ; ADDRESS", then commas from there - only 2+ safely
#      means a real list, not a name;address block)
#   2. Starts with "AGENT" / "CLASS" -> that class, regardless of YOLO's guess
#   3. Classified "agent" but text does NOT start with "AGENT" -> applicant
#      (every real agent block reads "AGENT..." - if it doesn't, YOLO
#      likely mislabeled the applicant's name+address as agent instead)
#   4. Contains "International priority date claimed" -> that class,
#      regardless of YOLO's guess; classified as that but the phrase is
#      NOT present -> rejected (YOLO picked up some unrelated word instead)
#   5. Classified "international_registration_number" but the text isn't
#      pure digits in the expected length (e.g. "1809879") -> rejected
# This never touches "logo" boxes: a logo can legitimately contain bold/
# stylized text of its own, and that must not get relabeled as
# applicant/agent just because it reads as text or looks bold.
#
# Usage:
#   python test_model.py                          <- prompts you for input
#   python test_model.py --input page.png         <- single image
#   python test_model.py --input journal.pdf      <- PDF
#   python test_model.py --input page.png --conf 0.3 --model models/best_t10.pt
#   python test_model.py --input journal.pdf --no-ocr-correct   <- disable the correction layer, YOLO-only
# ─────────────────────────────────────────────────────────────

import os
import argparse
import hashlib
import re
import cv2
import numpy as np
import pdfplumber
from ultralytics import YOLO

import similarity

# Class names for the model trained on the CURRENT final_dataset/logo_dataset.yaml
# scheme (text_logo merged into logo, international_registration_number added).
CLASS_NAMES = [
    "logo",
    "serial_number",
    "description",
    "agent",
    "applicant",
    "class",
    "date",
    "international_registration_date",
    "international_registration_number",
]

# Color per class (BGR) — shown on the output image
CLASS_COLORS = {
    "logo":                             (0,   0,   255),  # Red
    "serial_number":                    (255, 0,   0  ),  # Blue
    "description":                      (0,   170, 0  ),  # Green
    "agent":                            (0,   136, 255),  # Orange
    "applicant":                        (255, 0,   170),  # Purple
    "class":                            (255, 170, 0  ),  # Cyan
    "date":                             (47,  52,  74 ),  # Dark brown
    "international_registration_date":  (19,  69,  139),  # Brown
    "international_registration_number":(139, 125, 96 ),  # Slate blue-grey
}

# ── OCR post-detection correction ──────────────────────────────────────
# Boxes this correction is allowed to touch at all. "logo" is deliberately
# excluded - a logo can contain its own bold/stylized text, and reading
# text (or measuring boldness) inside a logo box must never turn it into
# "applicant"/"agent". serial_number is excluded: it has its own tight
# regex-checked format elsewhere in the real pipeline (pdf_extractor.py).
# "date" IS included despite also being regex-checked elsewhere - it's the
# most likely thing to get confused with "international_registration_date"
# (both are date-shaped content), so it needs to be reachable by Rule 4.
CORRECTABLE_CLASSES = {
    "agent", "applicant", "description", "class", "date",
    "international_registration_number", "international_registration_date",
}

# Literal label words/phrases that, if OCR finds them in a box's text,
# override YOLO's own class guess. Confirmed against real pages: AGENT and
# CLASS boxes reliably start with these bold labels; APPLICANT does NOT
# start with a fixed label word (it's just the applicant's name, bolded) -
# so there is deliberately no "APPLICANT" entry here.
#   value True  -> match must be at the START of the text (a leading bold label)
#   value False -> match anywhere in the text (a phrase, not necessarily first)
OCR_LABEL_OVERRIDES = {
    "AGENT":                             ("agent",                              True),
    #"CLASS":                             ("class",                              True),
    "PRIORITYDATECLAIM":                 ("international_registration_date",    False),
    "INTERNATIONALREGISTRATIONNUMBER":   ("international_registration_number",  False),
    # Disclaimer/notice text that precedes the real goods list - the same
    # recurring pattern chased throughout this whole investigation (double
    # description boxes, missing boxes, and now confirmed: raw YOLO
    # sometimes calls it "applicant" outright, e.g. GTH's "The trade mark
    # is limited to the colours..." at conf 0.50). Rule 3 only catches
    # agent-shaped mislabels; nothing previously caught applicant-shaped
    # ones. These always lead their own box's text, so at_start=True.
    "REGISTRATIONOFTHISTRADEMARK":       ("description",                        True),
    "THETRADEMARKIS":                    ("description",                        True),  # short prefix - OCR read "LIMITED" as "IMITED" once, don't depend on that word
    "ADVERTISEMENTOFASERIES":            ("description",                        True),
    "PROCEEDINGUNDERSECTION":            ("description",                        True),
    "MARKTRANS":                         ("description",                        True),  # translation/transliteration/the real "transaltion" typo
}

# Only present on Madrid Protocol / international-route filings. Format
# confirmed by the user: plain digits, e.g. "1809879" - no letters, no
# separators, 5-10 digits. NOT anchored to the whole string (^...$) - the
# box's text is "International Registration Number : 1809879" (same
# LABEL:VALUE structure as AGENT/CLASS), not just the bare digits, so this
# only needs to find the digit run somewhere in the text, not match it
# entirely (verified against a real page: a genuinely correct box was
# wrongly rejected by a full-string version of this check).
INTL_REG_NUMBER_RE = re.compile(r'\d{5,10}')

_raw_ocr_cache = {}
_field_ocr_engine = None


def _get_field_ocr_engine():
    """Separate PaddleOCR engine from similarity.py's shared singleton -
    similarity.py's engine (PP-OCRv6 medium) is already eval-validated for
    the Compare feature's font-mismatch guard, so it's left untouched. 
    This one uses PP-OCRv6 TINY instead: measured on a real page, tiny was
    32.5x faster (0.16s/box vs 5.05s/box) with byte-identical text output
    on every one of 16 real boxes (descriptions, AGENT/CLASS labels,
    applicant names+addresses, dates) - no accuracy tradeoff observed for
    this field-classification use case, which only needs short label/
    first-line reads, not dense-document OCR."""
    global _field_ocr_engine
    if _field_ocr_engine is None:
        try:
            from paddleocr import PaddleOCR
            _field_ocr_engine = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False,
                text_detection_model_name="PP-OCRv6_tiny_det",
                text_recognition_model_name="PP-OCRv6_tiny_rec",
            )
        except Exception:
            _field_ocr_engine = False
    return _field_ocr_engine


def read_box_text(crop_bgr):
    """One OCR pass on a crop, returning (normalized_text, raw_text).
    similarity.ocr_text_bytes() strips everything but A-Z0-9 for its own
    wordmark-comparison use case, which also destroys the punctuation/
    spacing this needs (semicolon counts, "SDN BHD"-style suffixes) - so
    this keeps its own cache and reads the engine directly instead of
    calling it twice (which would double the OCR latency per box)."""
    ok, buf = cv2.imencode(".png", crop_bgr)
    if not ok:
        return "", ""
    key = hashlib.md5(buf.tobytes()).hexdigest()
    if key in _raw_ocr_cache:
        return _raw_ocr_cache[key]

    normalized, raw = "", ""
    engine = _get_field_ocr_engine()
    if engine:
        try:
            # Same fix as similarity.ocr_text_bytes(): large/wide crops
            # measured 3.5-9.7s per OCR call vs ~0.6-1s on small ones - a
            # short label/first-line read needs no more than ~320px on the
            # long side, and downscaling first cuts that dramatically with
            # no accuracy loss (verified).
            hh, ww = crop_bgr.shape[:2]
            longest = max(hh, ww)
            if longest > similarity.OCR_MAX_DIM:
                scale = similarity.OCR_MAX_DIM / longest
                crop_bgr = cv2.resize(crop_bgr, (max(1, int(ww * scale)), max(1, int(hh * scale))),
                                       interpolation=cv2.INTER_AREA)
            for res in engine.predict(crop_bgr):
                texts  = res.get('rec_texts')  or []
                scores = res.get('rec_scores') or []
                kept   = [t for t, s in zip(texts, scores) if s >= similarity.OCR_MIN_CONFIDENCE]
                raw        = " ".join(kept)
                normalized = similarity.normalize(raw)
        except Exception:
            pass

    _raw_ocr_cache[key] = (normalized, raw)
    return normalized, raw


def ink_density(crop_bgr):
    """Fraction of dark ('ink') pixels in a text-field crop. Kept for
    inspection/printing only - validated against real crops and found
    UNRELIABLE for bold-vs-regular (a genuine bold applicant read 0.168-0.183,
    but italic disclaimer text read 0.140-0.204 - directly overlapping,
    since italic slant plus serif strokes covers comparable area to bold
    weight). Use stroke_width() instead for anything that actually gates a
    correction."""
    if crop_bgr.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return float(np.count_nonzero(binary)) / binary.size


def stroke_width(crop_bgr):
    """Median stroke width via connected-component geometry: for an
    elongated ink blob, 2*Area/Perimeter ~= width (exact for a long thin
    rectangle: Area=w*L, Perimeter~=2L when L>>w). Measures PERPENDICULAR
    stroke thickness rather than total dark-pixel coverage, so - unlike
    ink_density() - it isn't confused by italic slant.
    Validated against real page-7 boxes (index4.pdf): genuine bold
    applicant text measured 1.69-1.72; italic disclaimer text and regular
    (non-bold) goods-list text wrongly classified "applicant" all measured
    <=0.86 - a clean gap, no overlap. Threshold below is set well below the
    observed genuine-applicant floor for margin, but is only calibrated on
    this one page so far - watch for false corrections as more pages are
    checked and adjust if a genuine bold applicant ever reads below it."""
    if crop_bgr.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    widths = []
    for c in contours:
        area = cv2.contourArea(c)
        perimeter = cv2.arcLength(c, True)
        if perimeter > 0 and area > 2:
            widths.append(2 * area / perimeter)
    if not widths:
        return 0.0
    return float(np.median(widths))


# Genuine bold applicant text measured 1.69-1.72 on real crops; every false
# "applicant" (italic disclaimer, regular goods-list text) measured <=0.86.
# Set with margin below the observed genuine floor, not right at the gap.
APPLICANT_MIN_STROKE_WIDTH = 1.2


def ocr_correct(img, cls_name, box):
    """Returns (final_cls_name, info) where info carries the OCR text,
    ink density, and correction reason (if any) for printing/inspection.
    Only ever reassigns within CORRECTABLE_CLASSES - never touches "logo"
    or the regex-driven classes (serial_number/date/international_*)."""
    info = {"ocr_text": "", "ink_ratio": None, "reason": None}
    if cls_name not in CORRECTABLE_CLASSES:
        return cls_name, info

    x1, y1, x2, y2 = box
    h, w = img.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    full_crop = img[y1:y2, x1:x2]
    if full_crop.size == 0:
        return cls_name, info

    # Only the first line/two matters for these checks (label words lead
    # the block; a goods list already shows 2+ ";" within its first line
    # too) - description/agent/applicant boxes can be tall AND full-page-
    # width paragraphs. Measured on a real page: capping height only left
    # width untouched, and a wide-but-short crop still took 3.5-10.5s per
    # OCR call (vs ~1s for naturally-narrow class/date boxes) - width, not
    # just area, drives PaddleOCR's cost here. Cap both; 500px is enough
    # room to catch 2+ semicolons or a multi-word label/phrase.
    strip_h    = max(1, min(full_crop.shape[0], int(full_crop.shape[0] * 0.3) + 20))
    strip_w    = min(full_crop.shape[1], 500)
    label_crop = full_crop[:strip_h, :strip_w]

    norm_text, raw_text = read_box_text(label_crop)

    # Rule 1 needs to see further down the box than the phrase/stroke-width
    # checks do - a multi-line goods list's 2+ semicolons can start past
    # this short strip (confirmed: "Entertainment services providing
    # facilities for singing with (Karaoke); party planning...; all
    # included..." has both ";" on lines 2-3). Widening label_crop itself
    # to fix this broke stroke_width() instead - a taller crop pulls in
    # extra lines' connected components and shifts the per-character
    # area/perimeter ratio, flipping two previously-correct corrections
    # back to wrong (measured 1.11->1.49 and 0.68->1.44, both crossing back
    # above the bold floor). Keep label_crop short for those; use a second,
    # taller crop just for the semicolon count.
    tall_h = max(1, min(full_crop.shape[0], int(full_crop.shape[0] * 0.6) + 20))
    if raw_text.count(";") < 2 and tall_h > strip_h:
        tall_crop = full_crop[:tall_h, :strip_w]
        _, tall_raw_text = read_box_text(tall_crop)
        if len(tall_raw_text) > len(raw_text):
            raw_text = tall_raw_text
    info["ocr_text"]  = norm_text
    info["ink_ratio"] = round(ink_density(full_crop), 3)

    final_cls = cls_name

    # Rule 1 (checked first - strongest signal): 2+ semicolons is the NICE
    # classification goods/services-list convention (a real example had 3+
    # in just the first line). WRONG originally: checking for ANY ";" also
    # fires on "COMPANY SDN BHD ; No. 18, Jalan ..." - agent/applicant
    # blocks use exactly ONE semicolon to separate the name from its
    # address, then commas from there. Only 2+ safely distinguishes an
    # actual list from a name;address block.
    matched_override = False
    if raw_text.count(";") >= 2 and cls_name != "description":
        # Rule 1 (strongest signal): 2+ semicolons is the NICE
        # classification goods/services-list convention (a real example had
        # 3+ in just the first line). WRONG originally: checking for ANY
        # ";" also fires on "COMPANY SDN BHD ; No. 18, Jalan ..." -
        # agent/applicant blocks use exactly ONE semicolon to separate the
        # name from its address, then commas from there. Only 2+ safely
        # distinguishes an actual list from a name;address block.
        final_cls = "description"
        info["reason"] = f"raw text has {raw_text.count(';')} ';' (goods-list convention): '{raw_text[:40]}'"
        matched_override = True
    else:
        # Rule 2/4: literal label words/phrases override YOLO's guess
        # whenever they're found, regardless of what class it currently is.
        for phrase, (mapped_cls, at_start) in OCR_LABEL_OVERRIDES.items():
            found = norm_text.startswith(phrase) if at_start else (phrase in norm_text)
            if found and cls_name != mapped_cls:
                final_cls = mapped_cls
                info["reason"] = f"OCR text {'starts with' if at_start else 'contains'} '{phrase}' (read: '{norm_text[:30]}')"
                matched_override = True
                break

    if not matched_override:
        # Rule 5: a box classified "international_registration_number"
        # should either contain the field's own label or a 5-10 digit run
        # (the box holds "International Registration Number : 1809879" -
        # same LABEL:VALUE shape as AGENT/CLASS - so the label alone is
        # already real evidence even if the crop cut off before the
        # digits). Reject only when NEITHER is found at all - that's the
        # "YOLO picked up some unrelated word" case this targets.
        if (cls_name == "international_registration_number" and norm_text
                and "INTERNATIONALREGISTRATIONNUMBER" not in norm_text
                and not INTL_REG_NUMBER_RE.search(norm_text)):
            final_cls = "rejected"
            info["reason"] = (f"'international_registration_number' should contain the label or "
                               f"a 5-10 digit number (e.g. '1809879') - read '{norm_text[:30]}' instead")
        # Same idea for the priority-date phrase, checked the other
        # direction: classified as this but the phrase isn't there.
        elif (cls_name == "international_registration_date" and norm_text
                and "PRIORITYDATECLAIM" not in norm_text):
            final_cls = "rejected"
            info["reason"] = ("'international_registration_date' should read "
                               f"'International priority date claimed : ...' - read '{norm_text[:30]}' instead")
        # Rule 3 (negative evidence, weakest): every real "agent" box seen
        # so far starts with the literal word AGENT. If YOLO called
        # something "agent" and it clearly, readably does NOT, it's almost
        # always actually the applicant (caught: a company name+address
        # labeled "agent" at 0.32 with no AGENT prefix at all). Caveat:
        # this trusts OCR's negative result, so a genuine agent box OCR
        # garbles beyond recognition could get flipped too - watch for
        # that in results before trusting this rule.
        elif cls_name == "agent" and norm_text and not norm_text.startswith("AGENT"):
            final_cls = "applicant"
            info["reason"] = f"classified 'agent' but text doesn't start with AGENT (read: '{norm_text[:24]}')"

    # Rule 6: whatever landed on "applicant" (raw YOLO guess, or Rule 3's
    # own agent->applicant reassignment above) needs to actually be BOLD -
    # every real applicant name in this journal format is bold, unlike the
    # italic disclaimer text or regular-weight goods-list text that keeps
    # getting mistaken for it (see stroke_width() docstring for the
    # validated real numbers). Checked last and only for "applicant" so it
    # can't interfere with the text-pattern rules above, which are stronger
    # signals when they fire.
    if final_cls == "applicant":
        sw = stroke_width(label_crop)
        info["stroke_width"] = round(sw, 3)
        if sw < APPLICANT_MIN_STROKE_WIDTH:
            info["reason"] = (f"classified 'applicant' but stroke_width={sw:.2f} is below the bold "
                               f"floor of {APPLICANT_MIN_STROKE_WIDTH} (read: '{norm_text[:24]}')")
            final_cls = "description"

    return final_cls, info


def load_model(model_path):
    if not os.path.exists(model_path):
        print(f"[X] Model not found: {model_path}")
        print("    Pass --model with the correct path.")
        exit(1)
    print(f"[OK] Loading model: {model_path}")
    return YOLO(model_path)


def draw_results(img, results, conf_threshold, ocr_correct_enabled=True):
    """Draw bounding boxes + labels on image. Returns annotated image and
    the detection list, each carrying both the original YOLO class and the
    (possibly corrected) final class."""
    annotated = img.copy()
    boxes     = results[0].boxes

    if boxes is None or len(boxes) == 0:
        return annotated, []

    detections = []
    for box in boxes:
        conf  = float(box.conf[0])
        if conf < conf_threshold:
            continue

        cls_id     = int(box.cls[0])
        yolo_cls   = CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else f"class_{cls_id}"
        x1, y1, x2, y2 = map(int, box.xyxy[0])

        final_cls, ocr_info = (
            ocr_correct(img, yolo_cls, (x1, y1, x2, y2))
            if ocr_correct_enabled else (yolo_cls, {"ocr_text": "", "ink_ratio": None, "reason": None})
        )
        corrected = final_cls != yolo_cls
        color     = CLASS_COLORS.get(final_cls, (200, 200, 200))

        # Draw box - yellow dashed-look double box when corrected, so a
        # correction is visible at a glance without reading the label text.
        if corrected:
            cv2.rectangle(annotated, (x1 - 3, y1 - 3), (x2 + 3, y2 + 3), (0, 255, 255), 2)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        label = f"{final_cls} {conf:.2f}" + (f"  (was: {yolo_cls})" if corrected else "")
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(annotated, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        detections.append({
            "class":       final_cls,
            "yolo_class":  yolo_cls,
            "corrected":   corrected,
            "conf":        round(conf, 3),
            "box":         (x1, y1, x2, y2),
            "ocr_text":    ocr_info.get("ocr_text", ""),
            "ink_ratio":   ocr_info.get("ink_ratio"),
            "reason":      ocr_info.get("reason"),
        })

    return annotated, detections


def print_detections(detections):
    print(f"\n{'-'*70}")
    print(f"  Found {len(detections)} detection(s):")
    for d in detections:
        # Show the YOLO->final transition explicitly on a corrected box -
        # printing only the final class made it look like YOLO already had
        # it right, when the whole point is that it didn't.
        cls_display = f"{d['yolo_class']} -> {d['class']}" if d["corrected"] else d['class']
        flag = f"  <== CORRECTED: {d['reason']}" if d["corrected"] else ""
        print(f"  - {cls_display:<24} conf={d['conf']:<5}"
              f"  ocr='{d['ocr_text'][:30]}'"
              f"  ink={d['ink_ratio']}{flag}")
    print(f"{'-'*70}")


def test_image(model, img_path, conf, out_dir, ocr_correct_enabled):
    """Run detection on a single image file."""
    img = cv2.imread(img_path)
    if img is None:
        print(f"[X] Could not read image: {img_path}")
        return

    print(f"\nRunning detection on: {img_path}")
    results                = model(img, conf=conf, verbose=False)
    annotated, detections  = draw_results(img, results, conf, ocr_correct_enabled)

    if detections:
        print_detections(detections)
    else:
        print("  (no detections above confidence threshold)")

    os.makedirs(out_dir, exist_ok=True)
    stem     = os.path.splitext(os.path.basename(img_path))[0]
    out_path = os.path.join(out_dir, f"{stem}_result.jpg")
    cv2.imwrite(out_path, annotated)
    print(f"\nSaved result -> {out_path}")


def test_pdf(model, pdf_path, conf, out_dir, ocr_correct_enabled, start_page=4, max_pages=10, dpi=150):
    """Run detection on each page of a PDF, rendered via pdfplumber (no
    Poppler/pdf2image dependency - matches how the real pipeline in
    pdf_extractor.py / extract_trademarks.py renders pages)."""
    if not os.path.exists(pdf_path):
        print(f"[X] PDF not found: {pdf_path}")
        return

    os.makedirs(out_dir, exist_ok=True)
    total_detections = 0
    total_corrections = 0

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        end_page    = min(start_page + max_pages - 1, total_pages)

        print(f"\nPDF: {pdf_path}")
        print(f"   Pages {start_page}-{end_page} of {total_pages} (DPI={dpi})")

        for page_num in range(start_page, end_page + 1):
            page     = pdf.pages[page_num - 1]
            pil_img  = page.to_image(resolution=dpi).original.convert("RGB")
            img      = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

            results               = model(img, conf=conf, verbose=False)
            annotated, detections = draw_results(img, results, conf, ocr_correct_enabled)
            total_detections      += len(detections)
            total_corrections     += sum(1 for d in detections if d["corrected"])

            out_path = os.path.join(out_dir, f"page_{page_num:04d}_result.jpg")
            cv2.imwrite(out_path, annotated)

            print(f"\n  Page {page_num:>4}: {len(detections)} detection(s) -> {out_path}")
            print_detections(detections)

    print(f"\nDone - {total_detections} total detections across "
          f"{end_page - start_page + 1} pages, {total_corrections} corrected by OCR")
    print(f"Results saved to: {out_dir}")


def prompt_input():
    print("=" * 55)
    print("  YOLO Trademark Model Tester")
    print("=" * 55)
    path = input("\nEnter path to image or PDF: ").strip().strip('"')
    return path


def main():
    parser = argparse.ArgumentParser(description="Test your trained YOLO trademark model.")
    parser.add_argument("--input",      default=None,                     help="Path to image (.png/.jpg) or PDF")
    parser.add_argument("--model",      default="models/best_colab5.pt",  help="Path to trained model .pt file")
    parser.add_argument("--conf",       type=float, default=0.45,         help="Confidence threshold (default: 0.25)")
    parser.add_argument("--out",        default="test_results",           help="Output folder for annotated images")
    parser.add_argument("--start_page", type=int,   default=4,            help="PDF: first page to process")
    parser.add_argument("--max_pages",  type=int,   default=10,           help="PDF: max pages to process")
    parser.add_argument("--dpi",        type=int,   default=150,          help="PDF: render DPI (150=fast, 300=sharp)")
    parser.add_argument("--no-ocr-correct", action="store_true",          help="Disable the OCR correction layer (YOLO output only)")
    args = parser.parse_args()

    input_path = args.input or prompt_input()
    if not input_path:
        print("[X] No input provided.")
        return

    input_path = os.path.abspath(input_path)
    if not os.path.exists(input_path):
        print(f"[X] File not found: {input_path}")
        return

    model = load_model(args.model)
    ext   = os.path.splitext(input_path)[1].lower()
    ocr_correct_enabled = not args.no_ocr_correct

    if ext == ".pdf":
        test_pdf(model, input_path, args.conf, args.out, ocr_correct_enabled,
                 start_page=args.start_page,
                 max_pages=args.max_pages,
                 dpi=args.dpi)
    elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
        test_image(model, input_path, args.conf, args.out, ocr_correct_enabled)
    else:
        print(f"[X] Unsupported file type: {ext}")
        print("    Supported: .png .jpg .jpeg .pdf")


if __name__ == "__main__":
    main()
