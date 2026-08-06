# similarity.py
# Pure trademark-matching scoring logic — no Flask, no DB, no network I/O.
# Extracted from app.py so it can be reused by both the /compare route and
# an offline evaluation harness (eval_similarity.py) without the two drifting apart.

import io
import re
from difflib import SequenceMatcher

import cv2
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
PHASH_DISAGREEMENT_CEILING     = 0.25
PHASH_DAMPENING_FACTOR         = 0.4
IMG_SIM_SATURATION             = 0.92

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


def phash_score_bytes(b1: bytes, b2: bytes) -> float:
    try:
        h1   = imagehash.phash(PILImage.open(io.BytesIO(b1)).convert('RGB'))
        h2   = imagehash.phash(PILImage.open(io.BytesIO(b2)).convert('RGB'))
        dist = (h1 - h2)
        return max(0.0, 1.0 - dist / 64.0)
    except Exception:
        return 0.0


def orb_match_score_bytes(b1: bytes, b2: bytes) -> float:
    try:
        a = cv2.imdecode(np.frombuffer(b1, np.uint8), cv2.IMREAD_GRAYSCALE)
        b = cv2.imdecode(np.frombuffer(b2, np.uint8), cv2.IMREAD_GRAYSCALE)
        if a is None or b is None:
            return 0.0

        orb    = cv2.ORB_create(500)
        k1, d1 = orb.detectAndCompute(a, None)
        k2, d2 = orb.detectAndCompute(b, None)
        if d1 is None or d2 is None:
            return 0.0

        bf      = cv2.BFMatcher(cv2.NORM_HAMMING)
        matches = bf.knnMatch(d1, d2, k=2)
        good    = 0
        for m_n in matches:
            if len(m_n) < 2:
                continue
            m, n = m_n
            if m.distance < 0.75 * n.distance:
                good += 1
        denom = max(1, min(len(k1), len(k2)))
        return float(good) / denom
    except Exception:
        return 0.0


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
    text_sim = max(literal, t_ai * CLIP_TEXT_WEIGHT, fuzzy * FUZZY_TEXT_WEIGHT)

    pixel_sim     = phash_score_bytes(q_logo_bytes, db_logo_bytes) if (q_has_img and db_logo_bytes) else 0.0
    orb_sim       = orb_match_score_bytes(q_logo_bytes, db_logo_bytes) if (q_has_img and db_logo_bytes) else 0.0
    # min(), not max(): eval showed phash alone gives false agreement on unrelated
    # logos (avg 0.517 on false positives) while ORB stays near-zero (0.035) —
    # both signals must agree there's real structural similarity to trust l_ai.
    corroboration = min(pixel_sim, orb_sim)
    img_sim = (
        l_ai * PHASH_DAMPENING_FACTOR
        if corroboration < PHASH_DISAGREEMENT_CEILING
        else max(l_ai, pixel_sim, orb_sim)
    )
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
        "text_sim":  text_sim,
        "img_sim":   img_sim,
        "threshold": threshold,
        "include":   include,
    }
