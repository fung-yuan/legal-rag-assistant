"""
07_vector_indexer.py
====================
Renders each PDF page as an image, generates visual embeddings 
using Jina Embeddings v4 API in parallel with key rotation,
indexes vectors in ChromaDB, and writes polished raw text to the local disk.

Usage:
    # Build complete visual database using parallel key rotation
    python pipeline/etl/07_vector_indexer.py

    # Test only first 5 pages of a single PDF
    python pipeline/etl/07_vector_indexer.py --test-only
"""

import os
import sys
import json
import base64
import time
import argparse
import logging
import queue
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import fitz  # PyMuPDF
import chromadb
import pytesseract
from PIL import Image
import io

# Tesseract OCR executable path on Windows
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR = os.getenv("TESSDATA_PREFIX", os.path.expanduser(r"~\tessdata")) # Support default or env
if os.path.exists(TESSERACT_CMD):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# Config Paths
INPUT_DIR = "data/raw_pdfs_fr"
CHROMA_DIR = "data/chroma_db"
COLLECTION_NAME = "bo_maroc_jina_v4"
LOG_FILE = "data/logs/07_vector_indexer.log"
BATCH_SIZE = 2  # Keep batch size small to prevent rate-limit bursts

# Active Jina API Keys Pool for rotation and parallel speed
DEFAULT_API_KEYS = [
    "jina_68137d45664545a981a94855a11db3c3JUfKpia1k-y8SyZjsF6xz7TCVMP3",
    "jina_f23f1b37ae36457caecbc18d20982652WL9FVyIrr6SQPalxXyLSANYwIvq_"
]

# Set up clean logging
os.makedirs("data/logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

def get_jina_keys() -> list[str]:
    """Retrieve Jina API Keys from environment variable or fallback to defaults."""
    env_keys_str = os.getenv("JINA_API_KEYS", "")
    if env_keys_str:
        keys = [k.strip() for k in env_keys_str.split(",") if k.strip()]
        log.info(f"Loaded {len(keys)} API keys from environment variable JINA_API_KEYS.")
        return keys
    
    # Fallback to JINA_API_KEY if single key is provided
    single_env_key = os.getenv("JINA_API_KEY", "")
    if single_env_key:
        log.info("Loaded 1 API key from environment variable JINA_API_KEY.")
        return [single_env_key]
        
    log.info(f"Using default pool of {len(DEFAULT_API_KEYS)} API keys provided by user.")
    return DEFAULT_API_KEYS

def get_page_image_base64(page: fitz.Page, dpi: int = 72) -> str:
    """Render a PDF page to a crisp PNG image at 72 DPI to optimize speed and token limits."""
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix)
    img_bytes = pix.tobytes("png")
    return base64.b64encode(img_bytes).decode("utf-8")

def polish_legal_text(text: str) -> str:
    """Clean up formatting artifacts, soft hyphens, and repeated dot patterns."""
    import re
    # 1. Join split words that have soft-hyphens at the end of lines
    text = text.replace('\xad\n', '')
    text = text.replace('\xad', '')  # Clean up any remaining soft hyphens
    
    # 2. Clean up excessive dot leaders (e.g., "......... 4" -> " -> 4")
    text = re.sub(r'\.{2,}', ' -> ', text)
    
    # 3. Standardize multiple empty lines (limit to max 1 blank line between sections)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

