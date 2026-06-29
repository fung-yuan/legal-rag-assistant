"""
04_legal_classifier.py
======================
Scans cleaned page-level corpus sequentially to identify legal act boundaries.
Classifies pages and extracts metadata:
  1. Doc Type (Dahir, Décret, Arrêté, Décision, Circulaire)
  2. Doc Number (e.g. 1-23-85, 2-98-616)
  3. Signature dates (Hijri and Gregorian)
  4. Document Title / Subject
  5. Signatories
Assigns a unique Document_ID to group pages of the same act.
Outputs: data/moroccan_law_pages_classified.csv and .xlsx
"""

import os
import re
import logging
import pandas as pd
import numpy as np

INPUT_CSV = "data/etl_intermediate/moroccan_law_pages_cleaned.csv"
OUTPUT_CSV = "data/etl_intermediate/moroccan_law_pages_classified.csv"
OUTPUT_XLSX = "data/etl_intermediate/moroccan_law_pages_classified.xlsx"
LOG_FILE = "data/logs/04_legal_classifier.log"

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

# Heuristics for signatory name extraction from page signatures section
SIGNATORY_PATTERN = re.findall

def clean_title(title_candidate):
    """Clean and trim the extracted document title."""
    if not title_candidate:
        return ""
    # Collapse multiple spaces
    title = re.sub(r'\s+', ' ', title_candidate).strip()
    # If the title is too long, truncate it
    if len(title) > 300:
        title = title[:297] + "..."
    return title

def parse_document_header(text, start_pos):
    """
    Given a matched document header, try to extract Hijri/Gregorian dates,
    and scan forward to extract the title/subject of the act.
    """
    sub_text = text[start_pos:start_pos + 800] # Scan first 800 characters from header start
    
    # Try to parse dates: "du [Hijri] ([Gregorian])"
    hijri_date = ""
    greg_date = ""
    date_match = re.search(r'\bdu\s+([^(\n]{5,40})\s*\(([^)\n]{8,45})\)', sub_text, re.IGNORECASE)
    if date_match:
        hijri_date = date_match.group(1).strip()
        greg_date = date_match.group(2).strip()
    else:
        # Fallback date search
        greg_match = re.search(r'\b\d+\s+[a-zA-ZÀ-ÿ]+\s+\d{4}\b', sub_text)
        if greg_match:
            greg_date = greg_match.group(0).strip()
            
    # Try to extract the title
    # Legal act titles in Moroccan bulletins usually follow the date block and are introduced by
    # "portant..." or "relatif à..." or "sur le..." or follow directly after the date.
    # We will grab the text block starting after the date/number, looking for the first few sentences
    # or until the first "Article premier" or "Vu le..."
    title = ""
    title_start = 0
    if date_match:
        title_start = date_match.end()
    else:
        # Fallback to after the number match
        num_match = re.search(r'\bn°\s*(\d+[-–]\d+(?:[-–]\d+)?)\b', sub_text, re.IGNORECASE)
        if num_match:
            title_start = num_match.end()
            
    if title_start > 0:
        title_section = sub_text[title_start:].strip()
        # Truncate at common boundary markers
        end_markers = [
            r'(?i)\barticle\s+premier\b', 
            r'(?i)\bart\.\s*1\b', 
            r'(?i)\bvu\s+le\b', 
            r'(?i)\bvu\s+la\b', 
            r'(?i)\bvu\s+l\'\b',
            r'(?i)\ble\s+ministre\b',
            r'(?i)\ble\s+wali\b',
            r'(?i)\ble\s+chef\b',
            r'(?i)\ble\s+gouverneur\b',
            r'(?i)\bd[eé]cide\b',
            r'(?i)\bd[eé]cr[eè]te\b',
            r'(?i)\barr[eê]te\b',
            r'(?i)\bcirculaire\b',
            r'\n\s*\n'
        ]
        split_pos = len(title_section)
        for marker in end_markers:
            m = re.search(marker, title_section)
            if m and m.start() < split_pos:
                split_pos = m.start()
        
        title_candidate = title_section[:split_pos].strip()
        # Clean title prefix like "portant", "relatif à"
        title = clean_title(title_candidate)
        
    return hijri_date, greg_date, title

def extract_signatories(text):
    """Extract signatory names from signature blocks (ALL-CAPS names of 2+ words near the end)."""
    if not isinstance(text, str) or not text.strip():
        return ""
    
    # We look near signature-like terms like "Fait à", "Le Secrétaire général", "Pour contreseing"
    # and match capitalized names in the bottom half of the text
    lines = text.split('\n')
    signers = []
    
    # Standard entities blocklist
    blocklist = {
        'BULLETIN', 'OFFICIEL', 'ROYAUME', 'MAROC', 'TEXTES', 'GENERAUX', 
        'CHELLAH', 'PREMIER', 'MINISTRE', 'CHAMBRE', 'REPRESENTANTS'
    }
    
    # Look at bottom 40% lines of page
    start_idx = int(len(lines) * 0.6)
    bottom_text = " ".join(lines[start_idx:])
    
    candidates = re.findall(r'\b[A-Z\u00C0-\u00DC]{3,}(?:\s+[A-Z\u00C0-\u00DC]{3,})+\b', bottom_text)
    for cand in candidates:
        words = cand.split()
        if any(w in blocklist for w in words):
            continue
        name = " ".join(words)
        if 6 < len(name) < 35 and name not in signers:
            signers.append(name)
            
    return ", ".join(signers)

