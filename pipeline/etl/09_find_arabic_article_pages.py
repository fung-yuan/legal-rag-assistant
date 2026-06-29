"""
09_find_arabic_article_pages.py
================================
Scans every Arabic Bulletin Officiel PDF and finds the exact page where
each article (مادة / فصل) begins. Updates the Arabic stub provisions in
the database so the PDF viewer opens at the correct page.

Strategy (avoids full OCR quality dependency):
  - Render each page to an image at 150 DPI
  - Try PyMuPDF native text first (instant; works for digital PDFs)
  - Fall back to Tesseract Arabic OCR for scanned pages
  - Use the ARTICLE NUMBER as the primary anchor (numbers are not
    cursive so they survive poor scan quality far better than Arabic words)
  - Accept both Western (9) and Arabic-Indic (٩) numerals
  - Also detect "Article premier" / "الأول" spelled-out ordinals

Parallelism:
  - Pages within each PDF are processed in parallel (ProcessPoolExecutor)
  - PDFs are processed sequentially one by one

Resumability:
  - Per-bulletin JSON cache in data/ar_page_index/
  - Already-cached bulletins are skipped on re-run

Runtime estimate: ~30-45 min for 516 PDFs / ~13 k pages with 12 workers

Usage:
    python pipeline/etl/09_find_arabic_article_pages.py
    python pipeline/etl/09_find_arabic_article_pages.py --force   # redo all
    python pipeline/etl/09_find_arabic_article_pages.py --test    # first 5 PDFs only
"""

import os
import re
import sys
import json
import time
import sqlite3
import logging
import argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import fitz          # PyMuPDF
import pytesseract
from PIL import Image
import io

# ── Config ───────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).resolve().parents[2]
AR_PDF_DIR    = BASE_DIR / "data" / "raw_pdfs"
CACHE_DIR     = BASE_DIR / "data" / "ar_page_index"
DB_PATH       = BASE_DIR / "data" / "database.db"
LOG_FILE      = BASE_DIR / "data" / "logs" / "09_arabic_page_finder.log"

TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR  = str(Path.home() / "tessdata")   # where ara.traineddata lives
OCR_DPI       = 150
NUM_WORKERS   = 12

# ── Logging ───────────────────────────────────────────────────────────────────
(BASE_DIR / "data" / "logs").mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ── Arabic ordinals → integer ─────────────────────────────────────────────────
ORDINALS = {
    "premier": 1,  "première": 1,  "الأول": 1,  "الأولى": 1,  "أول": 1,
    "deuxième": 2, "second": 2,    "الثاني": 2, "الثانية": 2,
    "troisième": 3,                "الثالث": 3, "الثالثة": 3,
    "quatrième": 4,                "الرابع": 4, "الرابعة": 4,
    "cinquième": 5,                "الخامس": 5, "الخامسة": 5,
    "sixième": 6,                  "السادس": 6, "السادسة": 6,
    "septième": 7,                 "السابع": 7, "السابعة": 7,
    "huitième": 8,                 "الثامن": 8, "الثامنة": 8,
    "neuvième": 9,                 "التاسع": 9, "التاسعة": 9,
    "dixième": 10,                 "العاشر": 10,"العاشرة": 10,
}


def extract_article_num(provision_ref: str) -> int | None:
    """
    Extract the integer article number from a provision_ref string.
    Handles: 'Article 9', 'Art. 9', 'Art.9', 'Article premier', 'Preamble'
    Returns None when no number can be determined.
    """
    if not provision_ref:
        return None
    ref = provision_ref.strip()

    # 1. Try explicit digit first  (covers 'Article 9', 'Art. 9', 'Art.9', '9')
    m = re.search(r'\b(\d+)\b', ref)
    if m:
        return int(m.group(1))

    # 2. Try ordinal words (covers 'Article premier', 'الأول' etc.)
    ref_lower = ref.lower()
    for word, num in ORDINALS.items():
        if word.lower() in ref_lower:
            return num

    return None


def arabic_indic_to_western(text: str) -> str:
    """Convert Arabic-Indic numerals (٠١٢…) to Western (012…)."""
    table = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    return text.translate(table)


# ── Regex patterns for article detection (applied AFTER numeral conversion) ───
# Primary: keyword at START OF LINE + number.
# Requiring line-start eliminates cross-reference mentions like "يعدل المادة 32"
# in the middle of a sentence, while still matching article headers like:
#   "المادة 9\n..."   or   "الفصل 9 ـ ..."
_KW = r"(?:ال)?(?:مادة|فصل|بند)"
PATTERN_KEYWORD = re.compile(
    rf"(?:^|\n)\s*{_KW}\s*:?\s*(\d+)",
    re.UNICODE | re.MULTILINE,
)
# Secondary: standalone number at start of line followed by dash / colon / ـ
PATTERN_STANDALONE = re.compile(
    r"^(\d+)\s*[ـ\-–—:.]",
    re.MULTILINE,
)


