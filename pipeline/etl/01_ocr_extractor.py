"""
01_ocr_extractor.py
====================
High-speed, parallel OCR-only text extraction script.
Extracts raw text from ALL PDFs using page-level parallel processing.

Pipeline strategy:
  1. Process PDFs sequentially one-by-one.
  2. For the current PDF, process its pages in parallel across all CPU cores.
  3. PyMuPDF native text extraction (instant for digital PDFs)
  4. Gibberish/Corrupt CMAP detection (forces OCR for PDFs with bad unicode mappings)
  5. Tesseract OCR fallback (for scanned/image PDFs from 2000-2022)

Output: raw_text/{year}/{pdfname}/page{N}.txt for every page.

NO Jina API calls. NO ChromaDB writes. Pure CPU-parallel extraction.

Usage:
    # Extract ALL years (2000-2026) — skips pages already extracted
    python pipeline/etl/01_ocr_extractor.py

    # Force re-extract everything (overwrite existing files)
    python pipeline/etl/01_ocr_extractor.py --force

    # Quick test: only process 3 PDFs
    python pipeline/etl/01_ocr_extractor.py --test-only
"""

import os
import re
import sys
import time
import logging
import argparse
import threading
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import Manager, cpu_count

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io

# ─── Config ────────────────────────────────────────────────────────────────
INPUT_DIR        = "data/raw_pdfs_fr"
OUTPUT_DIR       = "data/raw_text"
LOG_FILE         = "data/logs/01_ocr_extractor.log"
TESSERACT_CMD    = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR     = os.path.expanduser(r"~\tessdata")
OCR_DPI          = 150          # Higher DPI for accurate OCR character matching
SKIP_MIN_CHARS   = 50           # Skip pages already extracted with >50 chars
NUM_WORKERS      = 14           # Parallel workers (keep 2 cores free for OS responsive)

