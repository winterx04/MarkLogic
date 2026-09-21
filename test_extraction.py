# test_extraction.py
# ─────────────────────────────────────────────────────────────
# Runs the real production extraction pipeline (pdf_extractor.py's
# UltraRobustExtractor) over a page range and prints each record's key
# fields plus any OCR cross-validation warnings (see
# UltraRobustExtractor.validate_fields_with_ocr) - a mismatch means
# find_blocks() likely grabbed text from the wrong region for that field.
#
# No database or Flask app needed - this calls the extractor directly.
#
# Usage:
#   python test_extraction.py --input journal.pdf --start_page 43 --max_pages 1
#   python test_extraction.py --input journal.pdf --start_page 1 --max_pages 50 --no-ocr-validation
# ─────────────────────────────────────────────────────────────

import argparse
import os

import pdfplumber

from pdf_extractor import UltraRobustExtractor


def main():
    parser = argparse.ArgumentParser(description="Test the production extraction pipeline on real pages.")
    parser.add_argument("--input",              required=True,             help="Path to the journal PDF")
    parser.add_argument("--start_page",         type=int, default=1,       help="First page to process (1-indexed)")
    parser.add_argument("--max_pages",          type=int, default=5,       help="How many pages to process")
    parser.add_argument("--no-ocr-validation",  action="store_true",       help="Skip the OCR cross-validation safety net")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[X] File not found: {args.input}")
        return

    extractor = UltraRobustExtractor(debug=True, enable_ocr_validation=not args.no_ocr_validation)

    total_records  = 0
    total_warnings = 0

    with pdfplumber.open(args.input) as pdf:
        total_pages = len(pdf.pages)
        end_page    = min(args.start_page + args.max_pages - 1, total_pages)
        pages_to_process = pdf.pages[args.start_page - 1:end_page]

        for offset, page in enumerate(pages_to_process):
            page_num = args.start_page + offset
            blocks   = extractor.find_blocks(page)
            if not blocks:
                continue

            print(f"\n=== Page {page_num}: {len(blocks)} record(s) ===")
            for block in blocks:
                result = extractor.extract_from_block(
                    page, block, page_num, pages_to_process, offset
                )
                if result is None:
                    continue

                total_records += 1
                warnings = result.get("validation_warnings", [])
                total_warnings += len(warnings)

                print(f"  serial={result['serial_number']!r}")
                print(f"    applicant = {result['applicant_name']!r}")
                print(f"    agent     = {(result['agent_details'] or '')[:70]!r}")
                print(f"    class     = {result['class_indices']!r}")
                if warnings:
                    print(f"    !!! VALIDATION WARNINGS: {warnings}")
                else:
                    print(f"    OK - no validation warnings")

    print(f"\nDone - {total_records} record(s), {total_warnings} validation warning(s) flagged")


if __name__ == "__main__":
    main()