def main():
    log.info("Starting Legal Act Classification & Page Boundary Labeling...")
    
    if not os.path.exists(INPUT_CSV):
        log.error(f"Input file '{INPUT_CSV}' not found! Please run 03_text_cleaner.py first.")
        return
        
    df = pd.read_csv(INPUT_CSV, encoding="utf-8")
    df = df.sort_values(by=["Year", "Bulletin", "Page"]).reset_index(drop=True)
    df["Clean_Content"] = df["Clean_Content"].fillna("")
    
    log.info(f"Loaded {len(df)} pages for classification.")
    
    # Pre-allocate metadata columns
    df["Document_ID"] = ""
    df["Doc_Type"] = ""
    df["Doc_Number"] = ""
    df["Doc_Date_Hijri"] = ""
    df["Doc_Date_Gregorian"] = ""
    df["Doc_Title"] = ""
    df["Signatories"] = ""
    
    # Regex for act starts: "Dahir n° 1-XX-XX", "Décret n° 2-XX-XX", "Arrêté n° XX-XX"
    # Matches type and number
    doc_start_pattern = re.compile(
        r'\b(Dahir|Décret|Arrêté|Décision|Circulaire)\s+(?:[a-zA-ZÀ-ÿ\s]{1,40}\s+)?n°\s*(\d+[-–]\d+(?:[-–]\d+)?)\b',
        re.IGNORECASE
    )
    
    # Group by Bulletin to process sequentially
    bulletin_groups = df.groupby(["Year", "Bulletin"])
    
    total_docs_found = 0
    
    for (year, bulletin), group_df in bulletin_groups:
        indices = group_df.index
        
        current_doc_id = ""
        current_doc_type = ""
        current_doc_number = ""
        current_hijri_date = ""
        current_greg_date = ""
        current_doc_title = ""
        
        doc_counter = 0
        
        for idx in indices:
            row = df.loc[idx]
            content = row["Clean_Content"]
            page_num = row["Page"]
            
            # Check for new document starts on this page
            # Find all candidates
            matches = list(doc_start_pattern.finditer(content))
            valid_starts = []
            
            for m in matches:
                start_pos = m.start()
                # Increase preceding window to 150 chars to catch distant references (e.g., "promulguée par le...")
                preceding = content[max(0, start_pos - 150):start_pos]
                
                # Check the following 50 chars for reference terms like "précité", "susvisé"
                following = content[m.end():min(len(content), m.end() + 50)]
                
                is_reference = re.search(
                    r'\b(?:vu|promulg|vis|modif|complet|pris pour|application|confor|abrog|en vertu|loi\s+n)',
                    preceding,
                    re.IGNORECASE
                )
                
                is_body_mention = re.search(
                    r'\b(?:du|des|le|la|ce|cet|cette|les|aux|par|dans|sur)\s+(?:dit\s+)?(dahir|décret|arrêté|décision)\b',
                    preceding,
                    re.IGNORECASE
                )
                
                is_following_ref = re.search(
                    r'\b(?:précit|susvis|susvisée|modif|abrog)',
                    following,
                    re.IGNORECASE
                )
                
                if not is_reference and not is_body_mention and not is_following_ref:
                    valid_starts.append(m)
            
            if valid_starts:
                # A document starts on this page!
                # If multiple documents start on the same page, we flag it with the first one,
                # but log it. The article segmenter will split them at character offsets later.
                first_match = valid_starts[0]
                doc_counter += 1
                total_docs_found += 1
                
                doc_type_raw = first_match.group(1).strip()
                # Normalize doc type capitalization
                current_doc_type = doc_type_raw.capitalize()
                current_doc_number = first_match.group(2).strip()
                
                current_doc_id = f"BO_{bulletin}_{row['Language']}_Doc_{doc_counter}"
                
                # Parse dates and title
                current_hijri_date, current_greg_date, current_doc_title = parse_document_header(content, first_match.start())
                
                log.info(f"Detected document {current_doc_id}: {current_doc_type} n° {current_greg_date or current_doc_number} on Page {page_num}")
                
            # If we don't have a document ID yet (e.g. pages before the first document, like Table of Contents),
            # we label it as "SOMMAIRE"
            if not current_doc_id:
                df.at[idx, "Document_ID"] = f"BO_{bulletin}_{row['Language']}_SOMMAIRE"
                df.at[idx, "Doc_Type"] = "SOMMAIRE"
            else:
                # Carry forward the active document ID
                df.at[idx, "Document_ID"] = current_doc_id
                df.at[idx, "Doc_Type"] = current_doc_type
                df.at[idx, "Doc_Number"] = current_doc_number
                df.at[idx, "Doc_Date_Hijri"] = current_hijri_date
                df.at[idx, "Doc_Date_Gregorian"] = current_greg_date
                df.at[idx, "Doc_Title"] = current_doc_title
                
            # Extract signatories on every page (signatories will accumulate or be combined during article segmentation)
            df.at[idx, "Signatories"] = extract_signatories(content)
            
    # Post-process missing titles
    df["Doc_Title"] = df["Doc_Title"].replace("", "Sans titre / Document administratif")
    
    # Save results
    log.info(f"Classification completed. Found {total_docs_found} total legal documents.")
    log.info(f"Saving page-level classified data to '{OUTPUT_CSV}'...")
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    
    log.info(f"Saving styled Excel to '{OUTPUT_XLSX}'...")
    df.to_excel(OUTPUT_XLSX, index=False)
    log.info("Classification pipeline successfully completed!")

if __name__ == "__main__":
    main()
