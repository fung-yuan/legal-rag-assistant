import os
import re
import json
import sqlite3
import logging
import pandas as pd

DB_PATH = r"c:\Users\dell\OneDrive\Desktop\chat_assistent\data\database.db"
CSV_PATH = r"c:\Users\dell\OneDrive\Desktop\chat_assistent\data\etl_intermediate\moroccan_law_articles.csv"
LOG_FILE = r"c:\Users\dell\OneDrive\Desktop\chat_assistent\data\logs\06_database_builder.log"

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

def clean_document_title(title):
    if not title or not isinstance(title, str):
        return title
    
    # 1. Fix common starting OCR patterns (done before stripping leading punctuation)
    title = re.sub(r'^!p\S*publi\S*tion\b', 'Publication', title, flags=re.IGNORECASE)
    title = re.sub(r'^!a\s+', 'La ', title, flags=re.IGNORECASE)
    
    # 2. Strip leading noise
    title = re.sub(r'^[^\w\u0600-\u06FF\(\[\{]+', '', title).strip()
    
    # 3. Fix layout noise words
    title = re.sub(r'^Pages\s+portant\s+', 'Portant ', title, flags=re.IGNORECASE)
    title = re.sub(r'^reconduisant\s+', 'Reconduisant ', title, flags=re.IGNORECASE)
    title = re.sub(r'^tel\s+qu\'il\s+', 'Tel qu\'il ', title, flags=re.IGNORECASE)
    title = re.sub(r'^portant\s+', 'Portant ', title, flags=re.IGNORECASE)
    title = re.sub(r'^tendant\s+', 'Tendant ', title, flags=re.IGNORECASE)
    
    # 4. Strip trailing/in-between gibberish
    title = re.sub(r'\s+porfwg\b', '', title, flags=re.IGNORECASE)
    
    # 5. Clean up corrupted phrases inside the title
    title = re.sub(r'lï\s*;\s*°\s*\d+%?–\d+.*?Dahir', 'loi ; Dahir', title)
    title = re.sub(r'lï\s*;\s*°\s*.*?\s*Dahir', 'loi ; Dahir', title)
    title = re.sub(r'lï\s*;\s*°\s*', 'loi n° ', title)
    title = re.sub(r'\blï\b', 'loi', title, flags=re.IGNORECASE)
    
    # 6. Safe word replacements
    replacements = {
        r'\bcoopration\b': 'coopération',
        r'\bcooprations\b': 'coopérations',
        r'\bannee\b': 'année',
        r'\bannees\b': 'années',
        r'\barrete\b': 'arrêté',
        r'\barretes\b': 'arrêtés',
        r'\bdecret\b': 'décret',
        r'\bdecrets\b': 'décrets',
        r'\bministre\b': 'ministère',
        r'\bsante\b': 'santé',
        r'\bmodifie\b': 'modifié',
        r'\bmodifies\b': 'modifiés',
        r'\bremplace\b': 'remplacé',
        r'\bremplaces\b': 'remplacés',
        r'\bgeneral\b': 'général',
        r'\bgeneraux\b': 'généraux',
        r'\breglement\b': 'règlement',
        r'\brepublique\b': 'république',
        r'\bfrancaise\b': 'française',
        r'\bfrancaises\b': 'françaises',
        r'\beconomique\b': 'économique',
        r'\beconomiques\b': 'économiques',
        r'\bmatiere\b': 'matière',
        r'\bdecembre\b': 'décembre',
        r'\bdelegation\b': 'délégation',
        r'\bdelegations\b': 'délégations',
        r'\bautorite\b': 'autorité',
        r'\bautorites\b': 'autorités',
        r'\btresor\b': 'Trésor',
        r'\bdesignees\b': 'désignées',
        r'\bdesignee\b': 'désignée',
        r'\bdeterminant\b': 'déterminant',
        r'\bquotites\b': 'quotités',
        r'\binterieures\b': 'intérieures',
        r'\binterieure\b': 'intérieure',
        r'\betranger\b': 'étranger',
        r'\betrangers\b': 'étrangers',
        r'\betrangeres\b': 'étrangères',
        r'\betrangere\b': 'étrangère',
        r'\bration\b': 'ration',
        r'\brafification\b': 'ratification',
    }
    
    for k, v in replacements.items():
        title = re.sub(k, v, title, flags=re.IGNORECASE)
    
    # Strip leading symbols again
    title = re.sub(r'^[^\w\u0600-\u06FF\(\[\{]+', '', title).strip()
    
    if title and title[0].islower():
        title = title[0].upper() + title[1:]
        
    return title