def get_jina_embeddings(base64_images: list[str], api_key: str) -> list[list[float]]:
    """Send base64 images to Jina Embeddings v4 API and retrieve vectors with robust Session retries and exponential backoff."""
    url = "https://api.jina.ai/v1/embeddings"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": "jina-embeddings-v4",
        "dimensions": 512,  # Compact, high-speed 512 dimensions via Matryoshka
        "normalized": True,
        "embedding_type": "float",
        "input": [{"image": img} for img in base64_images]
    }
    
    # Run with robust retries, fresh requests Session, exponential backoff, and higher timeout (120s)
    for attempt in range(6):
        try:
            with requests.Session() as session:
                response = session.post(url, json=payload, headers=headers, timeout=120)
                if response.status_code == 429:
                    wait_time = 20 + attempt * 10
                    log.warning(f"Rate limit (429) hit! Sleeping {wait_time} seconds to clear token window...")
                    time.sleep(wait_time)
                    continue
                response.raise_for_status()
                res_json = response.json()
                return [item["embedding"] for item in res_json["data"]]
        except Exception as e:
            wait_time = (2 ** attempt) * 5 + 5
            log.warning(f"Jina API attempt {attempt+1} failed: {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)
            
    log.error("Jina API failed completely after all retries.")
    return []

def process_single_pdf(pdf_path: Path, key_pool: queue.Queue, chroma_dir: str, test_only: bool = False) -> int:
    """Thread-safe processor that indexes a single PDF page-by-page, dynamically renting Jina API keys."""
    # Instantiate thread-local ChromaDB client and collection
    chroma_client = chromadb.PersistentClient(path=chroma_dir)
    collection = chroma_client.get_collection(COLLECTION_NAME)
    
    filename = pdf_path.name
    year = pdf_path.parent.name
    lang = "ar" if "_Ar.pdf" in filename else "fr"
    bo_number = filename.replace("_Ar.pdf", "").replace("_Fr.pdf", "").replace("BO_", "")
    
    doc = fitz.open(str(pdf_path))
    pages_to_process = min(len(doc), 5) if test_only else len(doc)
    
    log.info(f"Thread started for {filename} ({pages_to_process} pages to process)")
    
    batch_images = []
    batch_metadata = []
    batch_texts = []
    batch_ids = []
    
    indexed_count = 0
    
    for page_num in range(pages_to_process):
        page = doc.load_page(page_num)
        
        # 1. Render layout to image at 72 DPI (highly optimized for speed and token savings)
        b64_img = get_page_image_base64(page, dpi=72)
        
        # 2. Extract raw text
        raw_text_extracted = page.get_text("text")
        
        # Fallback to Tesseract OCR if PDF page contains no selectable text (scanned PDF)
        if not raw_text_extracted.strip():
            if os.path.exists(TESSERACT_CMD):
                try:
                    # Render page at 150 DPI for clean OCR character matching
                    zoom = 150 / 72
                    matrix = fitz.Matrix(zoom, zoom)
                    pix = page.get_pixmap(matrix=matrix)
                    img_bytes = pix.tobytes("png")
                    
                    img = Image.open(io.BytesIO(img_bytes))
                    ocr_lang = "fra" if lang == "fr" else "eng"
                    # Set TESSDATA_PREFIX so Tesseract finds the user-installed fra.traineddata
                    os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR
                    raw_text_extracted = pytesseract.image_to_string(img, lang=ocr_lang)
                    log.info(f"  [OCR Fallback] Read scanned page {page_num + 1} of {filename} ({len(raw_text_extracted)} chars)")
                except Exception as ocr_err:
                    log.warning(f"  OCR failed on page {page_num + 1} of {filename}: {ocr_err}")
            else:
                log.warning(f"  Scanned page detected on {filename} page {page_num + 1}, but Tesseract engine not found at: {TESSERACT_CMD}")
                
        raw_text = polish_legal_text(raw_text_extracted)
        
        # 3. Write physical text file inside raw_text/{year}/{pdfname}/page{page_number}.txt (no underscore)
        pdf_name = pdf_path.stem
        pdf_text_dir = Path("data/raw_text") / year / pdf_name
        pdf_text_dir.mkdir(parents=True, exist_ok=True)
        file_output_path = pdf_text_dir / f"page{page_num + 1}.txt"
        with open(file_output_path, "w", encoding="utf-8") as f:
            f.write(raw_text)
            
        # Unique ID for this page chunk
        chunk_id = f"bo_{bo_number}_{lang}_page_{page_num + 1}"
        
        batch_images.append(b64_img)
        batch_texts.append(raw_text)
        batch_ids.append(chunk_id)
        batch_metadata.append({
            "bo_number": str(bo_number),
            "year": str(year),
            "language": str(lang),
            "page_number": str(page_num + 1),
            "total_pages": str(len(doc)),
            "source_pdf": str(filename),
            "text_snippet": raw_text[:300]
        })
        
        # If batch size met, execute API call & save to Chroma
        if len(batch_images) == BATCH_SIZE or (page_num == pages_to_process - 1):
            # Rent Jina Key from the thread-safe resource pool queue
            api_key = key_pool.get()
            try:
                vectors = get_jina_embeddings(batch_images, api_key)
                if vectors:
                    collection.add(
                        ids=batch_ids,
                        embeddings=vectors,
                        documents=batch_texts,
                        metadatas=batch_metadata
                    )
                    indexed_count += len(batch_images)
                else:
                    log.error(f"❌ Failed to get embeddings for {filename} page {page_num + 1}")
            finally:
                # Always return key back to resource pool
                key_pool.put(api_key)
                
            # Reset batch containers
            batch_images = []
            batch_metadata = []
            batch_texts = []
            batch_ids = []
            
    doc.close()
    log.info(f"Finished processing {filename}: Successfully indexed {indexed_count} pages.")
    return indexed_count

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-only", action="store_true", help="Run a quick test on 1 PDF (first 5 pages)")
    args = parser.parse_args()

    api_keys = get_jina_keys()

    log.info("=" * 60)
    log.info("Moroccan Law AI -- Parallel Visual Indexer (Jina v4)")
    log.info("=" * 60)

    # 1. Collect only PDF files from the legacy OCR catalog (years 2000 to 2022)
    all_pdfs = [
        p for p in sorted(Path(INPUT_DIR).rglob("*.pdf"))
        if p.parent.name in [str(y) for y in range(2000, 2023)]
    ]
    if not all_pdfs:
        log.error(f"No PDFs found in the root directory: {INPUT_DIR}")
        sys.exit(1)

    log.info(f"Found {len(all_pdfs)} raw PDFs to index.")

    if args.test_only:
        # Select a representative PDF for a fast test run
        test_pdf = all_pdfs[0]
        pdf_files = [test_pdf]
        log.info(f"[Test Mode] Operating ONLY on a single PDF: {test_pdf.name}")
    else:
        pdf_files = all_pdfs

    # 2. Setup Persistent ChromaDB Client in the main thread to prepare collection
    log.info(f"Connecting to ChromaDB at: {os.path.abspath(CHROMA_DIR)}")
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    
    # Get or create the collection -- NEVER wipe so existing 2023-2026 vectors are preserved
    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    log.info(f"Connected to collection '{COLLECTION_NAME}' (current count: {collection.count()})")

    # 3. Create key pool queue to manage dynamic key allocation
    key_pool = queue.Queue()
    for key in api_keys:
        key_pool.put(key)

    # 4. Thread pool execution of independent PDF files
    total_indexed = 0
    start_time = time.time()
    num_threads = min(len(api_keys), len(pdf_files))

    log.info(f"Spawning {num_threads} threads for concurrent Jina indexing...")
    
    with ThreadPoolExecutor(max_workers=num_threads, thread_name_prefix="Indexer") as executor:
        futures = {
            executor.submit(process_single_pdf, pdf_path, key_pool, CHROMA_DIR, args.test_only): pdf_path
            for pdf_path in pdf_files
        }
        
        for future in as_completed(futures):
            pdf_path = futures[future]
            try:
                indexed_count = future.result()
                total_indexed += indexed_count
            except Exception as e:
                log.error(f"Error processing PDF {pdf_path.name}: {e}")

    elapsed = time.time() - start_time
    log.info(f"\n{'='*55}")
    log.info("Visual Indexing Complete!")
    log.info(f"  Total Pages Indexed : {total_indexed}")
    log.info(f"  Time Elapsed        : {elapsed:.1f} seconds")
    log.info(f"  Average Speed       : {total_indexed / (elapsed / 60):.2f} pages / minute")
    log.info(f"  DB Location         : {os.path.abspath(CHROMA_DIR)}")
    log.info(f"{'='*55}\n")

if __name__ == "__main__":
    main()
