# similarity.py
# Pure trademark-matching scoring logic — no Flask, no DB, no network I/O.
# Extracted from app.py so it can be reused by both the /compare route and
# an offline evaluation harness (eval_similarity.py) without the two drifting apart.

import io
import hashlib
import re
from difflib import SequenceMatcher

import cv2
import jellyfish
import numpy as np
import imagehash
from PIL import Image as PILImage

# ── Embedding dimensions (single source of truth) ──────────────────────────
IMAGE_EMBEDDING_DIM = 512   # clip-ViT-B-32
TEXT_EMBEDDING_DIM  = 384   # all-MiniLM-L6-v2

# ── Candidate pre-filter (before the full blend is even computed) ─────────
CANDIDATE_FLOOR = 0.3

# ── Blending weights ────────────────────────────────────────────────────
TEXT_LITERAL_SUBSTRING_SCORE   = 0.85
CLIP_TEXT_WEIGHT               = 0.9
FUZZY_TEXT_WEIGHT              = 0.95
PHONETIC_TEXT_WEIGHT           = 0.8
PHASH_DISAGREEMENT_CEILING     = 0.25
# Stricter than PHASH_DISAGREEMENT_CEILING: used when ORB has no reliable
# second opinion (see ORB_MIN_KEYPOINTS) and phash alone must carry the gate.
PHASH_ONLY_FALLBACK_FLOOR      = 0.45
PHASH_DAMPENING_FACTOR         = 0.4
IMG_SIM_SATURATION             = 0.92

# ── Same-font-different-word guard ──────────────────────────────────────
# CLIP/phash/ORB all react to visual STYLE (font, stroke weight, spacing),
# not literal letter identity - two different words set in the same font
# can score near-1.0 on every one of them (confirmed: an "AIRO" query
# scored img_sim=1.0 against an unrelated same-font wordmark). Below the
# fuzzy/phonetic ceiling, two name strings are treated as "clearly
# different" and img_sim gets dampened - registered names first (cheap,
# but only available when both sides were parsed with a name), falling
# back to OCR read directly off the pixels (works even on a bare
# image-upload query with no name field at all, e.g. /api/perform_comparison's
# single-image path).
TEXT_MISMATCH_FUZZY_CEIL = 0.35
NAME_MISMATCH_DAMPENING  = 0.6   # softer: registered-name evidence is indirect
OCR_MISMATCH_DAMPENING   = 0.35  # stronger: OCR reads the image directly
OCR_TRIGGER_FLOOR        = 0.65  # only worth the ~0.5-0.7s OCR call once img_sim already looks like a hit
OCR_MIN_CONFIDENCE       = 0.5   # PaddleOCR rec_score below this = "couldn't read it", not evidence
OCR_MAX_DIM              = 320   # downscale before OCR - see ocr_text_bytes()

# ── Match-inclusion thresholds ──────────────────────────────────────────
# Calibrated via eval/eval_similarity.py against bootstrapped ground truth
# (see eval/bootstrap_pairs.csv). Both known true matches scored img_sim of
# 0.776 and 1.000 — these thresholds sit with a safety margin below that,
# favoring recall on unseen cases over squeezing precision further on this
# still-thin sample. Re-run the eval harness before changing these again.
MATCH_THRESHOLD_WITH_IMAGE_AND_NAME = 0.50
MATCH_THRESHOLD_IMAGE_ONLY          = 0.55
MATCH_THRESHOLD_NAME_ONLY           = 0.40


def normalize(text):
    return re.sub(r'[^A-Z0-9]', '', (text or "").upper())


def seq_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def jaccard_tokens(a: str, b: str) -> float:
    sa = set((a or "").lower().split())
    sb = set((b or "").lower().split())
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def phonetic_ratio(a: str, b: str) -> float:
    """Metaphone-code similarity - catches same-SOUND-different-spelling
    conflicts (e.g. "AIRO" vs "EYRO"). Trademark confusion tests weigh
    visual, phonetic, AND conceptual similarity, not just spelling, so this
    is a real signal on its own merit, not just a font-bug workaround."""
    if not a or not b:
        return 0.0
    try:
        return seq_ratio(jellyfish.metaphone(a), jellyfish.metaphone(b))
    except Exception:
        return 0.0


