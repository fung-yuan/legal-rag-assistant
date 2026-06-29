import sys
import os
import json
import logging
import sqlite3
import re
import math
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from pydantic import BaseModel

def sanitize_nans(val):
    if isinstance(val, dict):
        return {k: sanitize_nans(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [sanitize_nans(v) for v in val]
    elif isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
    return val

# Add current path to import pipeline modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import importlib
orchestrator = importlib.import_module("pipeline.agent_orchestrator")
search_local_db = orchestrator.search_local_db
search_web_mock = orchestrator.search_web_mock
client = orchestrator.client

app = FastAPI(title="Moroccan Law AI Assistant API")

# Enable CORS for Next.js frontend running on localhost:3000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str

def get_pdf_fallback_html(bulletin: str, year: str):
    clean_bulletin = bulletin or "Non spécifié"
    clean_year = year or "Non spécifiée"
    content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Document non disponible</title>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&display=swap" rel="stylesheet">
        <style>
            body {{
                font-family: 'Plus Jakarta Sans', sans-serif;
                background-color: #f8fafc;
                color: #334155;
                margin: 0;
                padding: 40px 20px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 80vh;
                text-align: center;
            }}
            .card {{
                background: white;
                padding: 40px;
                border-radius: 24px;
                box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05);
                border: 1px solid #e2e8f0;
                max-width: 420px;
                width: 100%;
            }}
            .icon {{
                font-size: 48px;
                margin-bottom: 20px;
            }}
            h1 {{
                font-size: 18px;
                font-weight: 800;
                color: #1e293b;
                margin: 0 0 10px 0;
            }}
            p {{
                font-size: 13px;
                color: #64748b;
                line-height: 1.6;
                margin: 0 0 24px 0;
            }}
            .badge {{
                display: inline-block;
                background-color: #f1f5f9;
                color: #475569;
                padding: 6px 12px;
                border-radius: 8px;
                font-size: 11px;
                font-weight: 700;
                margin-bottom: 20px;
            }}
            .divider {{
                height: 1px;
                background-color: #e2e8f0;
                margin: 20px 0;
                width: 100%;
            }}
            .tip {{
                font-size: 11px;
                color: #94a3b8;
                font-style: italic;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">📄</div>
            <h1>Document PDF non disponible</h1>
            <p>Le scan officiel du Bulletin Officiel n'est pas disponible dans nos archives locales pour cette référence.</p>
            <div class="badge">
                Bulletin: {clean_bulletin} (Année: {clean_year})
            </div>
            <div class="divider"></div>
            <p class="tip">Vous pouvez toujours consulter le texte complet extrait du document juridique dans le panneau de gauche.</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=content, status_code=200)

@app.get("/api/pdf-view")
def view_pdf_page(lang: str, year: str, bulletin: str):
    if bulletin == "moudawana" or bulletin == "ma-adala-family-118":
        file_path = r"c:\Users\dell\OneDrive\Desktop\chat_assistent\data\raw_pdfs\مدونة الأسرة.pdf"
        if os.path.exists(file_path):
            return FileResponse(file_path, media_type="application/pdf")
        else:
            return get_pdf_fallback_html(bulletin, year)
            
    # Intercept custom Arabic document PDFs
    custom_pdfs = {
        "ma-code-famille": "family_code.pdf",
        "family_code": "family_code.pdf",
        "ma-code-penal": "penal_code.pdf",
        "penal_code": "penal_code.pdf",
        "ma-doc": "obligations_contracts.pdf",
        "obligations_contracts": "obligations_contracts.pdf",
        "ma-real-rights": "real_rights.pdf",
        "real_rights": "real_rights.pdf",
        "ma-code-commerce": "commerce_code.pdf",
        "commerce_code": "commerce_code.pdf",
        "ma-code-travail": "labor_code.pdf",
        "labor_code": "labor_code.pdf",
        "ma-criminal-procedure": "criminal_procedure.pdf",
        "criminal_procedure": "criminal_procedure.pdf",
        "ma-civil-procedure": "civil_procedure.pdf",
        "civil_procedure": "civil_procedure.pdf",
        "ma-alternative-sanctions": "alternative_sanctions.pdf",
        "alternative_sanctions": "alternative_sanctions.pdf",
    }
    
    if bulletin:
        bulletin_clean = bulletin.lower().replace("_ar", "").replace("_fr", "")
        if bulletin_clean in custom_pdfs:
            file_name = custom_pdfs[bulletin_clean]
            file_path = os.path.join(r"c:\Users\dell\OneDrive\Desktop\chat_assistent\data\raw_pdfs", file_name)
            if os.path.exists(file_path):
                return FileResponse(file_path, media_type="application/pdf")
            else:
                return get_pdf_fallback_html(bulletin, year)
                
    if year == "Unknown" or not bulletin or not year:
        return get_pdf_fallback_html(bulletin, year)
        
    try:
        # Determine base directory
        base_dir = r"c:\Users\dell\OneDrive\Desktop\chat_assistent\data\raw_pdfs_fr" if lang.lower() == "fr" else r"c:\Users\dell\OneDrive\Desktop\chat_assistent\data\raw_pdfs"
        
        # Target directory for the specific year
        year_dir = os.path.join(base_dir, year)
        if not os.path.exists(year_dir):
            return get_pdf_fallback_html(bulletin, year)
            
        # Clean bulletin ID (e.g. BO_4758_Fr or BO_4758_fr)
        target_pattern = f"{bulletin.lower()}.pdf"
        matched_filename = None
        
        try:
            for f in os.listdir(year_dir):
                if f.lower() == target_pattern or f.lower().startswith(bulletin.lower()):
                    matched_filename = f
                    break
        except Exception:
            return get_pdf_fallback_html(bulletin, year)
            
        if not matched_filename:
            # Fallback to standard name
            matched_filename = f"{bulletin}.pdf"
             
        file_path = os.path.join(year_dir, matched_filename)
        if not os.path.exists(file_path):
            return get_pdf_fallback_html(bulletin, year)
             
        return FileResponse(file_path, media_type="application/pdf")
    except Exception:
        return get_pdf_fallback_html(bulletin, year)

@app.post("/api/chat")
async def chat_endpoint(request: QueryRequest):
    if not client:
        raise HTTPException(status_code=500, detail="OpenAI client not initialized on backend.")

    query = request.query
    
    def event_generator():
        try:
            # 1. Start Agent 1
            yield json.dumps({"status": "agent_1_start", "message": "Agent 1: Querying local DB..."}) + "\n"
            
            db_results = search_local_db(query)
            try:
                parsed_db = json.loads(db_results)
                db_citations = sanitize_nans(parsed_db.get("matched_articles", []))
            except Exception:
                db_citations = []
            
            # Let Agent 1 formulate a brief
            agent_1_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are Agent 1 (Moroccan Law Database Researcher). Summarize the local laws and amendment documents matching the user request. Focus only on the facts in the provided database context. Cite specific articles and modification decrees. The database contains content in both French and Arabic — include relevant findings from BOTH languages in your summary. Always write your internal summary in French and include Arabic article text verbatim where retrieved."},
                    {"role": "user", "content": f"User Query: {query}\n\nDatabase Context:\n{db_results}"}
                ],
                temperature=0.2
            )
            brief_1 = agent_1_response.choices[0].message.content
            yield json.dumps({"status": "agent_1_done", "data": brief_1}) + "\n"

            # 2. Start Agent 2
            yield json.dumps({"status": "agent_2_start", "message": "Agent 2: Searching web/portals..."}) + "\n"
            
            web_results = search_web_mock(query)
            try:
                parsed_web = json.loads(web_results)
                brief_2 = parsed_web.get("brief", "")
                parsed_resources = parsed_web.get("resources", [])
            except Exception:
                brief_2 = "Standard administrative lookup. Please consult the official gazettes or relevant ministerial portals directly for forms and guidelines."
                parsed_resources = []
                
            yield json.dumps({"status": "agent_2_done", "data": brief_2}) + "\n"

            # 3. Start Agent 3
            yield json.dumps({"status": "agent_3_start", "message": "Agent 3: Synthesizing final advice..."}) + "\n"
            
            agent_3_response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": """You are Agent 3 (Senior Moroccan Legal Advisor). Synthesize the work of Agent 1 (local legal text database) and Agent 2 (administrative portals and guides) into a premium, authoritative, concise response.

