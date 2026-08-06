# eval/eval_similarity.py
#
# Runs the bootstrapped labeled pairs (eval/bootstrap_pairs.csv) through
# similarity.score_match() and reports precision/recall/F1 against the
# current thresholds, plus a threshold-sweep table so future changes to
# similarity.py can be measured instead of guessed.
#
# Usage:
#   uv run eval/eval_similarity.py [--pairs eval/bootstrap_pairs.csv]

import argparse
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db
import similarity

DEFAULT_PAIRS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bootstrap_pairs.csv")
SWEEP_THRESHOLDS = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]


def load_pairs(path):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return [(int(r["query_id"]), int(r["candidate_id"]), r["label"], r["source"]) for r in reader]


def fetch_rows_by_id(ids):
    conn = db.get_db_connection()
    cur  = conn.cursor()
    cur.execute(
        """SELECT id, trademark_name, applicant_name, logo_data, logo_embedding, text_embedding
           FROM trademarks WHERE id = ANY(%s)""",
        (list(ids),),
    )
    cols = ["id", "trademark_name", "applicant_name", "logo_data", "logo_embedding", "text_embedding"]
    rows = {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}
    cur.close()
    conn.close()
    return rows


def cosine_sim(vec_a_bytes, vec_b_bytes, dim):
    if not vec_a_bytes or not vec_b_bytes:
        return 0.0
    a = np.frombuffer(vec_a_bytes, dtype=np.float32)
    b = np.frombuffer(vec_b_bytes, dtype=np.float32)
    if a.shape[0] != dim or b.shape[0] != dim:
        return 0.0
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def evaluate(pairs, rows):
    scored = []  # (qid, cid, label, text_sim, img_sim, include, threshold, t_ai, l_ai, pixel_sim, orb_sim)
    skipped = 0

    for qid, cid, label, source in pairs:
        a, b = rows.get(qid), rows.get(cid)
        if not a or not b:
            skipped += 1
            continue

        t_ai = cosine_sim(a["text_embedding"], b["text_embedding"], similarity.TEXT_EMBEDDING_DIM)
        l_ai = cosine_sim(a["logo_embedding"], b["logo_embedding"], similarity.IMAGE_EMBEDDING_DIM)
        q_has_img = bool(a["logo_data"]) and bool(b["logo_data"])

        q_name = a["trademark_name"] or a["applicant_name"] or ""
        db_name = b["trademark_name"] or b["applicant_name"] or ""

        result = similarity.score_match(q_name, db_name, a["logo_data"], b["logo_data"], t_ai, l_ai, q_has_img)

        pixel_sim = similarity.phash_score_bytes(a["logo_data"], b["logo_data"]) if (q_has_img and b["logo_data"]) else 0.0
        if q_has_img and b["logo_data"]:
            orb_sim, orb_reliable = similarity.orb_match_score_bytes(a["logo_data"], b["logo_data"])
        else:
            orb_sim, orb_reliable = 0.0, False

        scored.append((qid, cid, label, result["text_sim"], result["img_sim"], result["include"],
                       result["threshold"], t_ai, l_ai, pixel_sim, orb_sim))

    if skipped:
        print(f"  (skipped {skipped} pairs referencing rows outside the sampled/limit window)")

    return scored


def report_true_match_signals(scored):
    """Print raw signal values for known true matches, to sanity-check that a
    proposed corroboration rule (e.g. min(phash, orb)) wouldn't itself dampen
    the real positives before adopting it."""
    matches = [s for s in scored if s[2] == "match"]
    if not matches:
        return
    print("=== Raw signals for known true-match pairs ===")
    for qid, cid, label, text_sim, img_sim, include, threshold, t_ai, l_ai, pixel_sim, orb_sim in matches:
        print(f"  query={qid} candidate={cid}  t_ai={t_ai:.3f}  l_ai={l_ai:.3f}  "
              f"phash={pixel_sim:.3f}  orb={orb_sim:.3f}  img_sim={img_sim:.3f}  include={include}")
    print()


def report_fp_breakdown(scored):
    """
    Diagnose WHICH channel (text vs image) is driving false positives at the
    production threshold, so threshold/weight changes target the right lever
    instead of guessing.
    """
    fps = [s for s in scored if s[2] == "no_match" and s[5]]
    if not fps:
        print("No false positives at the production threshold — nothing to break down.\n")
        return

    text_only = img_only = both = 0
    for qid, cid, label, text_sim, img_sim, include, threshold, t_ai, l_ai, pixel_sim, orb_sim in fps:
        text_over = text_sim >= threshold
        img_over  = img_sim  >= threshold
        if text_over and img_over:
            both += 1
        elif text_over:
            text_only += 1
        elif img_over:
            img_only += 1

    n = len(fps)
    print("=== False-positive driver breakdown (production threshold) ===")
    print(f"  total false positives: {n}")
    print(f"  triggered by text_sim only: {text_only} ({text_only/n:.0%})")
    print(f"  triggered by img_sim  only: {img_only} ({img_only/n:.0%})")
    print(f"  triggered by both:          {both} ({both/n:.0%})")
    avg_t_ai      = sum(s[7]  for s in fps) / n
    avg_l_ai      = sum(s[8]  for s in fps) / n
    avg_pixel_sim = sum(s[9]  for s in fps) / n
    avg_orb_sim   = sum(s[10] for s in fps) / n
    print(f"  avg raw t_ai (text CLIP cosine) among FPs: {avg_t_ai:.3f}")
    print(f"  avg raw l_ai (image CLIP cosine) among FPs: {avg_l_ai:.3f}")
    print(f"  avg phash sim among FPs: {avg_pixel_sim:.3f}")
    print(f"  avg ORB sim among FPs:   {avg_orb_sim:.3f}\n")