def _clearly_different(a: str, b: str) -> bool:
    """True when two normalized strings are provably unrelated: no
    substring relation, low edit-distance similarity, AND low phonetic
    similarity - so a genuine sound-alike (AIRO/EYRO) is never flagged."""
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return False
    if seq_ratio(a, b) >= TEXT_MISMATCH_FUZZY_CEIL:
        return False
    if phonetic_ratio(a, b) >= TEXT_MISMATCH_FUZZY_CEIL:
        return False
    return True


_ocr_engine = None
_ocr_cache  = {}  # md5(image bytes) -> recognized text ("" = unreadable/unavailable)


def _get_ocr_engine():
    """Lazy singleton - PaddleOCR takes ~2s to construct (model load), so it
    must not happen at import time or per-call."""
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from paddleocr import PaddleOCR
            # enable_mkldnn=False: PP-OCRv6's detection model hits an
            # unimplemented oneDNN CPU op on this paddlepaddle build
            # (NotImplementedError: ConvertPirAttribute2RuntimeAttribute) -
            # confirmed by direct reproduction; plain CPU kernels work fine.
            _ocr_engine = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                lang='en',
                enable_mkldnn=False,
            )
        except Exception:
            _ocr_engine = False  # sentinel: OCR unavailable, don't retry every call
    return _ocr_engine


def ocr_text_bytes(b: bytes) -> str:
    """Best-effort literal text read off a logo crop, normalized the same
    way as trademark names. Returns "" if OCR is unavailable or found
    nothing above OCR_MIN_CONFIDENCE - callers must treat "" as "no
    evidence", never as proof the image has no text."""
    if not b:
        return ""
    key = hashlib.md5(b).hexdigest()
    if key in _ocr_cache:
        return _ocr_cache[key]

    text = ""
    engine = _get_ocr_engine()
    if engine:
        try:
            img = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                # Measured directly: OCR on full-size DB crops (150-290KB)
                # took 3.5-9.7s each vs ~0.6-1s on small ones - PaddleOCR's
                # CPU graph re-specializes per input shape it hasn't seen
                # before, so large/irregular sizes are disproportionately
                # slow. A short wordmark needs no more than ~320px on the
                # long side to read; downscaling first turned the 9.7s worst
                # case into well under a second (verified).
                h, w = img.shape[:2]
                longest = max(h, w)
                if longest > OCR_MAX_DIM:
                    scale = OCR_MAX_DIM / longest
                    img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))),
                                      interpolation=cv2.INTER_AREA)
                for res in engine.predict(img):
                    texts  = res.get('rec_texts')  or []
                    scores = res.get('rec_scores') or []
                    kept   = [t for t, s in zip(texts, scores) if s >= OCR_MIN_CONFIDENCE]
                    text   = normalize(" ".join(kept))
        except Exception:
            text = ""

    _ocr_cache[key] = text
    return text


def phash_score_bytes(b1: bytes, b2: bytes) -> float:
    try:
        h1   = imagehash.phash(PILImage.open(io.BytesIO(b1)).convert('RGB'))
        h2   = imagehash.phash(PILImage.open(io.BytesIO(b2)).convert('RGB'))
        dist = (h1 - h2)
        return max(0.0, 1.0 - dist / 64.0)
    except Exception:
        return 0.0


ORB_MIN_KEYPOINTS = 15  # below this, too few keypoints for the match score to mean anything


def orb_match_score_bytes(b1: bytes, b2: bytes):
    """Returns (score, reliable). reliable=False when either image has too few
    detectable keypoints (e.g. a plain icon with little internal texture) —
    callers should not treat an unreliable near-zero score as evidence of
    dissimilarity, since ORB simply couldn't get a meaningful read at all."""
    try:
        a = cv2.imdecode(np.frombuffer(b1, np.uint8), cv2.IMREAD_GRAYSCALE)
        b = cv2.imdecode(np.frombuffer(b2, np.uint8), cv2.IMREAD_GRAYSCALE)
        if a is None or b is None:
            return 0.0, False

        orb    = cv2.ORB_create(500)
        k1, d1 = orb.detectAndCompute(a, None)
        k2, d2 = orb.detectAndCompute(b, None)
        if d1 is None or d2 is None:
            return 0.0, False

        bf      = cv2.BFMatcher(cv2.NORM_HAMMING)
        matches = bf.knnMatch(d1, d2, k=2)
        good    = 0
        for m_n in matches:
            if len(m_n) < 2:
                continue
            m, n = m_n
            if m.distance < 0.75 * n.distance:
                good += 1
        smaller_count = min(len(k1), len(k2))
        denom = max(1, smaller_count)
        return float(good) / denom, smaller_count >= ORB_MIN_KEYPOINTS
    except Exception:
        return 0.0, False