LANGUAGE RULE (CRITICAL):
- Detect the language of the User Query.
- If the query is in Arabic (العربية), respond ENTIRELY in Arabic — including all headings, labels, legal terms, and explanations. Use proper Modern Standard Arabic (MSA).
- If the query is in French, respond entirely in French.
- If the query is in English, respond entirely in English.
- NEVER mix languages in the same response.

CRITICAL SCOPE RULES:
- This system's LOCAL database specializes in: digital/tech law (09-08, 05-20, 31-08, 43-20), the complete Moroccan Penal Code (Code Pénal), and Bulletin Officiel articles.
- EXTENDED COVERAGE via official web sources: The Cour Constitutionnelle (cour-constitutionnelle.ma/Documents/Lois/) hosts consolidated PDFs of ALL major Moroccan codes — Family Law (Moudawana), Code du Commerce, Obligations et Contrats, Code du Travail, Procédure Civile, Procédure Pénale, Droit Foncier, Droit de l'Eau, Droit de l'Environnement, Droit des Sociétés, etc. Reference these when relevant.
- If Agent 1's local database results are UNRELATED to the query, clearly label it as outside local scope, then answer using your general knowledge of Moroccan law and direct to the Cour Constitutionnelle PDF library.
- When the query IS within local scope (digital/tech laws or Penal Code), give a thorough synthesis with specific article citations.
- For family law, property law, labor law, commercial law: draw from general knowledge AND point to the relevant PDF on the Cour Constitutionnelle site via the resource cards.
- Do NOT write raw URLs in your text — they appear as separate cards.
- Format in clean markdown with alerts."""},
                    {"role": "user", "content": f"User Query: {query}\n\nAgent 1 (Base Laws & Amendments):\n{brief_1}\n\nAgent 2 (Portals & Forms):\n{brief_2}"}
                ],
                temperature=0.3
            )
            final_answer = agent_3_response.choices[0].message.content
            
            yield json.dumps({
                "status": "agent_3_done", 
                "data": final_answer,
                "resources": parsed_resources,
                "citations": db_citations
            }) + "\n"

        except Exception as e:
            yield json.dumps({"status": "error", "message": str(e)}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

@app.get("/api/documents")
def get_documents():
    if not os.path.exists(orchestrator.DB_PATH):
        raise HTTPException(status_code=404, detail="Database not found.")
        
    conn = sqlite3.connect(orchestrator.DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT d.id, d.title, d.status, d.issued_date, d.description, d.short_name, COUNT(p.id)
            FROM legal_documents d
            LEFT JOIN legal_provisions p ON d.id = p.document_id
            GROUP BY d.id
            ORDER BY d.title
        """)
        rows = cursor.fetchall()
        docs = []
        for r in rows:
            docs.append({
                "id": r[0],
                "title": r[1],
                "status": r[2],
                "issued_date": r[3],
                "description": r[4],
                "short_name": r[5],
                "provision_count": r[6]
            })
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/documents/{document_id}/provisions")
def get_provisions(document_id: str, query: str = None):
    if not os.path.exists(orchestrator.DB_PATH):
        raise HTTPException(status_code=404, detail="Database not found.")
        
    conn = sqlite3.connect(orchestrator.DB_PATH)
    cursor = conn.cursor()
    try:
        if query:
            cursor.execute("""
                SELECT id, provision_ref, title, content, metadata
                FROM legal_provisions
                WHERE document_id = ? AND (content LIKE ? OR provision_ref LIKE ? OR title LIKE ?)
                LIMIT 100
            """, (document_id, f"%{query}%", f"%{query}%", f"%{query}%"))
        else:
            cursor.execute("""
                SELECT id, provision_ref, title, content, metadata
                FROM legal_provisions
                WHERE document_id = ?
            """, (document_id,))
            
        rows = cursor.fetchall()
        provisions = []
        for r in rows:
            ref = r[1] or ""
            num_match = re.search(r'\d+', ref)
            sort_num = int(num_match.group(0)) if num_match else 999999
            
            prov_metadata = sanitize_nans(json.loads(r[4])) if r[4] else {}
            
            lang = prov_metadata.get("language")
            if not lang:
                content = r[3] or ""
                if re.search(r'[\u0600-\u06FF]', content):
                    lang = "AR"
                else:
                    lang = "FR"
            prov_metadata["language"] = lang.upper()
            
            provisions.append({
                "id": r[0],
                "provision_ref": r[1],
                "title": r[2],
                "content": r[3],
                "metadata": prov_metadata,
                "sort_num": sort_num
            })
            
        provisions.sort(key=lambda x: x["sort_num"])
        return provisions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/provisions/correspond")
