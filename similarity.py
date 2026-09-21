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

# ── Color guard ──────────────────────────────────────────────────────────
# phash and ORB both work on grayscale - they're blind to color entirely,
# so two logos with identical silhouettes but obviously different claimed
# colors (real field seen in production data: "COLOURS CLAIMED : RED, BLUE
# AND BLACK") would otherwise score identically under those two signals.
# Softer than the text-mismatch dampening: color alone isn't dispositive
# of a different mark (many marks are registered without color limitation),
# so this only nudges the score down, never vetoes.
COLOR_MISMATCH_CEILING   = 0.35  # below this HSV histogram correlation, colors are "clearly different"
COLOR_MISMATCH_DAMPENING = 0.75
COLOR_MIN_PIXELS         = 50    # below this many non-transparent pixels, a color read is unreliable

# The old dampening (multiplying img_sim by ~0.4x on corroboration
# disagreement) was doing double duty: destructive to real matches (the
# Kinder Bueno bug), but it ALSO acted as a much-higher effective bar for
# anything that failed corroboration - no disagreeing candidate could
# mathematically survive that cut and still clear MATCH_THRESHOLD_*.
# Removing the dampening fixed the destructive part but also removed that
# implicit filter: CLIP's raw cosine similarity turns out to be a
# generously low bar for generic round/badge-shaped logos, so without a
# separate floor, "review" flooded with weakly-related candidates
# (confirmed real case: unrelated logos at 58-68% raw confidence all
# surfaced once corroboration no longer suppressed them). A disagreeing
# candidate now needs CLIP to be genuinely confident, not just past the
# base threshold, before it's worth a human's time.
REVIEW_CONFIDENCE_FLOOR = 0.70

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


ORB_MIN_KEYPOINTS       = 15   # below this, too few keypoints for the match score to mean anything
RANSAC_MIN_MATCHES      = 8    # below this, too few points to fit/trust a homography - fall back to raw ratio-test count
RANSAC_REPROJ_THRESHOLD = 5.0  # pixels - standard default for logo-scale crops


