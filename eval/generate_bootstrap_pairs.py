# eval/generate_bootstrap_pairs.py
#
# Bootstraps a labeled evaluation set for trademark-matching accuracy directly
# from existing `trademarks` data, since no hand-reviewed ground truth exists
# yet. This is a statistical PROXY, not verified legal judgment — it catches
# obvious regressions (a known duplicate stops matching, an unrelated pair
# starts matching) but won't surface subtler true-conflict-but-different-name
# cases. Swap in real attorney-reviewed pairs later under the same CSV schema
# (query_id, candidate_id, label, source) once available.
#
# Usage:
#   uv run eval/generate_bootstrap_pairs.py [--category MYIPO] [--limit 3000]

import argparse
import csv
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db
import similarity

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bootstrap_pairs.csv")

MAX_MATCH_PAIRS_PER_GROUP  = 3
MAX_HARD_NEGATIVE_PAIRS    = 150
MAX_RANDOM_NEGATIVE_PAIRS  = 150
NAME_OVERLAP_CEILING       = 0.3   # below this seq_ratio, two names are "clearly different"


def fetch_rows(category, limit):
    conn = db.get_db_connection()
    cur  = conn.cursor()
    if category:
        cur.execute(
            """SELECT id, serial_number, trademark_name, applicant_name, class_indices,
                      logo_data, logo_embedding, text_embedding
               FROM trademarks
               WHERE category = %s AND logo_embedding IS NOT NULL AND text_embedding IS NOT NULL
               ORDER BY id LIMIT %s""",
            (category, limit),
        )
    else:
        cur.execute(
            """SELECT id, serial_number, trademark_name, applicant_name, class_indices,
                      logo_data, logo_embedding, text_embedding
               FROM trademarks
               WHERE logo_embedding IS NOT NULL AND text_embedding IS NOT NULL
               ORDER BY id LIMIT %s""",
            (limit,),
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    cols = ["id", "serial_number", "trademark_name", "applicant_name", "class_indices",
            "logo_data", "logo_embedding", "text_embedding"]
    return [dict(zip(cols, r)) for r in rows]


def primary_class(class_indices):
    if not class_indices:
        return None
    token = class_indices.replace(",", " ").split()
    return token[0] if token else None


def build_pairs(rows):
    pairs = []  # (query_id, candidate_id, label, source)

    # ── Likely-match: same normalized name, different DB rows ──
    by_name = {}
    for row in rows:
        name = similarity.normalize(row["trademark_name"] or row["applicant_name"] or "")
        if not name:
            continue
        by_name.setdefault(name, []).append(row["id"])

    for name, ids in by_name.items():
        if len(ids) < 2:
            continue
        random.shuffle(ids)
        made = 0
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if made >= MAX_MATCH_PAIRS_PER_GROUP:
                    break
                pairs.append((ids[i], ids[j], "match", "bootstrap_same_name"))
                made += 1
            if made >= MAX_MATCH_PAIRS_PER_GROUP:
                break

    # ── Hard negatives: same primary class, clearly different name ──
    by_class = {}
    for row in rows:
        cls = primary_class(row["class_indices"])
        if not cls:
            continue
        by_class.setdefault(cls, []).append(row)

    hard_neg = []
    for cls, group in by_class.items():
        if len(group) < 2:
            continue
        sample = group[:] if len(group) <= 30 else random.sample(group, 30)
        for i in range(len(sample)):
            for j in range(i + 1, len(sample)):
                a, b = sample[i], sample[j]
                name_a = similarity.normalize(a["trademark_name"] or a["applicant_name"] or "")
                name_b = similarity.normalize(b["trademark_name"] or b["applicant_name"] or "")
                if not name_a or not name_b or name_a == name_b:
                    continue
                if similarity.seq_ratio(name_a, name_b) >= NAME_OVERLAP_CEILING:
                    continue
                hard_neg.append((a["id"], b["id"]))
    random.shuffle(hard_neg)
    for qid, cid in hard_neg[:MAX_HARD_NEGATIVE_PAIRS]:
        pairs.append((qid, cid, "no_match", "bootstrap_hard_negative"))

    # ── Random negatives: unrelated pairs, any class ──
    random_neg = []
    attempts = 0
    ids_all = [r["id"] for r in rows]
    row_by_id = {r["id"]: r for r in rows}
    while len(random_neg) < MAX_RANDOM_NEGATIVE_PAIRS and attempts < MAX_RANDOM_NEGATIVE_PAIRS * 20 and len(ids_all) >= 2:
        attempts += 1
        qid, cid = random.sample(ids_all, 2)
        a, b = row_by_id[qid], row_by_id[cid]
        name_a = similarity.normalize(a["trademark_name"] or a["applicant_name"] or "")
        name_b = similarity.normalize(b["trademark_name"] or b["applicant_name"] or "")
        if name_a and name_b and similarity.seq_ratio(name_a, name_b) < NAME_OVERLAP_CEILING:
            random_neg.append((qid, cid))
    for qid, cid in random_neg:
        pairs.append((qid, cid, "no_match", "bootstrap_random_negative"))

    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default=None, help="Restrict to one category (e.g. MYIPO)")
    ap.add_argument("--limit", type=int, default=3000, help="Max rows to pull from trademarks")
    args = ap.parse_args()

    print(f"Fetching up to {args.limit} rows (category={args.category or 'ALL'})...")
    rows = fetch_rows(args.category, args.limit)
    print(f"  {len(rows)} rows with both embeddings present")

    if len(rows) < 2:
        print("Not enough rows with embeddings to bootstrap pairs. Import more data first.")
        return

    pairs = build_pairs(rows)
    match_n    = sum(1 for p in pairs if p[2] == "match")
    no_match_n = sum(1 for p in pairs if p[2] == "no_match")
    print(f"  Built {len(pairs)} pairs ({match_n} match / {no_match_n} no_match)")

    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["query_id", "candidate_id", "label", "source"])
        writer.writerows(pairs)

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