def get_corresponding_provision(document_id: str, provision_ref: str, target_lang: str):
    if not os.path.exists(orchestrator.DB_PATH):
        raise HTTPException(status_code=404, detail="Database not found.")

    conn = sqlite3.connect(orchestrator.DB_PATH)
    cursor = conn.cursor()

    try:
        target_lang = target_lang.upper()

        # Dynamic/programmatic translation mapping fallback for the Land Registry Law (Dahir 1-11-177 / Loi 39-08)
        if document_id == "BO_BO_6004_Fr_FR_Doc_5" and target_lang == "AR":
            ref_lower = provision_ref.lower().strip()
            if ref_lower in ("article premier", "article 1"):
                target_ref = "art1"
            else:
                target_ref = ref_lower.replace("article ", "art").replace(" ", "")
                
            cursor.execute("""
                SELECT provision_ref, content, metadata
                FROM legal_provisions
                WHERE document_id = ? AND provision_ref = ?
                LIMIT 1
            """, ("ma-adala-real-estate-128", target_ref))
            match = cursor.fetchone()
            if match:
                # Get current french page to estimate arabic page
                cursor.execute("""
                    SELECT metadata FROM legal_provisions
                    WHERE document_id = ? AND provision_ref = ?
                    LIMIT 1
                """, (document_id, provision_ref))
                cur_row = cursor.fetchone()
                cur_meta = json.loads(cur_row[0]) if cur_row and cur_row[0] else {}
                try:
                    pages_str = cur_meta.get("pages") or cur_meta.get("page_number") or "1"
                    first_page_match = re.search(r'\d+', pages_str)
                    french_page = int(first_page_match.group(0)) if first_page_match else 1
                    # French code is 155 pages, Arabic is 104 pages
                    estimated_page = int(french_page * (104.0 / 155.0))
                    if estimated_page < 1:
                        estimated_page = 1
                except Exception:
                    estimated_page = 1
                
                return {
                    "document_id":   "ma-adala-real-estate-128",
                    "provision_ref": match[0],
                    "page":          str(estimated_page),
                    "content":       match[1],
                    "metadata": {
                        "year": "2011",
                        "bulletin": "BO_5994_Ar",
                        "language": "AR",
                        "pages": str(estimated_page)
                    }
                }

        if document_id == "ma-adala-real-estate-128" and target_lang == "FR":
            ref_lower = provision_ref.lower().strip()
            if ref_lower == "art1":
                target_ref = "Article premier"
            else:
                num_part = ref_lower.replace("art", "")
                target_ref = f"Article {num_part}"
                
            cursor.execute("""
                SELECT provision_ref, content, metadata
                FROM legal_provisions
                WHERE document_id = ? AND provision_ref = ?
                LIMIT 1
            """, ("BO_BO_6004_Fr_FR_Doc_5", target_ref))
            match = cursor.fetchone()
            if match:
                meta = json.loads(match[2]) if match[2] else {}
                pages = meta.get("pages") or meta.get("page_number") or "1"
                return {
                    "document_id":   "BO_BO_6004_Fr_FR_Doc_5",
                    "provision_ref": match[0],
                    "page":          pages,
                    "content":       match[1],
                    "metadata":      meta
                }

        # 1. Get the current provision metadata to extract its bulletin ID
        cursor.execute("""
            SELECT metadata FROM legal_provisions
            WHERE document_id = ? AND provision_ref = ?
            LIMIT 1
        """, (document_id, provision_ref))
        row = cursor.fetchone()
        if not row:
            return None

        cur_meta    = json.loads(row[0]) if row[0] else {}
        cur_bulletin = cur_meta.get("bulletin", "")
        cur_year     = cur_meta.get("year", "")

        if not cur_bulletin or not cur_year:
            return None

        # 2. Derive the target-language bulletin ID by swapping _Fr / _Ar suffix
        if target_lang == "AR":
            target_bulletin = re.sub(r"_[Ff][Rr]$", "_Ar", cur_bulletin)
        else:
            target_bulletin = re.sub(r"_[Aa][Rr]$", "_Fr", cur_bulletin)

        if target_bulletin == cur_bulletin:
            return None  # Already in the requested language

        # 3. Find the matching provision in the target bulletin by provision_ref + year
        cursor.execute("""
            SELECT p.document_id, p.provision_ref, p.metadata, p.content
            FROM legal_provisions p
            WHERE p.provision_ref = ?
              AND json_extract(p.metadata, "$.bulletin") = ?
              AND json_extract(p.metadata, "$.year")    = ?
            LIMIT 1
        """, (provision_ref, target_bulletin, cur_year))
        match = cursor.fetchone()
        if match:
            meta  = json.loads(match[2]) if match[2] else {}
            pages = meta.get("pages") or meta.get("page_number") or "1"
            return {
                "document_id":   match[0],
                "provision_ref": match[1],
                "page":          pages,
                "content":       match[3],
            }

        return None
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/stats")
def get_database_stats():
    if not os.path.exists(orchestrator.DB_PATH):
        raise HTTPException(status_code=404, detail="Database not found.")
        
    conn = sqlite3.connect(orchestrator.DB_PATH)
    cursor = conn.cursor()
    try:
        # 1. Total documents count
        cursor.execute("SELECT COUNT(*) FROM legal_documents")
        total_docs = cursor.fetchone()[0]
        
        # 2. Total provisions count
        cursor.execute("SELECT COUNT(*) FROM legal_provisions")
        total_provs = cursor.fetchone()[0]
        
        # 3. Top 5 documents by provision count
        cursor.execute("""
            SELECT d.id, d.title, COUNT(p.id)
            FROM legal_documents d
            JOIN legal_provisions p ON d.id = p.document_id
            GROUP BY d.id
            ORDER BY COUNT(p.id) DESC
            LIMIT 5
        """)
        top_docs_rows = cursor.fetchall()
        top_documents = []
        for r in top_docs_rows:
            top_documents.append({
                "id": r[0],
                "title": r[1],
                "provision_count": r[2]
            })
            
        # 4. Years distribution
        cursor.execute("""
            SELECT json_extract(metadata, '$.year') as yr, COUNT(*)
            FROM legal_provisions
            GROUP BY yr
            ORDER BY yr ASC
        """)
        years_rows = cursor.fetchall()
        years_distribution = []
        for r in years_rows:
            yr = r[0]
            if yr is None or yr == "0" or yr == "":
                yr = "Unknown"
            years_distribution.append({
                "year": yr,
                "count": r[1]
            })
            
        # 5. Language distribution
        cursor.execute("SELECT id, title FROM legal_documents")
        doc_langs = {}
        for doc_id, doc_title in cursor.fetchall():
            if doc_title and re.search(r'[\u0600-\u06FF]', doc_title):
                doc_langs[doc_id] = "AR"
            else:
                doc_langs[doc_id] = "FR"
                
        cursor.execute("SELECT document_id, COUNT(*) FROM legal_provisions GROUP BY document_id")
        lang_distribution = {"AR": 0, "FR": 0}
        for doc_id, count in cursor.fetchall():
            lang = doc_langs.get(doc_id, "FR")
            lang_distribution[lang] = lang_distribution.get(lang, 0) + count
            
        return {
            "total_documents": total_docs,
            "total_provisions": total_provs,
            "top_documents": top_documents,
            "years_distribution": years_distribution,
            "language_distribution": lang_distribution
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