# ─── Logging (Only write to file to avoid messing up the console dashboard) ───
os.makedirs("data/logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


def is_gibberish(text: str, lang: str) -> bool:
    """
    Detects if the extracted native text is corrupted CMAP gibberish or a hybrid page (header-only).
    """
    if not text or len(text.strip()) < 15:
        return False
        
    # Check for Latin Extended-B / IPA Extensions (corrupted CMAP markers)
    if re.search(r'[\u0180-\u02AF]', text):
        return True
        
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    total_words = len(words)
    
    if total_words == 0:
        return True

    # 1. Header-Only check (detects hybrid pages where only header was digital)
    header_footer_words = {
        'bulletin', 'officiel', 'page', 'n°', 'n', 'edition', 'traduction', 'officielle',
        'janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
        'moharrem', 'safar', 'rabii', 'joumada', 'rajab', 'chaabane', 'ramadan', 'chaoual', 'kaada', 'hija', 'doul',
        'el', 'ouvert', 'tarifs', 'abonnement', 'imprimerie', 'annonces', 'légales', 'judiciaires', 'administratives'
    }
    body_words = [w for w in words if not w.isdigit() and w not in header_footer_words]
    if len(body_words) < 5:
        return True

    # 2. Vocabulary match check (detects gibberish/corrupt text maps)
    if lang == "fr":
        common_words = {
            'de', 'la', 'le', 'et', 'les', 'en', 'des', 'du', 'un', 'une', 'pour', 'dans', 
            'par', 'sur', 'au', 'aux', 'loi', 'article', 'bulletin', 'officiel', 'est', 'sont'
        }
    else:
        common_words = {
            'من', 'في', 'على', 'إلى', 'الجريدة', 'الرسمية', 'ظهير', 'قانون', 'مرسوم', 'المادة', 'رقم'
        }
        
    match_count = sum(1 for w in words if w in common_words)
    vocab_ratio = match_count / total_words
    
    # If the text is significant but has extremely low stopword frequency, it is gibberish
    if total_words > 15 and vocab_ratio < 0.08:
        return True
        
    return False


def polish_legal_text(text: str) -> str:
    """Clean up OCR artifacts and formatting noise from the extracted text."""
    # 1. Remove soft hyphens (word-break artifacts)
    text = text.replace('\xad\n', '').replace('\xad', '')
    # 2. Replace dot leaders (table of contents dots) with arrows
    text = re.sub(r'\.{2,}', ' -> ', text)
    # 3. Collapse runs of 3+ blank lines to a single blank line
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_page_text(pdf_path: str, page_num: int, lang: str, status_dict=None, pid=None) -> str:
    """
    Extract text from a single PDF page.
    - Tries PyMuPDF native text layer first (instant, zero CPU cost).
    - Falls back to Tesseract OCR if the page is a scanned image or has corrupted CMAP.
    Returns the polished text string.
    """
    doc  = fitz.open(pdf_path)
    page = doc.load_page(page_num)
    text = page.get_text("text")
    doc.close()

    is_empty = not text.strip()
    is_gib = is_gibberish(text, lang)

    # Fall back to Tesseract OCR if page is empty or font mapping is corrupted
    if is_empty or is_gib:
        if status_dict is not None and pid is not None:
            mode_desc = "OCR (Scanned)" if is_empty else "OCR (Corrupt CMAP)"
            try:
                status_dict[pid] = {
                    **status_dict[pid],
                    "mode": mode_desc
                }
            except Exception:
                pass

        if os.path.exists(TESSERACT_CMD):
            try:
                os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR
                pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

                doc2 = fitz.open(pdf_path)
                page2 = doc2.load_page(page_num)
                zoom  = OCR_DPI / 72
                pix   = page2.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                img   = Image.open(io.BytesIO(pix.tobytes("png")))
                doc2.close()

                ocr_lang = "fra" if lang == "fr" else "eng"
                text = pytesseract.image_to_string(img, lang=ocr_lang)
            except Exception as e:
                text = f"[OCR FAILED: {e}]"
        else:
            text = "[TESSERACT OCR NOT FOUND]"
    else:
        if status_dict is not None and pid is not None:
            try:
                status_dict[pid] = {
                    **status_dict[pid],
                    "mode": "Native (Digital)"
                }
            except Exception:
                pass

    return polish_legal_text(text)


def process_page(args: tuple) -> dict:
    """
    Worker function executed in parallel by each CPU core.
    Processes a single page of a PDF: checks for gibberish skip, extracts, saves.
    Returns status.
    """
    pdf_path_str, page_num, lang, force, out_file_str, status_dict = args
    pid = os.getpid()
    out_file = Path(out_file_str)

    # Skip logic: read and verify text is not gibberish
    if not force and out_file.exists() and out_file.stat().st_size >= SKIP_MIN_CHARS:
        try:
            existing_text = out_file.read_text(encoding="utf-8")
            if not is_gibberish(existing_text, lang):
                try:
                    status_dict[pid] = {
                        "page": page_num + 1,
                        "mode": "Skipped",
                        "status": "Idle"
                    }
                except Exception:
                    pass
                return {"status": "skipped", "page": page_num + 1}
        except Exception:
            pass

    # Set process status to Running for this page (only show pages actively doing work)
    try:
        status_dict[pid] = {
            "page": page_num + 1,
            "mode": "Detecting...",
            "status": "Running"
        }
    except Exception:
        pass

    try:
        text = extract_page_text(pdf_path_str, page_num, lang, status_dict, pid)
        out_file.write_text(text, encoding="utf-8")
        result_status = "extracted"
    except Exception as e:
        result_status = "failed"

    # Reset status to Idle when page is done
    try:
        status_dict[pid] = {
            "page": page_num + 1,
            "mode": "Done",
            "status": "Idle"
        }
    except Exception:
        pass

    return {"status": result_status, "page": page_num + 1}


def dashboard_loop(status_dict, all_pdfs_count, start_time, stop_event, completed_ref, stats_ref, current_pdf_ref):
    """Refreshes the console dashboard screen with live worker and overall statistics."""
    while not stop_event.is_set():
        time.sleep(0.5)

        active_workers = 0
        ocr_count = 0
        native_count = 0
        worker_lines = []

        # Read statuses of processes
        for pid, info in list(status_dict.items()):
            if info.get("status") == "Running":
                active_workers += 1
                mode = info.get("mode", "")
                if "OCR" in mode:
                    ocr_count += 1
                elif "Native" in mode:
                    native_count += 1

                page = info.get("page", 0)
                worker_lines.append(f"  Worker PID {pid:<5d} | Page {page:>3d} | {mode}")

        elapsed = time.time() - start_time
        completed = completed_ref[0]
        pct = (completed / all_pdfs_count) * 100 if all_pdfs_count > 0 else 0

        total_extracted = stats_ref["extracted"]
        total_skipped   = stats_ref["skipped"]
        total_failed    = stats_ref["failed"]

        speed = (total_extracted + total_skipped) / (elapsed / 60) if elapsed > 0 else 0

        current_pdf_name = current_pdf_ref.get("name", "None")
        current_pdf_year = current_pdf_ref.get("year", "None")
        current_pdf_pages = current_pdf_ref.get("total_pages", 0)

        dashboard_text = []
        dashboard_text.append("=" * 80)
        dashboard_text.append("   MOROCCAN LAW AI — HIGH-SPEED PARALLEL OCR EXTRACTOR DASHBOARD")
        dashboard_text.append("=" * 80)
        dashboard_text.append(f"  Overall Progress : {completed}/{all_pdfs_count} PDFs completed ({pct:.1f}%)")
        dashboard_text.append(f"  Pages Processed  : {total_extracted + total_skipped:<6d} (Extracted: {total_extracted} | Skipped: {total_skipped} | Failed: {total_failed})")
        dashboard_text.append(f"  Average Speed    : {speed:.1f} pages/minute")
        dashboard_text.append(f"  Time Elapsed     : {elapsed/60:.1f} minutes")
        dashboard_text.append("-" * 80)
        dashboard_text.append(f"  Current PDF      : {current_pdf_name} (Year: {current_pdf_year})")
        dashboard_text.append(f"  PDF Pages        : {current_pdf_pages} pages total")
        dashboard_text.append(f"  Active Workers   : {active_workers:<2d} processes  (OCR: {ocr_count:<2d} | PyMuPDF: {native_count:<2d})")
        dashboard_text.append("-" * 80)
        dashboard_text.append("  Active Worker Details (Page level):")
        if worker_lines:
            dashboard_text.extend(sorted(worker_lines))
        else:
            dashboard_text.append("  No active workers (skipping or starting up...)")
        dashboard_text.append("=" * 80)

        # Clear screen cleanly on Windows and Unix without relying on ANSI characters
        os.system('cls' if os.name == 'nt' else 'clear')
        sys.stdout.write("\n".join(dashboard_text) + "\n")
        sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="High-speed parallel OCR extractor")
    parser.add_argument("--force",     action="store_true", help="Re-extract all pages even if .txt already exists")
    parser.add_argument("--test-only", action="store_true", help="Quick test: process only the first 3 PDFs (5 pages each)")
    args = parser.parse_args()

    # Collect all PDFs from all years in raw_pdfs_fr
    all_pdfs = sorted(Path(INPUT_DIR).rglob("*.pdf"))
    if not all_pdfs:
        print(f"Error: No PDFs found in: {INPUT_DIR}")
        sys.exit(1)

    if args.test_only:
        all_pdfs = all_pdfs[:3]

    # Initialize shared memory for workers and main thread tracking
    manager = Manager()
    status_dict = manager.dict()
    completed_ref = [0]
    stats_ref = manager.dict({"extracted": 0, "skipped": 0, "failed": 0})
    current_pdf_ref = manager.dict({"name": "", "year": "", "total_pages": 0})

    # Log initial status to data/ocr_extractor.log
    log.info("=" * 65)
    log.info("Moroccan Law AI — Sequential PDF Page-Parallel Extractor Initiated")
    log.info(f"  CPU Workers  : {NUM_WORKERS}")
    log.info(f"  Input Dir    : {os.path.abspath(INPUT_DIR)}")
    log.info(f"  Output Dir   : {os.path.abspath(OUTPUT_DIR)}")
    log.info(f"  Mode         : {'TEST (3 PDFs)' if args.test_only else 'FULL (ALL PDFs)'}")
    log.info(f"  Files Count  : {len(all_pdfs)}")
    log.info("=" * 65)

    start_time = time.time()
    stop_event = threading.Event()

    # Launch console dashboard background thread
    dashboard_thread = threading.Thread(
        target=dashboard_loop,
        args=(status_dict, len(all_pdfs), start_time, stop_event, completed_ref, stats_ref, current_pdf_ref)
    )
    dashboard_thread.daemon = True
    dashboard_thread.start()

    try:
        # Create a single ProcessPoolExecutor for the entire lifetime to avoid restart overhead
        with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
            for pdf_idx, pdf_path in enumerate(all_pdfs):
                filename = pdf_path.name
                year = pdf_path.parent.name
                pdf_name = pdf_path.stem
                lang = "ar" if "_Ar.pdf" in filename else "fr"

                pdf_text_dir = Path(OUTPUT_DIR) / year / pdf_name
                pdf_text_dir.mkdir(parents=True, exist_ok=True)

                try:
                    doc = fitz.open(str(pdf_path))
                    total_pages = len(doc)
                    doc.close()
                except Exception as e:
                    log.error(f"Error opening {pdf_path}: {e}")
                    stats_ref["failed"] += 1
                    completed_ref[0] = pdf_idx + 1
                    continue

                pages_to_run = min(total_pages, 5) if args.test_only else total_pages

                # Update current PDF details for the dashboard
                current_pdf_ref["name"] = filename
                current_pdf_ref["year"] = year
                current_pdf_ref["total_pages"] = pages_to_run

                # Submit all pages of this PDF to the process pool
                page_tasks = []
                for p_num in range(pages_to_run):
                    out_file_str = str(pdf_text_dir / f"page{p_num + 1}.txt")
                    page_tasks.append((str(pdf_path), p_num, lang, args.force, out_file_str, status_dict))

                futures = {executor.submit(process_page, task): task[1] for task in page_tasks}

                pdf_extracted = 0
                pdf_skipped   = 0
                pdf_failed    = 0

                # Wait for all pages of the current PDF to finish
                for future in as_completed(futures):
                    res = future.result()
                    status = res["status"]
                    if status == "extracted":
                        pdf_extracted += 1
                    elif status == "skipped":
                        pdf_skipped += 1
                    else:
                        pdf_failed += 1

                    # Update running global stats
                    stats_ref["extracted"] += 1 if status == "extracted" else 0
                    stats_ref["skipped"]   += 1 if status == "skipped" else 0
                    stats_ref["failed"]    += 1 if status == "failed" else 0

                # Log PDF completion
                log.info(
                    f"[{((pdf_idx + 1)/len(all_pdfs))*100:5.1f}%] {filename} | "
                    f"extracted={pdf_extracted} | skipped={pdf_skipped} | failed={pdf_failed}"
                )

                completed_ref[0] = pdf_idx + 1

    except KeyboardInterrupt:
        print("\n\nExecution interrupted by user. Stopping dashboard...")
    finally:
        # Gracefully stop the dashboard background thread
        stop_event.set()
        dashboard_thread.join()

    # Final summary display on terminal
    elapsed = time.time() - start_time
    total_processed = stats_ref["extracted"] + stats_ref["skipped"]
    
    print("\n" + "=" * 65)
    print("OCR EXTRACTION PROCESS COMPLETE!")
    print(f"  PDFs Processed   : {completed_ref[0]}")
    print(f"  Pages Extracted  : {stats_ref['extracted']}")
    print(f"  Pages Skipped    : {stats_ref['skipped']} (already extracted)")
    print(f"  Pages Failed     : {stats_ref['failed']}")
    print(f"  Total Time       : {elapsed:.0f} seconds ({elapsed/60:.1f} minutes)")
    print(f"  Average Speed    : {total_processed / (elapsed / 60) if elapsed > 0 else 0:.1f} pages/minute")
    print(f"  Output Location  : {os.path.abspath(OUTPUT_DIR)}")
    print(f"  Log File         : {os.path.abspath(LOG_FILE)}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