def score_match(q_name_raw, db_name_raw, q_logo_bytes, db_logo_bytes, t_ai, l_ai, q_has_img):
    """
    Blend text + image signals into a single match decision.
    Mirrors the logic previously inline in app.py's perform_comparison() 1:1.

    t_ai / l_ai: CLIP cosine similarities for text/image, already looked up
                 from the FAISS search results by the caller.
    q_has_img:   whether the query item has a usable logo image.
    """
    q_name  = normalize(q_name_raw)
    db_name = normalize(db_name_raw)

    if not q_name or not db_name:
        literal = 0.0
    elif q_name == db_name:
        literal = 1.0
    elif q_name in db_name or db_name in q_name:
        literal = TEXT_LITERAL_SUBSTRING_SCORE
    else:
        literal = 0.0

    fuzzy    = seq_ratio(q_name, db_name) if (q_name and db_name) else 0.0
    phonetic = phonetic_ratio(q_name, db_name)
    text_sim = max(literal, t_ai * CLIP_TEXT_WEIGHT, fuzzy * FUZZY_TEXT_WEIGHT, phonetic * PHONETIC_TEXT_WEIGHT)

    pixel_sim = phash_score_bytes(q_logo_bytes, db_logo_bytes) if (q_has_img and db_logo_bytes) else 0.0
    if q_has_img and db_logo_bytes:
        orb_sim, orb_reliable = orb_match_score_bytes(q_logo_bytes, db_logo_bytes)
    else:
        orb_sim, orb_reliable = 0.0, False
    # min(), not max(): eval showed phash alone gives false agreement on unrelated
    # logos while ORB stays near-zero — both signals must agree there's real
    # structural similarity to trust l_ai. But ORB needs enough keypoints to mean
    # anything (a plain icon with little texture yields near-zero regardless of
    # similarity) — fall back to phash alone when ORB couldn't get a reliable read.
    if orb_reliable:
        corroboration, ceiling = min(pixel_sim, orb_sim), PHASH_DISAGREEMENT_CEILING
    else:
        corroboration, ceiling = pixel_sim, PHASH_ONLY_FALLBACK_FLOOR
    img_sim = (
        l_ai * PHASH_DAMPENING_FACTOR
        if corroboration < ceiling
        else max(l_ai, pixel_sim, orb_sim)
    )

    # Same-font-different-word guard (see constants above). Registered
    # names first - cheap, no image decoding; OCR only as a fallback when
    # a name is missing, and only when img_sim is already high enough that
    # the false-positive pattern could actually occur (worth the ~0.5-0.7s
    # OCR call).
    text_mismatch = "none"
    if _clearly_different(q_name, db_name):
        img_sim *= NAME_MISMATCH_DAMPENING
        text_mismatch = "name"
    elif img_sim >= OCR_TRIGGER_FLOOR and q_has_img and db_logo_bytes:
        q_ocr, db_ocr = ocr_text_bytes(q_logo_bytes), ocr_text_bytes(db_logo_bytes)
        if _clearly_different(q_ocr, db_ocr):
            img_sim *= OCR_MISMATCH_DAMPENING
            text_mismatch = "ocr"

    if img_sim > IMG_SIM_SATURATION:
        img_sim = 1.0

    if q_has_img and q_name_raw:
        threshold = MATCH_THRESHOLD_WITH_IMAGE_AND_NAME
    elif q_has_img:
        threshold = MATCH_THRESHOLD_IMAGE_ONLY
    elif q_name_raw:
        threshold = MATCH_THRESHOLD_NAME_ONLY
    else:
        threshold = 1.0

    include = img_sim >= threshold or text_sim >= threshold

    return {
        "text_sim":      text_sim,
        "img_sim":       img_sim,
        "threshold":     threshold,
        "include":       include,
        # "none" | "name" | "ocr" - which signal (if any) proved the words differ
        "text_mismatch": text_mismatch,
    }