def report_ranking(scored):
    """
    /compare only ever shows the TOP 3 ranked candidates per query — so what
    matters in practice is whether the true match outranks the noise for its
    own query, not raw precision/recall against a flat threshold. Group by
    query_id and check: does the true "match" candidate score highest (or
    top-3) among all candidates gathered for that same query?
    """
    by_query = {}
    for qid, cid, label, text_sim, img_sim, include, threshold, t_ai, l_ai, pixel_sim, orb_sim in scored:
        by_query.setdefault(qid, []).append((cid, label, max(text_sim, img_sim)))

    queries_with_match = {qid: cands for qid, cands in by_query.items()
                          if any(label == "match" for _, label, _ in cands)}

    if not queries_with_match:
        print("No query in the bootstrap set has both a match and non-match candidate to rank against.")
        return

    hit_at_1 = 0
    hit_at_3 = 0
    reciprocal_ranks = []
    for qid, cands in queries_with_match.items():
        ranked = sorted(cands, key=lambda c: c[2], reverse=True)
        match_rank = next(i for i, (cid, label, score) in enumerate(ranked, start=1) if label == "match")
        reciprocal_ranks.append(1.0 / match_rank)
        if match_rank == 1:
            hit_at_1 += 1
        if match_rank <= 3:
            hit_at_3 += 1

    n = len(queries_with_match)
    mrr = sum(reciprocal_ranks) / n
    print(f"=== Per-query ranking (what a real /compare user would actually see) ===")
    print(f"  queries evaluated: {n}")
    print(f"  hit@1 (true match ranked #1): {hit_at_1}/{n} ({hit_at_1/n:.0%})")
    print(f"  hit@3 (true match in top 3):  {hit_at_3}/{n} ({hit_at_3/n:.0%})")
    print(f"  mean reciprocal rank: {mrr:.3f}\n")


def confusion(scored, predicate):
    tp = fp = fn = tn = 0
    for qid, cid, label, text_sim, img_sim, include, threshold, t_ai, l_ai, pixel_sim, orb_sim in scored:
        pred_match = predicate(text_sim, img_sim, include)
        actual_match = (label == "match")
        if pred_match and actual_match: tp += 1
        elif pred_match and not actual_match: fp += 1
        elif not pred_match and actual_match: fn += 1
        else: tn += 1
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall    = tp / (tp + fn) if (tp + fn) else float("nan")
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) and precision == precision and recall == recall and (precision + recall) > 0 else float("nan")
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall, "f1": f1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=DEFAULT_PAIRS_PATH)
    args = ap.parse_args()

    if not os.path.exists(args.pairs):
        print(f"No pairs file at {args.pairs} — run generate_bootstrap_pairs.py first.")
        return

    pairs = load_pairs(args.pairs)
    print(f"Loaded {len(pairs)} labeled pairs from {args.pairs}")

    ids = set()
    for qid, cid, _, _ in pairs:
        ids.add(qid); ids.add(cid)
    rows = fetch_rows_by_id(ids)
    print(f"Fetched {len(rows)} distinct rows for those pairs\n")

    scored = evaluate(pairs, rows)
    if not scored:
        print("No pairs could be scored (missing rows/embeddings).")
        return

    n_match = sum(1 for s in scored if s[2] == "match")
    n_no_match = len(scored) - n_match
    print(f"Scored {len(scored)} pairs ({n_match} match / {n_no_match} no_match)\n")

    report_ranking(scored)

    print("=== Current production logic (similarity.score_match's own threshold) ===")
    current = confusion(scored, lambda t, i, inc: inc)
    print(f"  TP={current['tp']} FP={current['fp']} FN={current['fn']} TN={current['tn']}")
    print(f"  precision={current['precision']:.3f}  recall={current['recall']:.3f}  f1={current['f1']:.3f}\n")

    report_true_match_signals(scored)
    report_fp_breakdown(scored)

    print("=== Uniform threshold sweep (diagnostic only — include if text_sim>=t or img_sim>=t) ===")
    print(f"  {'threshold':>9}  {'precision':>9}  {'recall':>9}  {'f1':>9}  {'TP':>4}  {'FP':>4}  {'FN':>4}  {'TN':>4}")
    for t in SWEEP_THRESHOLDS:
        res = confusion(scored, lambda text_sim, img_sim, inc, t=t: (text_sim >= t or img_sim >= t))
        print(f"  {t:>9.2f}  {res['precision']:>9.3f}  {res['recall']:>9.3f}  {res['f1']:>9.3f}  "
              f"{res['tp']:>4}  {res['fp']:>4}  {res['fn']:>4}  {res['tn']:>4}")


if __name__ == "__main__":
    main()