def clean_law_number(text):
    """Normalize law numbers to match IDs like '09-08' or '17-97'."""
    if not isinstance(text, str):
        return None
    # Look for patterns like n° 09-08 or n° 17.97
    match = re.search(r'(?:loi|décret)\s+(?:n°\s*)?(\d+)[-.](\d+)', text, re.IGNORECASE)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return None

def main():
    log.info("Starting Unified SQLite Database Builder...")

    if not os.path.exists(DB_PATH):
        log.error(f"Base database not found at '{DB_PATH}'. Please run build:db script first.")
        return

    if not os.path.exists(CSV_PATH):
        log.error(f"BO articles CSV not found at '{CSV_PATH}'.")
        return

    log.info(f"Connecting to database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    log.info("Purging old Bulletin Officiel data...")
    cursor.execute("DELETE FROM legal_provisions WHERE document_id LIKE 'BO_%'")
    prov_deleted = cursor.rowcount
    cursor.execute("DELETE FROM legal_documents WHERE id LIKE 'BO_%'")
    docs_deleted = cursor.rowcount
    cursor.execute("DELETE FROM cross_references WHERE source_document_id LIKE 'BO_%' OR target_document_id LIKE 'BO_%'")
    refs_deleted = cursor.rowcount
    log.info(f"Purged {prov_deleted} provisions, {docs_deleted} documents, and {refs_deleted} cross-references.")

    log.info(f"Loading BO articles from CSV: {CSV_PATH}")
    # Load in chunks or use low_memory to avoid memory exhaustion
    df = pd.read_csv(CSV_PATH, dtype=str)
    log.info(f"Loaded {len(df)} articles from CSV.")

    # 1. Insert BO Documents into legal_documents
    log.info("Ingesting Bulletin Officiel documents...")
    # Group by Document_ID to get unique documents
    doc_groups = df.groupby("Document_ID")
    total_docs = len(doc_groups)
    docs_inserted = 0

    # Retrieve existing base law IDs for reference mapping
    cursor.execute("SELECT id, title, short_name FROM legal_documents")
    existing_docs = cursor.fetchall()
    base_law_ids = {doc[0] for doc in existing_docs}
    log.info(f"Found {len(base_law_ids)} base laws already in DB.")

    # Compile a map of normalized law numbers in existing documents to their IDs
    # e.g., '09-08' -> '01-data-protection-law-09-08'
    base_law_number_map = {}
    for doc_id, doc_title, doc_short in existing_docs:
        num = clean_law_number(doc_id) or clean_law_number(doc_title) or clean_law_number(doc_short)
        if num:
            base_law_number_map[num] = doc_id
        # Also map standard ID numbers directly if present
        for chunk in doc_id.split("-"):
            if re.match(r'^\d+$', chunk) and len(chunk) >= 2:
                # Add to map if it's unique
                pass

    log.info(f"Compiled base law number mapping: {base_law_number_map}")

    # Insert BO documents
    for doc_id, doc_df in doc_groups:
        # Check if already exists
        cursor.execute("SELECT 1 FROM legal_documents WHERE id = ?", (doc_id,))
        if cursor.fetchone():
            continue

        first_row = doc_df.iloc[0]
        doc_type = first_row.get("Doc_Type", "statute")
        # Map doc_type to allowed values ('statute', 'bill', 'case_law')
        if doc_type.lower() in ["dahir", "loi", "décret", "arrêté"]:
            mapped_type = "statute"
        else:
            mapped_type = "statute"

        title = first_row.get("Doc_Title", "Untitled Document")
        cleaned_title = clean_document_title(title)
        issued_date = first_row.get("Doc_Date_Gregorian", None)
        short_name = first_row.get("Doc_Number", None)
        
        description = f"Bulletin Officiel N° {first_row.get('Bulletin', '')}"
        cleaned_desc = clean_document_title(description)

        cursor.execute("""
            INSERT OR IGNORE INTO legal_documents (id, type, title, title_en, short_name, status, issued_date, in_force_date, url, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            doc_id, mapped_type, cleaned_title, None, short_name, "in_force", issued_date, None, None, cleaned_desc
        ))
        docs_inserted += 1

    log.info(f"Inserted {docs_inserted} new BO documents.")

    # 2. Insert BO Articles into legal_provisions
    log.info("Ingesting Bulletin Officiel articles...")
    articles_inserted = 0
    
    # We will do batch insert for performance
    batch = []
    for idx, row in df.iterrows():
        doc_id = row["Document_ID"]
        prov_ref = row["Article_Name"]
        content = row["Article_Content"]
        
        if pd.isna(content) or not content.strip():
            continue
            
        # Standardize article names to match the provisions format
        metadata = {
            "year": row.get("Year"),
            "bulletin": row.get("Bulletin"),
            "language": row.get("Language"),
            "doc_number": row.get("Doc_Number"),
            "signatories": row.get("Signatories"),
            "pages": row.get("Pages")
        }
        metadata_str = json.dumps(metadata)
        
        batch.append((
            doc_id,
            prov_ref if pd.notna(prov_ref) else f"Article {idx}",
            None, # chapter
            "main", # section
            prov_ref, # title
            content,
            metadata_str
        ))
        
        if len(batch) >= 1000:
            cursor.executemany("""
                INSERT OR IGNORE INTO legal_provisions (document_id, provision_ref, chapter, section, title, content, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, batch)
            articles_inserted += len(batch)
            batch = []
            
    if batch:
        cursor.executemany("""
            INSERT OR IGNORE INTO legal_provisions (document_id, provision_ref, chapter, section, title, content, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, batch)
        articles_inserted += len(batch)

    log.info(f"Inserted {articles_inserted} articles/provisions into legal_provisions.")

    # 3. Build Cross-References (Linker)
    log.info("Linking amendments to base laws via heuristic matching...")
    xrefs_created = 0
    
    # Select all newly inserted BO documents
    cursor.execute("SELECT id, title FROM legal_documents WHERE id LIKE 'BO_%'")
    bo_docs = cursor.fetchall()
    
    for bo_id, title in bo_docs:
        # Check if the title mentions modifying or completing a law
        if not title:
            continue
            
        # Look for phrases like "modifiant et complétant la loi n° XX-XX" or "modifiant la loi n° XX-XX"
        # Search for law numbers in the title
        found_num = clean_law_number(title)
        if found_num and found_num in base_law_number_map:
            target_id = base_law_number_map[found_num]
            # Verify if this link already exists
            cursor.execute("""
                SELECT 1 FROM cross_references 
                WHERE source_document_id = ? AND target_document_id = ? AND ref_type = 'amended_by'
            """, (bo_id, target_id))
            
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO cross_references (source_document_id, source_provision_ref, target_document_id, target_provision_ref, ref_type)
                    VALUES (?, ?, ?, ?, 'amended_by')
                """, (bo_id, None, target_id, None))
                xrefs_created += 1

    log.info(f"Created {xrefs_created} cross-reference amendment links.")

    # 4. Synchronize FTS5 virtual tables
    log.info("Synchronizing Full-Text Search (provisions_fts)...")
    # FTS triggers are already active in schema, but we can do a rebuild if necessary
    cursor.execute("INSERT INTO provisions_fts(provisions_fts) VALUES('rebuild')")
    log.info("FTS5 rebuild completed.")

    conn.commit()
    conn.close()
    log.info("Unified database compilation successfully completed!")

if __name__ == "__main__":
    main()