def numbers_on_page(ocr_text: str) -> set[int]:
    """
    Return the set of article numbers detected on a page's OCR text.

    Two-tier strategy:
      1. Keyword matches (المادة / الفصل + number) — high confidence.
         These are always accepted.
      2. Standalone line-start number (e.g. "9 ـ") — low confidence,
         only accepted for numbers 1-30 to avoid cross-reference noise.
         (Large article numbers like 444 appearing on early pages are
         almost certainly cross-references, not headers.)
    """
    text = arabic_indic_to_western(ocr_text)
    found = set()

    for m in PATTERN_KEYWORD.finditer(text):
        found.add(int(m.group(1)))

    # Standalone fallback only for small article numbers (≤ 30)
    if not found:
        for m in PATTERN_STANDALONE.finditer(text):
            n = int(m.group(1))
            if 1 <= n <= 30:
                found.add(n)

    return found


# ── Worker function (runs in a subprocess) ────────────────────────────────────
def ocr_page_worker(args: tuple) -> tuple[int, str]:
    """
    Render one PDF page and return (page_num_0indexed, ocr_text).
    Tries native text first; falls back to Tesseract Arabic OCR.
    """
    pdf_path, page_num = args
    try:
        doc  = fitz.open(pdf_path)
        page = doc.load_page(page_num)

        # Try native text layer (instant, perfect quality)
        native = page.get_text("text").strip()
        ar_chars = sum(1 for c in native if "؀" <= c <= "ۿ")
        if ar_chars > 30:
            doc.close()
            return (page_num, native)

        # Render to image for Tesseract
        zoom = OCR_DPI / 72
        pix  = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        img  = Image.open(io.BytesIO(pix.tobytes("png")))
        doc.close()

        os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        text = pytesseract.image_to_string(
            img, lang="ara",
            config="--oem 3 --psm 3",
        )
        return (page_num, text)

    except Exception as e:
        return (page_num, "")


# ── Per-PDF processing ────────────────────────────────────────────────────────
def build_page_map(pdf_path: str, article_nums: set[int]) -> dict[int, int]:
    """
    Scan the PDF and return {article_num: page_number_1indexed}.
    Pages are processed in parallel; results are sorted and scanned
    sequentially to preserve article ordering.
    """
    try:
        doc = fitz.open(pdf_path)
        total_pages = doc.page_count
        doc.close()
    except Exception as e:
        log.warning(f"Cannot open {pdf_path}: {e}")
        return {}

    # Submit all pages in parallel
    tasks = [(pdf_path, pn) for pn in range(total_pages)]
    page_texts: list[tuple[int, str]] = [None] * total_pages

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as ex:
        futures = {ex.submit(ocr_page_worker, t): t[1] for t in tasks}
        for fut in as_completed(futures):
            pn, text = fut.result()
            page_texts[pn] = (pn, text)

    # Walk pages in order and record the FIRST page each article number
    # appears on.  No monotonicity filter — bulletins contain multiple laws
    # that each restart from Article 1, so sequential ordering cannot be
    # assumed across the whole PDF.
    page_map: dict[int, int] = {}
    remaining = set(article_nums)

    for pn, text in page_texts:
        if not remaining:
            break
        if not text:
            continue
        nums_here = numbers_on_page(text)
        for n in nums_here & remaining:
            page_map[n] = pn + 1   # 1-indexed
            remaining.discard(n)

    return page_map


# ── DB helpers ────────────────────────────────────────────────────────────────
def get_stubs_for_bulletin(conn: sqlite3.Connection, bulletin: str, year: str):
    """
    Return list of (provision_id, provision_ref, metadata_dict) for every
    Arabic stub provision belonging to this bulletin.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT id, provision_ref, metadata
        FROM legal_provisions
        WHERE json_extract(metadata, '$.bulletin') = ?
          AND json_extract(metadata, '$.year')     = ?
          AND json_extract(metadata, '$.language') = 'AR'
    """, (bulletin, year))
    rows = []
    for row_id, ref, meta_str in cur.fetchall():
        meta = json.loads(meta_str) if meta_str else {}
        rows.append((row_id, ref, meta))
    return rows


