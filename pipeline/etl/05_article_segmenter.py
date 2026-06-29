"""
05_article_segmenter.py
=======================
Groups classified pages by Document_ID, merges their text, and splits them
on article boundaries to produce an article-level dataset.
Resolves which page range each article spans based on inline page markers.
Outputs: data/moroccan_law_articles.csv and .xlsx
"""

import os
import re
import logging
import pickle
import pandas as pd
import numpy as np

INPUT_CSV = "data/etl_intermediate/moroccan_law_pages_classified.csv"
OUTPUT_CSV = "data/etl_intermediate/moroccan_law_articles.csv"
OUTPUT_XLSX = "data/etl_intermediate/moroccan_law_articles.xlsx"
LOG_FILE = "data/logs/05_article_segmenter.log"
MODEL_PATH = "pipeline/models/article_classifier.pkl"

os.makedirs("data/logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# Load trained classifier model
classifier_model = None
if os.path.exists(MODEL_PATH):
    try:
        with open(MODEL_PATH, "rb") as f:
            classifier_model = pickle.load(f)
        log.info(f"Loaded article boundary ML classifier from {MODEL_PATH}")
    except Exception as e:
        log.error(f"Failed to load ML classifier from {MODEL_PATH}: {e}")
else:
    log.warning(f"ML classifier not found at {MODEL_PATH}. Falling back to heuristic rules.")

def is_article_definition(match, text, language=None):
    # If French document and classifier is available, predict using the ML model
    if language == "FR" and classifier_model is not None:
        start_pos = max(0, match.start() - 50)
        end_pos = min(len(text), match.end() + 50)
        context = text[start_pos:end_pos].replace("\n", " ").strip()
        try:
            prediction = classifier_model.predict([context])[0]
            return bool(prediction == 1)
        except Exception as e:
            log.warning(f"Error predicting with ML model, falling back to heuristics: {e}")

    # Heuristic rules fallback
    start = match.start()
    end = match.end()
    
    # 1. Extract prefix (up to 30 chars before)
    prefix_raw = text[max(0, start-30):start]
    prefix = prefix_raw.lower().strip()
    
    # 2. Extract suffix (up to 30 chars after)
    suffix_raw = text[end:end+30]
    suffix = suffix_raw.lower().strip()
    
    match_text = match.group(0)
    
    # Standard cross-reference indicators in prefix
    ref_prefixes = [
        "l'", "d'", "les", "des", "aux", "de", "à", "dans", "sur", "sous", 
        "cet", "ce", "chaque", "un", "une", "par", "comme", "le", "la", "du", "au"
    ]
    
    # Check if prefix ends with any of the reference prefixes
    is_ref = False
    for p in ref_prefixes:
        if p.endswith("'"):
            if prefix.endswith(p):
                is_ref = True
                break
        else:
            if re.search(r'\b' + re.escape(p) + r'\s*$', prefix):
                is_ref = True
                break
                
    # Also check if matched text is lowercase "article" or "art" in the middle of a sentence
    # Definitions are typically capitalized: "Article", "Art."
    is_capitalized = match_text[0].isupper()
    
    # Cross-reference indicators in suffix
    ref_suffixes = ["ci-dessus", "ci-dessous", "précité", "précitée", "du présent", "de la présente", "et suivants"]
    for s in ref_suffixes:
        if s in suffix:
            is_ref = True
            break
            
    # Decision logic
    if is_ref:
        return False
    if not is_capitalized:
        return False
        
    return True

def main():
    log.info("Starting Legal Act Article Segmentation Pipeline...")
    
    if not os.path.exists(INPUT_CSV):
        log.error(f"Input file '{INPUT_CSV}' not found! Please run 04_legal_classifier.py first.")
        return
        
    log.info(f"Loading classified page dataset '{INPUT_CSV}'...")
    df = pd.read_csv(INPUT_CSV, encoding="utf-8")
    
    # Filter out Table of Contents / SOMMAIRE
    df_docs = df[df["Doc_Type"] != "SOMMAIRE"].copy()
    log.info(f"Filtered out SOMMAIRE pages. {len(df_docs)} legal content pages remaining.")
    
    # Group by Document_ID
    grouped = df_docs.groupby("Document_ID")
    
    articles_data = []
    
    # Regex pattern to match article boundaries
    article_pattern = re.compile(
        r'\b(article\s+premier|art\.\s*\d+|article\s*\d+)\b',
        re.IGNORECASE
    )
    
    total_articles = 0
    doc_count = 0
    total_docs = len(grouped)
    
    for doc_id, doc_df in grouped:
        doc_count += 1
        if doc_count % 1000 == 0:
            log.info(f"Processing document {doc_count}/{total_docs}...")
            
        doc_df = doc_df.sort_values(by="Page")
        first_row = doc_df.iloc[0]
        doc_lang = first_row.get("Language")
        
        # Build merged text with page markers
        merged_text = ""
        for _, row in doc_df.iterrows():
            merged_text += f"\n[PAGE_MARK: {row['Page']}]\n" + str(row["Clean_Content"])
            
        # Find all page markers and their indexes in the merged text
        page_markers = []
        for m in re.finditer(r'\[PAGE_MARK:\s*(\d+)\]', merged_text):
            page_markers.append((m.start(), int(m.group(1))))
            
        def get_page_for_index(idx):
            """Returns the page number corresponding to a character index in merged_text."""
            if not page_markers:
                return first_row["Page"]
            # Find the largest page marker start that is <= idx
            active_page = page_markers[0][1]
            for start_pos, page_num in page_markers:
                if start_pos <= idx:
                    active_page = page_num
                else:
                    break
            return active_page
            
        # Split text into article sections (filtering out inline cross-references)
        matches = []
        for m in article_pattern.finditer(merged_text):
            if is_article_definition(m, merged_text, language=doc_lang):
                matches.append(m)
                
        # Split text into article sections based on filtered matches
        parts = []
        last_end = 0
        for m in matches:
            parts.append(merged_text[last_end:m.start()])
            parts.append(m.group(0))
            last_end = m.end()
        parts.append(merged_text[last_end:])
        
        # Determine character positions of the splits in the merged_text
        # We search matches sequentially to find their character indexes
        current_pos = 0
        
        # First section is the preamble/visa text of the act
        preamble_text = parts[0].strip()
        preamble_clean = re.sub(r'\[PAGE_MARK:\s*\d+\]', '', preamble_text).strip()
        
        # Get metadata from the first page of the document
        
        if preamble_clean:
            # We treat the preamble as a virtual "Preamble" article
            start_page = get_page_for_index(0)
            end_page = get_page_for_index(len(parts[0]))
            page_range = f"{start_page}" if start_page == end_page else f"{start_page}-{end_page}"
            
            articles_data.append({
                "Article_ID": f"{doc_id}_Preamble",
                "Document_ID": doc_id,
                "Year": first_row["Year"],
                "Bulletin": first_row["Bulletin"],
                "Language": first_row["Language"],
                "Doc_Type": first_row["Doc_Type"],
                "Doc_Number": first_row["Doc_Number"],
                "Doc_Title": first_row["Doc_Title"],
                "Doc_Date_Hijri": first_row["Doc_Date_Hijri"],
                "Doc_Date_Gregorian": first_row["Doc_Date_Gregorian"],
                "Signatories": first_row["Signatories"],
                "Article_Name": "Preamble",
                "Article_Content": preamble_clean,
                "Pages": page_range
            })
            
        current_pos += len(parts[0])
        
        # Process actual article splits
        art_idx = 0
        for i in range(1, len(parts), 2):
            art_idx += 1
            total_articles += 1
            
            art_name_raw = parts[i]
            art_body_raw = parts[i+1] if i+1 < len(parts) else ""
            
            match_start = current_pos
            match_end = current_pos + len(art_name_raw) + len(art_body_raw)
            
            start_page = get_page_for_index(match_start)
            end_page = get_page_for_index(match_end)
            page_range = f"{start_page}" if start_page == end_page else f"{start_page}-{end_page}"
            
            # Remove inline page markers from content for clean RAG indexing
            clean_body = re.sub(r'\[PAGE_MARK:\s*\d+\]', '', art_body_raw).strip()
            
            articles_data.append({
                "Article_ID": f"{doc_id}_Art_{art_idx}",
                "Document_ID": doc_id,
                "Year": first_row["Year"],
                "Bulletin": first_row["Bulletin"],
                "Language": first_row["Language"],
                "Doc_Type": first_row["Doc_Type"],
                "Doc_Number": first_row["Doc_Number"],
                "Doc_Title": first_row["Doc_Title"],
                "Doc_Date_Hijri": first_row["Doc_Date_Hijri"],
                "Doc_Date_Gregorian": first_row["Doc_Date_Gregorian"],
                "Signatories": first_row["Signatories"],
                "Article_Name": art_name_raw.strip().capitalize(),
                "Article_Content": clean_body,
                "Pages": page_range
            })
            
            current_pos += len(art_name_raw) + len(art_body_raw)
            
    # Save the resulting article-level dataset
    log.info(f"Segmentation completed. Extracted {total_articles} total articles/preambles.")
    
    art_df = pd.DataFrame(articles_data)
    
    log.info(f"Saving article-level CSV database to '{OUTPUT_CSV}'...")
    art_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    
    log.info(f"Saving article-level Excel database to '{OUTPUT_XLSX}'...")
    # Excel sheet maximum cell limit safety truncation (32,767 characters)
    # We truncate exceptionally long articles (annexes or schedules) to prevent Excel errors
    def truncate_cell(val):
        if isinstance(val, str) and len(val) > 32000:
            return val[:32000] + " ... [TRUNCATED IN EXCEL VIEW]"
        return val
        
    excel_df = art_df.copy()
    excel_df["Article_Content"] = excel_df["Article_Content"].apply(truncate_cell)
    excel_df.to_excel(OUTPUT_XLSX, index=False)
    
    log.info("Article segmentation pipeline successfully completed!")

if __name__ == "__main__":
    main()
