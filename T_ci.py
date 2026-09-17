# T_ci.py - quick sanity checks for class_index.py, plus an interactive lookup
# Run with: python T_ci.py
# Or skip straight to the lookup: python T_ci.py 1,5,10

import sys

import class_index as ci

failures = []


# def check(label, condition):
#     status = "PASS" if condition else "FAIL"
#     print(f"[{status}] {label}")
#     if not condition:
#         failures.append(label)


# 1. Every Nice class 1-45 has an entry, and it's a non-empty list of ints.
# missing = [n for n in range(1, 46) if n not in ci.CLASS_INDEX]
# check("all classes 1-45 present in CLASS_INDEX", not missing)

# empty = [n for n, v in ci.CLASS_INDEX.items() if not v]
# check("no class maps to an empty list", not empty)

# bad_types = [
#     n for n, v in ci.CLASS_INDEX.items()
#     if not all(isinstance(x, int) for x in v)
# ]
# check("every search-also entry is an int", not bad_types)

# # 2. get_search_classes() mirrors CLASS_INDEX exactly.
# check(
#     "get_search_classes(1) matches CLASS_INDEX[1]",
#     ci.get_search_classes(1) == ci.CLASS_INDEX[1],
# )
# check(
#     "get_search_classes() returns [] for an unknown class",
#     ci.get_search_classes(999) == [],
# )

# # 3. Nike example from the brief: filed in [1, 5, 10].
# nike = ci.expand_classes([1, 5, 10])
# expected_nike = {1, 2, 3, 5, 9, 10, 16, 17, 29, 30, 35, 40, 42, 43, 44}
# check("expand_classes([1,5,10]) matches expected Nike sweep set", nike == expected_nike)
# check("expand_classes() always includes the original filed classes", {1, 5, 10} <= nike)

# # 4. Catch-all rows (35, 40, 42) should sweep in most of the classification.
# check("class 35 (catch-all) covers at least 40 classes", len(ci.CLASS_INDEX[35]) >= 40)
# check("class 40 (catch-all) covers at least 35 classes", len(ci.CLASS_INDEX[40]) >= 35)
# check("class 42 (catch-all) covers at least 40 classes", len(ci.CLASS_INDEX[42]) >= 40)

# print()
# if failures:
#     print(f"{len(failures)} check(s) failed: {failures}")
#     raise SystemExit(1)
# else:
#     print("All checks passed.")


# ---------------------------------------------------------------------------
# Interactive lookup: enter one class (e.g. 1) or several (e.g. 1,5,10) and
# see the full cross-search sweep set, split into "filed" vs "also search".
# ---------------------------------------------------------------------------

def parse_classes(raw):
    parts = raw.replace(",", " ").split()
    classes = []
    for p in parts:
        if not p.isdigit():
            raise ValueError(f"'{p}' is not a valid class number")
        n = int(p)
        if not 1 <= n <= 45:
            raise ValueError(f"{n} is out of range (Nice classes are 1-45)")
        classes.append(n)
    if not classes:
        raise ValueError("no class numbers given")
    return classes


def run_lookup(raw):
    try:
        classes = parse_classes(raw)
    except ValueError as e:
        print(f"Invalid input: {e}")
        return

    swept = sorted(ci.expand_classes(classes))
    also_search = sorted(set(swept) - set(classes))

    print()
    print(f"Filed classes:      {sorted(classes)}")
    print(f"Also search:         {also_search}")
    print(f"Full sweep set:      {swept}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_lookup(" ".join(sys.argv[1:]))
    else:
        print()
        raw = input("Enter class number(s), e.g. 1 or 1,5,10: ").strip()
        if raw:
            run_lookup(raw)