def update_stubs(conn: sqlite3.Connection,
                 stubs: list,
                 page_map: dict[int, int]) -> int:
    """
    Update the `pages` field in metadata for every stub whose article
    number was found. Returns count of updated rows.
    """
    cur = conn.cursor()
    updated = 0
    for row_id, ref, meta in stubs:
        art_num = extract_article_num(ref)
        if art_num is None:
            continue
        if art_num in page_map:
            meta["pages"]       = str(page_map[art_num])
            meta["pages_exact"] = True
        else:
            meta["pages"]       = meta.get("pages", "1")
            meta["pages_exact"] = False
        cur.execute(
            "UPDATE legal_provisions SET metadata = ? WHERE id = ?",
            (json.dumps(meta, ensure_ascii=False), row_id),
        )
        updated += 1
    conn.commit()
    return updated


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Re-process bulletins that already have a cache file")
    parser.add_argument("--test", action="store_true",
                        help="Process only the first 5 Arabic PDFs")
    args = parser.parse_args()

    # Collect all Arabic PDFs
    pdf_entries: list[tuple[str, str, str]] = []   # (year, bulletin_stem, pdf_path)
    for yr_dir in sorted(AR_PDF_DIR.iterdir()):
        if not yr_dir.is_dir():
            continue
        year = yr_dir.name
        for pdf_file in sorted(yr_dir.glob("*_Ar.pdf")):
            bulletin = pdf_file.stem          # e.g. BO_4758_Ar
            pdf_entries.append((year, bulletin, str(pdf_file)))

    if args.test:
        pdf_entries = pdf_entries[:5]

    total = len(pdf_entries)
    log.info(f"Found {total} Arabic PDFs to process.")

    conn = sqlite3.connect(str(DB_PATH))
    t0 = time.time()

    pdfs_done    = 0
    pdfs_skipped = 0
    total_updated = 0

    for idx, (year, bulletin, pdf_path) in enumerate(pdf_entries, 1):
        cache_file = CACHE_DIR / f"{year}__{bulletin}.json"

        # ── Resume: skip if already cached ──────────────────────────────────
        if cache_file.exists() and not args.force:
            # Still apply cache to DB in case a previous run was interrupted
            # before the DB update
            try:
                page_map = {int(k): v for k, v in
                            json.loads(cache_file.read_text("utf-8")).items()}
                stubs = get_stubs_for_bulletin(conn, bulletin, year)
                if stubs:
                    update_stubs(conn, stubs, page_map)
            except Exception:
                pass
            pdfs_skipped += 1
            continue

        # ── Get article numbers we need to find for this bulletin ────────────
        stubs = get_stubs_for_bulletin(conn, bulletin, year)
        if not stubs:
            pdfs_skipped += 1
            continue

        article_nums = set()
        for _, ref, _ in stubs:
            n = extract_article_num(ref)
            if n is not None:
                article_nums.add(n)

        if not article_nums:
            pdfs_skipped += 1
            continue

        elapsed = time.time() - t0
        rate    = pdfs_done / (elapsed / 60) if elapsed > 0 else 0
        eta     = ((total - idx) / rate) if rate > 0 else 0
        log.info(
            f"[{idx}/{total}] {year}/{bulletin}  "
            f"articles={len(article_nums)}  "
            f"done={pdfs_done}  rate={rate:.1f}/min  ETA={eta:.0f}min"
        )

        # ── Scan the PDF ─────────────────────────────────────────────────────
        try:
            page_map = build_page_map(pdf_path, article_nums)
        except Exception as e:
            log.warning(f"  Failed to scan {pdf_path}: {e}")
            page_map = {}

        found    = len(page_map)
        missing  = len(article_nums) - found
        log.info(f"  Found: {found}/{len(article_nums)} articles  "
                 f"(missing: {missing})")

        # ── Cache result ─────────────────────────────────────────────────────
        cache_file.write_text(
            json.dumps({str(k): v for k, v in page_map.items()},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # ── Update DB ────────────────────────────────────────────────────────
        n_updated = update_stubs(conn, stubs, page_map)
        total_updated += n_updated

        pdfs_done += 1

    conn.close()

    elapsed = time.time() - t0
    log.info("=" * 60)
    log.info("Arabic page finder complete.")
    log.info(f"  PDFs processed  : {pdfs_done}")
    log.info(f"  PDFs skipped    : {pdfs_skipped} (cached or no stubs)")
    log.info(f"  DB rows updated : {total_updated}")
    log.info(f"  Total time      : {elapsed/60:.1f} min")
    log.info(f"  Cache location  : {CACHE_DIR}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