def orb_match_score_bytes(b1: bytes, b2: bytes):
    """Returns (score, reliable). reliable=False when either image has too few
    detectable keypoints (e.g. a plain icon with little internal texture) —
    callers should not treat an unreliable near-zero score as evidence of
    dissimilarity, since ORB simply couldn't get a meaningful read at all.

    Matches are geometrically verified via RANSAC homography fitting when
    there are enough of them - counting only inliers (keypoints consistent
    with a single coherent transform between the two images), not just raw
    ratio-test matches. Two unrelated logos can accumulate coincidental
    keypoint matches that individually pass the ratio test but are
    scattered incoherently across the image; a plain match count can't
    tell that apart from a real match, RANSAC can."""
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
        good    = []
        for m_n in matches:
            if len(m_n) < 2:
                continue
            m, n = m_n
            if m.distance < 0.75 * n.distance:
                good.append(m)

        smaller_count = min(len(k1), len(k2))
        reliable      = smaller_count >= ORB_MIN_KEYPOINTS
        denom         = max(1, smaller_count)

        if len(good) < RANSAC_MIN_MATCHES:
            # Too few points to fit/trust a homography - same behavior as
            # before RANSAC was added, not "no match".
            return float(len(good)) / denom, reliable

        src_pts = np.float32([k1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([k2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        _, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, RANSAC_REPROJ_THRESHOLD)
        inliers = int(mask.sum()) if mask is not None else 0

        return float(inliers) / denom, reliable
    except Exception:
        return 0.0, False


def _masked_hsv_hist(img):
    """HSV hue/saturation histogram, masked to non-transparent pixels only
    (our logo crops are saved with a transparent background via
    remove_white_bg_make_transparent() - background pixels would otherwise
    dilute the actual logo's color signature with whatever RGB happened to
    sit under the transparency)."""
    mask = None
    if img.ndim == 3 and img.shape[2] == 4:
        mask = img[:, :, 3]
        bgr  = img[:, :, :3]
    elif img.ndim == 3:
        bgr = img
    else:
        bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    non_transparent = int(np.count_nonzero(mask)) if mask is not None else bgr.shape[0] * bgr.shape[1]
    hsv  = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], mask, [50, 60], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist, non_transparent


def color_hist_score(b1: bytes, b2: bytes):
    """Returns (score, reliable). HSV histogram correlation over the
    non-transparent (actual logo ink) pixels only. reliable=False when
    either image has too few non-transparent pixels to build a meaningful
    histogram (e.g. a near-blank crop) - same "can't read it, not evidence
    of difference" philosophy as ORB_MIN_KEYPOINTS."""
    try:
        img1 = cv2.imdecode(np.frombuffer(b1, np.uint8), cv2.IMREAD_UNCHANGED)
        img2 = cv2.imdecode(np.frombuffer(b2, np.uint8), cv2.IMREAD_UNCHANGED)
        if img1 is None or img2 is None:
            return 0.0, False

        h1, n1 = _masked_hsv_hist(img1)
        h2, n2 = _masked_hsv_hist(img2)
        reliable = n1 >= COLOR_MIN_PIXELS and n2 >= COLOR_MIN_PIXELS

        corr = cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)
        return max(0.0, float(corr)), reliable
    except Exception:
        return 0.0, False


def score_match(q_name_raw, db_name_raw, q_logo_bytes, db_logo_bytes, t_ai, l_ai, q_has_img):
    """
    Blend text + image signals into a match decision.

    CONFIDENCE vs CORROBORATION are kept separate for the visual channel
    instead of collapsed into one mutated number. The old design
    multiplicatively dampened CLIP's raw confidence (l_ai) whenever
    phash/ORB/color disagreed - which repeatedly destroyed real matches
    whose only "problem" was a heuristic corroboration check that was
    never designed for the actual situation (confirmed: a genuine "Kinder
    Bueno Dark" match scored l_ai=0.83, but was silently dismissed at 25%
    because a partial-crop query broke phash/ORB/color's assumption of
    comparable framing between the two images - the mark was real, the
    corroboration check was just wrong for THIS case, and the old design
    had no way to distinguish "corroboration disagrees because this is a
    bad match" from "corroboration disagrees for an unrelated reason").
    Now: img_sim stays close to the raw confidence (still boosted when
    corroboration DOES agree - that's confirming information, not
    destroying it), visual_corroboration reports agree/disagree/unknown
    separately, and disagreement routes to a "review" tier for a human to
    check instead of silently vanishing.

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

    img_sim = l_ai
    # "agree" | "disagree" | "unknown" - unknown when there's no image on
    # one/both sides to corroborate against at all (not evidence either way).
    visual_corroboration = "unknown"

    if q_has_img and db_logo_bytes:
        pixel_sim                 = phash_score_bytes(q_logo_bytes, db_logo_bytes)
        orb_sim, orb_reliable     = orb_match_score_bytes(q_logo_bytes, db_logo_bytes)
        color_sim, color_reliable = color_hist_score(q_logo_bytes, db_logo_bytes)

        # min(), not max(): eval showed phash alone gives false agreement on
        # unrelated logos while ORB stays near-zero — both signals must agree
        # there's real structural similarity. But ORB needs enough keypoints
        # to mean anything (a plain icon with little texture yields near-zero
        # regardless of similarity) — fall back to phash alone when ORB
        # couldn't get a reliable read.
        if orb_reliable:
            po_corroboration, po_ceiling = min(pixel_sim, orb_sim), PHASH_DISAGREEMENT_CEILING
        else:
            po_corroboration, po_ceiling = pixel_sim, PHASH_ONLY_FALLBACK_FLOOR
        po_agrees = po_corroboration >= po_ceiling

        # phash/ORB are grayscale-blind - color is the only signal that
        # would catch "same shape, different claimed color" (real field
        # seen in production data: "COLOURS CLAIMED : RED, BLUE AND BLACK").
        color_agrees = (not color_reliable) or (color_sim >= COLOR_MISMATCH_CEILING)

        if po_agrees:
            img_sim = max(img_sim, pixel_sim, orb_sim)

        visual_corroboration = "agree" if (po_agrees and color_agrees) else "disagree"
        # A partial-crop query (e.g. a tight screenshot of a wider stored
        # composite) legitimately fails phash/ORB/color, which all assume
        # comparable framing - a dedicated template-matching "is this a
        # crop of that" check was tried here and REMOVED: normalized
        # cross-correlation turned out to not be discriminative enough
        # (confirmed: 4 unrelated logos scored 0.58-0.68 "containment"
        # against a real query, indistinguishable from a genuine crop's
        # 0.62, even after gating on local pixel variance). Not needed
        # anyway - a genuine partial-crop case with high CLIP confidence
        # already routes to "review" below instead of being silently
        # dismissed, which resolves the same underlying problem without
        # a separate, unreliable signal.

    # Same-font-different-word guard (see constants above). OCR reads the
    # actual logo pixels directly - more direct, dispositive evidence than
    # the visual-style corroboration above, so it stays a real dampening
    # veto rather than feeding the review-routing decision. When available,
    # it overrides the registered-name signal rather than being skipped
    # once the name check already fired. Confirmed necessary: a real
    # record's trademark_name was "pure" (a product line) while the logo
    # itself reads "DURU" (the brand name lives in applicant_name instead)
    # - a query for "DU" was wrongly dampened by the name check (0.6x,
    # 85.78%->51.47%) even though OCR of the actual logo correctly reads
    # "DURU", of which "DU" is a clean substring. Only checked when img_sim
    # is already high enough that the false-positive pattern could occur
    # (worth the ~0.5-0.7s OCR call).
    text_mismatch = "none"
    name_mismatch = _clearly_different(q_name, db_name)
    ocr_mismatch  = None  # None = not checked / no usable OCR evidence
    if img_sim >= OCR_TRIGGER_FLOOR and q_has_img and db_logo_bytes:
        q_ocr, db_ocr = ocr_text_bytes(q_logo_bytes), ocr_text_bytes(db_logo_bytes)
        if q_ocr and db_ocr:
            ocr_mismatch = _clearly_different(q_ocr, db_ocr)

    if ocr_mismatch is True:
        img_sim *= OCR_MISMATCH_DAMPENING
        text_mismatch = "ocr"
    elif ocr_mismatch is False:
        pass  # direct pixel evidence overrides a name-only mismatch - no dampening
    elif name_mismatch:
        img_sim *= NAME_MISMATCH_DAMPENING
        text_mismatch = "name"

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

    # Routing: crossing the threshold used to mean one binary thing
    # ("show it"). Now a candidate that clears threshold purely on visual
    # confidence, with no text-mismatch evidence either way, but whose
    # visual corroboration disagrees, gets routed to "review" instead of a
    # confident "match" - surfaced to a human instead of either silently
    # hidden (the old bug) or confidently mislabeled as verified.
    if text_sim >= threshold:
        match_tier = "match"
    elif img_sim >= threshold:
        if text_mismatch == "none" and visual_corroboration == "disagree":
            # See REVIEW_CONFIDENCE_FLOOR above - a disagreeing candidate
            # needs CLIP to be genuinely confident, not just past the base
            # threshold, or this tier floods with weak, generic matches.
            match_tier = "review" if img_sim >= REVIEW_CONFIDENCE_FLOOR else "dismiss"
        else:
            match_tier = "match"
    else:
        match_tier = "dismiss"

    include = match_tier != "dismiss"

    return {
        "text_sim":             text_sim,
        "img_sim":              img_sim,
        "threshold":            threshold,
        "include":              include,
        "match_tier":           match_tier,            # "match" | "review" | "dismiss"
        "visual_corroboration": visual_corroboration,   # "agree" | "disagree" | "unknown"
        # "none" | "name" | "ocr" - which signal (if any) proved the words differ
        "text_mismatch":        text_mismatch,
    }
