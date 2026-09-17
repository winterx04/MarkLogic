"""
Nice Classification cross-search mapping, from Appendix 1 - Cross-Search List.pdf
("Cross Search List for Classes.pdf").

Semantics
---------
CLASS_INDEX[n] = list of classes that must ALSO be searched when a mark is
filed in class n, per the source document's "SEARCH ALSO" column. This is
the table AS PRINTED - it is not made symmetric (class A listing class B does
not imply class B's entry lists class A back), per the source being a legal
reference document rather than a derived graph.

This module only expands "which classes to sweep". It does NOT decide
whether a conflict found in one of the mark's own filed classes should be
flagged differently from one found only via cross-search - that distinction
belongs in the matching/scoring code (e.g. similarity.py), by comparing a
candidate's class against the query mark's own class_indices before/after
calling expand_classes() below.

Known irregularities to verify against the source PDF before relying on this
in production (flagged rather than silently "corrected"):
  - Class 3: row includes 35 (Business services of related industry) even
    though the "if it includes" examples read like pure goods - confirm.
  - Class 4, 37, 39, 43, 44: each lists ITSELF in its own "search also"
    column in the source table (e.g. class 37 -> [... ,37, ...]). Kept as
    printed; may be an artifact of the original document's table layout.
  - Class 35, 40, 42: "catch-all" rows in the source read as ranges
    ("1 to 36", "1 to 34", "1 to 42"). Expanded literally below into full
    class lists per your instruction to keep catch-alls as-is rather than
    using a sentinel - this means these three classes map to nearly every
    other class.
  - Several description cells reference a class number in parentheses that
    does NOT appear in that row's class-number column (e.g. class 3's
    description mentions "(43) Hairdressing salons" and "(4) Preservatives
    for leather", not present in class 3's own listed [5,21,35,40,42,44]).
    Only the explicit class-number column was used here; the parenthetical
    text was not used to infer additional classes.
"""

CLASS_INDEX = {
    1: [2, 5, 9, 16, 17, 35, 40, 42, 44],
    2: [1, 16, 17, 35, 37, 40, 42],
    3: [5, 21, 35, 40, 42, 44],
    4: [1, 3, 4, 35, 37, 39, 40, 42],  # self-reference (4) as printed - verify
    5: [1, 3, 10, 29, 30, 35, 40, 42, 44],
    6: [14, 19, 20, 26, 28, 35, 37, 40, 42],
    7: [8, 9, 11, 12, 21, 35, 37, 40, 42, 44],
    8: [7, 35, 40, 42, 44],
    9: [1, 7, 15, 35, 37, 38, 40, 41, 42, 45],
    10: [5, 35, 40, 42, 43, 44],
    11: [7, 21, 35, 37, 39, 40, 42, 43],
    12: [7, 35, 37, 39, 40, 42],
    13: [35, 37, 40, 45],
    14: [6, 20, 34, 35, 36, 37, 40, 42],
    15: [9, 35, 37, 41, 42],
    16: [1, 2, 17, 20, 21, 28, 35, 37, 38, 40, 41, 42],
    17: [1, 2, 35, 37, 40, 42, 44],
    18: [22, 35, 37, 40, 42, 44],
    19: [6, 35, 37, 40, 42],
    20: [6, 14, 16, 35, 37, 40, 45],
    21: [7, 16, 35, 40, 42, 43],
    22: [18, 35, 40, 42, 43, 44],
    23: [35, 40, 42, 44],
    24: [25, 26, 35, 37, 40, 42],
    25: [24, 40, 41, 42, 45],
    26: [6, 24, 25, 35, 40, 42, 44],
    27: [35, 37, 40, 42],
    28: [6, 16, 35, 37, 40, 41, 42],
    29: [5, 30, 31, 32, 35, 40, 42, 43, 44],
    30: [5, 29, 31, 35, 40, 42, 43, 44],
    31: [29, 30, 35, 40, 41, 42, 43, 44],
    32: [29, 33, 35, 40, 42, 43, 44],
    33: [32, 35, 40, 42, 43],
    34: [14, 35, 40, 42, 44],
    # Catch-all row: source reads "1 to 36" plus 38,41,42,43,44,45.
    35: list(range(1, 37)) + [38, 41, 42, 43, 44, 45],
    36: [14, 16, 35, 39, 42, 44, 45],
    # Self-reference (37) as printed - verify.
    37: [4, 6, 7, 9, 11, 12, 13, 14, 15, 16, 37, 38, 39, 40, 42, 44, 45],
    38: [9, 16, 35, 37, 39, 41, 42, 43, 44, 45],
    39: [4, 11, 12, 36, 37, 38, 39, 42, 44],  # self-reference (39) as printed - verify
    # Catch-all row: source reads "1 to 34" plus 37,40,42.
    40: list(range(1, 35)) + [37, 40, 42],
    41: [9, 15, 16, 25, 28, 31, 35, 38, 41, 44],
    # Catch-all row: source reads "1 to 42" plus 44.
    42: list(range(1, 43)) + [44],
    43: [9, 16, 29, 30, 31, 32, 33, 35, 39, 41, 43, 44],  # self-reference (43) - verify
    44: [1, 5, 10, 16, 31, 35, 39, 42, 44],  # self-reference (44) - verify
    45: [9, 12, 16, 20, 25, 28, 35, 36, 38, 39, 41, 42],
}


def get_search_classes(class_no):
    """Return the list of classes to also search for a given filed class, as printed."""
    return CLASS_INDEX.get(class_no, [])


def expand_classes(classes):
    """
    Given a mark's filed classes (e.g. [1, 5, 10] for the Nike example), return
    the union of those classes plus every class each one says to also search.

    The result INCLUDES the original filed classes, so a caller comparing a
    candidate's class against this set cannot distinguish "same class as
    filed" from "reached via cross-search" - do that comparison against the
    original `classes` argument directly, before calling this function, if
    that distinction needs to be flagged.
    """
    result = set(classes)
    for c in classes:
        result.update(get_search_classes(c))
    return result
