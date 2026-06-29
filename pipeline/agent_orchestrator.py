import os
import re
import sys
import json
import sqlite3
import argparse
from openai import OpenAI
from dotenv import load_dotenv

# Load env variables from root .env
load_dotenv(dotenv_path=r"c:\Users\dell\OneDrive\Desktop\chat_assistent\.env")

# Secure print override to handle encoding crashes on Windows cmd stdout
def print(*args, **kwargs):
    sep = kwargs.get('sep', ' ')
    end = kwargs.get('end', '\n')
    text = sep.join(str(arg) for arg in args) + end
    enc = sys.stdout.encoding or 'utf-8'
    sys.stdout.buffer.write(text.encode(enc, errors='replace'))
    sys.stdout.flush()

DB_PATH = r"c:\Users\dell\OneDrive\Desktop\chat_assistent\data\database.db"

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("WARNING: OPENAI_API_KEY not found in environment. Agent calls will fail.")
client = OpenAI(api_key=api_key) if api_key else None

def search_local_db(query_text):
    """Agent 1's primary tool: Search the consolidated SQLite database."""
    if not os.path.exists(DB_PATH):
        return f"Error: Database not found at {DB_PATH}."
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Parse query to see if specific law numbers are mentioned (e.g. 09-08)
    law_nums = re.findall(r'\b\d+[-.]\d+\b', query_text)
    doc_results = []
    
    for num in law_nums:
        normalized = num.replace(".", "-")
        # Search documents
        cursor.execute("""
            SELECT id, title, status, issued_date, description 
            FROM legal_documents 
            WHERE id LIKE ? OR title LIKE ? OR short_name LIKE ?
        """, (f"%{normalized}%", f"%{normalized}%", f"%{normalized}%"))
        docs = cursor.fetchall()
        for doc in docs:
            doc_results.append({
                "type": "base_law",
                "id": doc[0],
                "title": doc[1],
                "status": doc[2],
                "issued_date": doc[3],
                "description": doc[4]
            })
            
    # 2. Extract bilingual keywords (French + Arabic) using LLM to match database content
    search_keywords = ""
    if client:
        try:
            kw_completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a bilingual legal translation assistant. Extract the core specific legal nouns and subject concepts from the query in both French and Arabic. Do NOT include generic legal terms like 'peine', 'loi', 'article', 'condamnation', 'délit', 'crime', 'maroc', 'procédure', 'cas', 'قانون', 'مادة', 'عقوبة', 'جريمة', 'المغرب', 'حكم'. Return ONLY a space-separated list containing 2-4 specific French keywords followed by 2-4 specific Arabic keywords, with no explanations, no prefix, and no markdown formatting. For example: 'what is the sentence for a murder case' -> 'meurtre assassinat homicide قتل عمد جناية', 'how are CNDP data transfers authorized' -> 'transfert données personnelles نقل معطيات شخصية'."},
                    {"role": "user", "content": query_text}
                ],
                temperature=0.1,
                max_tokens=100
            )
            kws = kw_completion.choices[0].message.content.strip()
            kws_clean = re.sub(r'[^a-zA-Z0-9\sàâäéèêëîïôöùûüç\u0600-\u06FF]', ' ', kws).strip()
            if kws_clean:
                search_keywords = kws_clean
        except Exception as e:
            pass

    if not search_keywords:
        search_keywords = query_text

    # 3. Search provisions using FTS5 virtual table
    # We clean the query for FTS5 syntax safety (preserving French accents and Arabic Unicode)
    clean_query = re.sub(r'[^a-zA-Z0-9\sàâäéèêëîïôöùûüç\u0600-\u06FF]', ' ', search_keywords).strip()
    fts_results = []
    if clean_query:
        # Split into words and join with OR. Filter out common stopwords in EN, FR, and AR.
        stopwords = {
            "what", "is", "the", "for", "a", "case", "in", "of", "and", "to", "on", "about",
            "quelle", "est", "la", "pour", "un", "une", "des", "les", "dans", "de", "et", "sur",
            "في", "من", "على", "إلى", "عن", "مع", "أو", "أن", "هذا", "هذه", "التي", "الذي", "ما"
        }
        words = [f'"{w}"' for w in clean_query.split() if w and w.lower() not in stopwords]
        
        if not words:
            words = [f'"{w}"' for w in clean_query.split() if w]
            
        fts_query = " OR ".join(words)
        
        try:
            cursor.execute("""
                SELECT p.document_id, p.provision_ref, p.title, p.content, p.metadata
                FROM legal_provisions p
                JOIN provisions_fts f ON p.id = f.rowid
                WHERE provisions_fts MATCH ?
                ORDER BY rank
                LIMIT 8
            """, (fts_query,))
            provisions = cursor.fetchall()
            for prov in provisions:
                fts_results.append({
                    "document_id": prov[0],
                    "provision_ref": prov[1],
                    "title": prov[2],
                    "content": prov[3],
                    "metadata": json.loads(prov[4]) if prov[4] else {}
                })
        except Exception as e:
            # Fallback to simple LIKE search if FTS fails
            cursor.execute("""
                SELECT document_id, provision_ref, title, content, metadata
                FROM legal_provisions
                WHERE content LIKE ? OR title LIKE ?
                LIMIT 5
            """, (f"%{clean_query}%", f"%{clean_query}%"))
            provisions = cursor.fetchall()
            for prov in provisions:
                fts_results.append({
                    "document_id": prov[0],
                    "provision_ref": prov[1],
                    "title": prov[2],
                    "content": prov[3],
                    "metadata": json.loads(prov[4]) if prov[4] else {}
                })

    # 3. Retrieve linked amendments for any matched documents
    matched_doc_ids = set([d["id"] for d in doc_results] + [p["document_id"] for p in fts_results])
    amendments = []
    
    for doc_id in matched_doc_ids:
        cursor.execute("""
            SELECT xr.source_document_id, d.title, d.issued_date, p.provision_ref, p.content
            FROM cross_references xr
            JOIN legal_documents d ON xr.source_document_id = d.id
            LEFT JOIN legal_provisions p ON d.id = p.document_id
            WHERE xr.target_document_id = ? AND xr.ref_type = 'amended_by'
        """, (doc_id,))
        amends = cursor.fetchall()
        for amend in amends:
            amendments.append({
                "amendment_doc_id": amend[0],
                "title": amend[1],
                "issued_date": amend[2],
                "provision_ref": amend[3],
                "content": amend[4]
            })

    conn.close()
    
    # Structure the findings
    findings = {
        "matched_laws": doc_results,
        "matched_articles": fts_results,
        "linked_amendments": amendments
    }
    return json.dumps(findings, indent=2, ensure_ascii=False)

def search_web_mock(query_text):
    """Agent 2's tool: Structured single-call web compliance generation with verified URLs."""
    if not client:
        return json.dumps({"brief": "No OpenAI client available.", "resources": []})
    log_prompt = f"Searching administrative portals for: '{query_text}'"
    print(f"[*] Agent 2 (Web Researcher): {log_prompt}")
    
    # Hand-verified active official Moroccan portals and platforms
    verified_database = [
        # ── DIGITAL LAW & DATA PROTECTION ──────────────────────────────────────
        {
            "keywords": ["cndp", "données personnelles", "protection des données", "donnee", "privacy", "rgpd"],
            "title": "CNDP - Portail de Protection des Données",
            "url": "https://www.cndp.ma",
            "snippet": "Portail officiel de la Commission Nationale de contrôle de la protection des Données à caractère Personnel pour les déclarations de conformité."
        },
        {
            "keywords": ["cndp", "données personnelles", "transfert", "étranger"],
            "title": "CNDP - Demandes de Transfert Hors du Maroc",
            "url": "https://www.cndp.ma",
            "snippet": "Guides and formulaires officiels pour l'autorisation de transfert de données à caractère personnel à l'étranger."
        },
        {
            "keywords": ["cybersecurite", "dgssi", "sécurité", "cloud", "vital", "loi 05-20"],
            "title": "DGSSI - Direction Générale de la Sécurité des Systèmes d'Information",
            "url": "https://www.dgssi.gov.ma",
            "snippet": "Portail national de la DGSSI détaillant la conformité aux règlements de sécurité pour les infrastructures critiques."
        },
        {
            "keywords": ["signature", "trust", "loi 43-20", "électronique", "cryptographique", "cachet", "confiance"],
            "title": "DGSSI - Prestataires de Services de Confiance Agréés",
            "url": "https://www.dgssi.gov.ma",
            "snippet": "Liste des prestataires et autorités nationales agréées pour délivrer des signatures et certificats électroniques réglementés."
        },
        # ── OFFICIAL GAZETTES & LEGISLATION ────────────────────────────────────
        {
            "keywords": ["bulletin", "sgg", "dahir", "officiel", "publication", "décret", "loi"],
            "title": "SGG - Bulletins Officiels du Maroc",
            "url": "https://www.sgg.gov.ma/BulletinOfficiel.aspx",
            "snippet": "Accès officiel aux archives du Bulletin Officiel du Royaume du Maroc pour consulter les textes législatifs publiés."
        },
        {
            "keywords": ["loi", "sgg", "codes", "organique", "statut", "penal", "civil"],
            "title": "SGG - Codes Consolidés Officiels",
            "url": "https://www.sgg.gov.ma/Legislation.aspx",
            "snippet": "Publications officielles des codes juridiques consolidés (Code Pénal, de Commerce, de la Route) par le SGG."
        },
        # ── CONSTITUTIONAL COURT DOCUMENTS LIBRARY ─────────────────────────────
        {
            "keywords": ["cour constitutionnelle", "loi organique", "constitution", "moudawana", "famille", "code pénal", "code de commerce", "code de la route",
                         "obligations et contrats", "procédure civile", "procédure pénale", "travail", "nationalité",
                         "immobilier", "foncier", "eau", "environnement", "mines", "énergie", "baux", "loyer",
                         "consommateur", "blanchiment", "sociétés", "fiscalité", "douane", "pensions", "justice",
                         "نظام", "مدونة", "قانون", "مسطرة"],
            "title": "Cour Constitutionnelle - Bibliothèque des Lois",
            "url": "https://www.cour-constitutionnelle.ma/Documents/Lois/",
            "snippet": "Bibliothèque numérique officielle de la Cour Constitutionnelle du Maroc hébergeant les PDFs consolidés de tous les codes majeurs (Pénal, Commerce, Famille, Travail, Procédure Civile, Eau, Mines, Sociétés, etc.)."
        },
        {
            "keywords": ["moudawana", "famille", "mariage", "divorce", "kafala", "succession", "héritage", "enfant",
                         "garde", "tutelle", "filiation", "répudiation", "pension alimentaire",
                         "الأسرة", "زواج", "طلاق", "نسب", "حضانة"],
            "title": "Moudawana (Code de la Famille) - Cour Constitutionnelle",
            "url": "https://www.cour-constitutionnelle.ma/Documents/Lois/%D9%85%D8%AF%D9%88%D9%86%D8%A9%20%D8%A7%D9%84%D8%A3%D8%B3%D8%B1%D8%A9.pdf",
            "snippet": "Texte complet et officiel de la Moudawana (Code de la Famille Marocain) en arabe, hébergé par la Cour Constitutionnelle."
        },
        {
            "keywords": ["commerce", "commercial", "société", "entreprise", "fonds de commerce",
                         "obligations", "contrats", "vente", "achat", "bail commercial", "krac",
                         "التجارة", "عقد", "شركة"],
            "title": "Code de Commerce & Obligations - Cour Constitutionnelle",
            "url": "https://www.cour-constitutionnelle.ma/Documents/Lois/%D9%85%D8%AF%D9%88%D9%86%D8%A9%20%D8%A7%D9%84%D8%AA%D8%AC%D8%A7%D8%B1%D8%A9.pdf",
            "snippet": "PDFs officiels du Code de Commerce marocain et du Dahir des Obligations et Contrats (DOC), hébergés par la Cour Constitutionnelle."
        },
        {
            "keywords": ["immobilier", "propriété", "foncier", "hypothèque", "copropriété", "emphytéose", "loyer",
                         "bail", "immeuble", "habitat", "lotissement", "expropriation",
                         "العقار", "ملكية", "كراء", "رهن"],
            "title": "Droit Immobilier & Foncier - Cour Constitutionnelle",
            "url": "https://www.cour-constitutionnelle.ma/Documents/Lois/",
            "snippet": "Ensemble des textes juridiques sur le droit immobilier au Maroc : bail, copropriété, lotissements, expropriation, droits réels, enregistrement foncier — tous disponibles en PDF officiel."
        },
        {
            "keywords": ["travail", "salaire", "licenciement", "grève", "syndicat", "congé", "contrat de travail",
                         "cnss", "sécurité sociale", "accident de travail", "employeur", "salarié",
                         "الشغل", "العمل", "أجر", "فصل"],
            "title": "Code du Travail & CNSS - Maroc",
            "url": "https://www.cour-constitutionnelle.ma/Documents/Lois/%D9%85%D8%AF%D9%88%D9%86%D8%A9%20%D8%A7%D9%84%D8%B4%D8%BA%D9%84.pdf",
            "snippet": "Texte consolidé du Code du Travail marocain (Moudawana Choghl). Pour la protection sociale, voir aussi le portail CNSS (cnss.ma)."
        },
        {
            "keywords": ["cnss", "retraite", "pension", "sécurité sociale", "cotisation", "maladie", "AMO"],
            "title": "CNSS - Caisse Nationale de Sécurité Sociale",
            "url": "https://www.cnss.ma",
            "snippet": "Portail officiel de la CNSS pour l'affiliation, le paiement des cotisations, les droits aux prestations (retraite, maladie, maternité)."
        },
        {
            "keywords": ["mineur", "pénal", "crime", "délit", "infraction", "peine", "prison", "condamnation",
                         "procédure pénale", "code pénal", "tribunal correctionnel", "cour d'appel", "parquet",
                         "جريمة", "عقوبة", "حكم", "جنح"],
            "title": "Code Pénal & Procédure Pénale - Cour Constitutionnelle",
            "url": "https://www.cour-constitutionnelle.ma/Documents/Lois/%D9%85%D8%AC%D9%85%D9%88%D8%B9%D8%A9%20%D8%A7%D9%84%D9%82%D8%A7%D9%86%D9%88%D9%86%20%D8%A7%D9%84%D8%AC%D9%86%D8%A7%D8%A6%D9%8A.pdf",
            "snippet": "Texte officiel du Code Pénal marocain (Moudawana Qanoun Jina'i) et du Code de Procédure Pénale, en version PDF consolidée."
        },
        # ── CONSUMER PROTECTION & COMMERCE ─────────────────────────────────────
        {
            "keywords": ["consommateur", "loi 31-08", "achat", "vente", "protection", "mcinet"],
            "title": "MCINET - Protection du Consommateur Marocain",
            "url": "https://www.mcinet.gov.ma/fr/content/protection-du-consommateur",
            "snippet": "Règles, guides d'achat, délais de rétractation et droits des consommateurs sous la Loi 31-08."
        },
        # ── URBANISM & CONSTRUCTION ────────────────────────────────────────────
        {
            "keywords": ["permis", "construire", "urbanisme", "construction", "batiment", "maison", "architecte", "plan", "rokhas", "immeuble"],
            "title": "Rokhas - Portail National des Autorisations d'Urbanisme",
            "url": "https://www.rokhas.ma",
            "snippet": "Plateforme numérique officielle pour le dépôt des demandes et l'obtention des permis de construire et d'aménager au Maroc."
        },
        {
            "keywords": ["urbanisme", "construction", "amenagement", "habitat", "ville", "foncier", "muat"],
            "title": "Ministère de l'Urbanisme et de l'Habitat (MUAT)",
            "url": "https://www.muat.gov.ma",
            "snippet": "Site officiel du Ministère de l'Aménagement du Territoire National, de l'Urbanisme, de l'Habitat et de la Politique de la Ville."
        },
        {
            "keywords": ["urbanisme", "casablanca", "agence", "auc"],
            "title": "Agence Urbaine de Casablanca (AUC)",
            "url": "https://www.auc.ma",
            "snippet": "Portail officiel de l'AUC fournissant les notes de renseignements d'urbanisme, les règlements et plans d'aménagement de Casablanca."
        },
        # ── JUSTICE & JUDICIAL PROCEDURES ─────────────────────────────────────
        {
            "keywords": ["justice", "tribunal", "procedure", "civil", "penal", "adala", "avocat", "juge", "recours"],
            "title": "Ministère de la Justice du Maroc",
            "url": "https://www.justice.gov.ma",
            "snippet": "Portail officiel du Ministère de la Justice fournissant les services judiciaires électroniques et l'accès à la législation pénale."
        },
        {
            "keywords": ["adala", "jurisprudence", "décision", "jugement", "arrêt", "cassation", "appel"],
            "title": "Adala - Portail de la Justice Marocaine",
            "url": "https://adala.justice.gov.ma",
            "snippet": "Portail national Adala pour l'accès aux textes législatifs, la jurisprudence et les services juridiques électroniques."
        },
        # ── ENVIRONMENT & NATURAL RESOURCES ───────────────────────────────────
        {
            "keywords": ["environnement", "eau", "pollution", "déchets", "énergie", "mines", "forêt", "côte", "nature"],
            "title": "Cour Constitutionnelle - Lois Environnementales",
            "url": "https://www.cour-constitutionnelle.ma/Documents/Lois/",
            "snippet": "Textes officiels des lois marocaines sur l'eau, la protection de l'environnement, la gestion des déchets, les mines, et les énergies renouvelables."
        },
        # ── FISCAL & FINANCIAL LAW ─────────────────────────────────────────────
        {
            "keywords": ["impôt", "fiscal", "taxe", "TVA", "DGI", "finances", "budget", "loi de finances"],
            "title": "DGI - Direction Générale des Impôts",
            "url": "https://www.tax.gov.ma",
            "snippet": "Portail officiel de la DGI pour les déclarations fiscales, le calcul de l'IS, IR, et TVA, et les guides fiscaux en vigueur."
        },
        {
            "keywords": ["banque", "crédit", "financement", "taux", "Bank Al-Maghrib", "BAM", "microfinance"],
            "title": "Bank Al-Maghrib",
            "url": "https://www.bkam.ma",
            "snippet": "Banque centrale du Maroc. Réglementation bancaire, statistiques monétaires et financières, politique de change."
        },
        # ── FOREIGN NATIONALS & IMMIGRATION ───────────────────────────────────
        {
            "keywords": ["étranger", "immigration", "visa", "résidence", "naturalisation", "expulsion"],
            "title": "DGMRE - Direction Générale des MRE et Affaires de la Migration",
            "url": "https://www.marocainsdumonde.gov.ma",
            "snippet": "Portail officiel dédié aux Marocains Résidant à l'Étranger et à la législation sur l'immigration au Maroc."
        },
    ]
    
    query_lower = query_text.lower()
    scored = []
    for r in verified_database:
        score = sum(1 for kw in r["keywords"] if kw in query_lower)
        scored.append((score, r))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    matching = [item for score, item in scored if score > 0]
    
    # Fill remaining spots with default high-quality links if we have less than 4 matches
    defaults = [
        {"title": "Secrétariat Général du Gouvernement (SGG)", "url": "https://www.sgg.gov.ma", "snippet": "Official legal texts, codes, and government bulletins."},
        {"title": "Ministère de la Justice du Maroc", "url": "https://www.justice.gov.ma", "snippet": "Portail officiel du Ministère de la Justice pour les services judiciaires."},
        {"title": "Rokhas - Portail des Autorisations d'Urbanisme", "url": "https://www.rokhas.ma", "snippet": "Portail national pour l'obtention des permis de construire."},
        {"title": "CNDP - Portail de Protection des Données", "url": "https://www.cndp.ma", "snippet": "Portail de conformité pour la protection des données personnelles."}
    ]
    
    selected_options = matching[:4]
    seen_urls = {r["url"] for r in selected_options}
    for d in defaults:
        if len(selected_options) >= 4:
            break
        if d["url"] not in seen_urls:
            selected_options.append(d)
            seen_urls.add(d["url"])
            
    options_str = json.dumps(selected_options, indent=2, ensure_ascii=False)
    
    # Combined single LLM call for both brief and resources array
    web_gen = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"""You are a web research assistant specializing in Moroccan law and administrative compliance procedures.
            
            Given a user query, you must perform two actions and return them inside a single JSON object:
            1. Compile a written `brief` (in the SAME LANGUAGE as the user query — Arabic, French, or English, 2-3 paragraphs) summarizing the administrative guidelines, forms, and compliance procedures related to the query. Focus on operational details, forms, external processes, and URLs.
            2. Choose 2-4 `resources` (official portals and guides) from the provided verified options that are most relevant to the query.
            
            LANGUAGE RULE: Detect the language of the user query and write the `brief` in that language entirely. If Arabic, use proper Modern Standard Arabic.
            
            CANDIDATE VERIFIED RESOURCES (You must ONLY select from this list):
            {options_str}
            
            RULES FOR RESOURCES:
            - You MUST copy the `title` and `url` EXACTLY from the candidate list above. Do not alter them or hallucinate other websites.
            - Write a custom, query-specific `snippet` for each chosen resource detailing how it applies to the query.
            
            Return ONLY a valid JSON object matching this schema, with no markdown fencing:
            {{
              "brief": "Your detailed text here...",
              "resources": [
                {{ "title": "...", "url": "...", "snippet": "..." }}
              ]
            }}"""},
            {"role": "user", "content": f"Query: {query_text}"}
        ],
        temperature=0.2
    )
    try:
        raw = web_gen.choices[0].message.content.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
        results = json.loads(raw)
        if "brief" not in results:
            results["brief"] = "No compliance brief could be generated."
        if "resources" not in results:
            results["resources"] = []
    except Exception:
        results = {
            "brief": "Standard administrative lookup. Please consult the official gazettes or relevant ministerial portals directly for forms and guidelines.",
            "resources": selected_options[:2]
        }
    return json.dumps(results, indent=2, ensure_ascii=False)

def run_agent_workflow(user_query):
    if not client:
        return "Error: OpenAI client not initialized. Check your API key in the .env file."
        
    print(f"\n[+] Starting 3-Agent Collaborative Search for: '{user_query}'\n")
    
    # --- AGENT 1: Local Database Researcher ---
    print("[*] Launching Agent 1 (Internal Legal Database Researcher)...")
    db_results = search_local_db(user_query)
    
    # Let Agent 1 formulate a legal brief based on database findings
    agent_1_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are Agent 1 (Moroccan Law Database Researcher). Summarize the local laws and amendment documents matching the user request. Focus only on the facts in the provided database context. Cite specific articles and modification decrees. The database contains content in both French and Arabic — include relevant findings from BOTH languages in your summary. Always write your internal summary in French and include Arabic article text verbatim where retrieved."},
            {"role": "user", "content": f"User Query: {user_query}\n\nDatabase Context:\n{db_results}"}
        ],
        temperature=0.2
    )
    brief_1 = agent_1_response.choices[0].message.content
    print("\n[OK] Agent 1 complete. Brief:")
    print("-" * 50)
    print(brief_1)
    print("-" * 50)
    
    # --- AGENT 2: Live Web Searcher ---
    print("\n[*] Launching Agent 2 (Web Researcher)...")
    web_results = search_web_mock(user_query)
    
    try:
        parsed_web = json.loads(web_results)
        brief_2 = parsed_web.get("brief", "")
    except Exception:
        brief_2 = "Error generating web compliance brief."
        
    print("\n[OK] Agent 2 complete. Brief:")
    print("-" * 50)
    print(brief_2)
    print("-" * 50)
    
    # --- AGENT 3: Synthesizer & Resolver ---
    print("\n[*] Launching Agent 3 (Senior Legal Resolver)...")
    
    agent_3_response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": """You are Agent 3 (Senior Moroccan Legal Advisor). Your job is to synthesize findings from Agent 1 (local law database) and Agent 2 (web portals) into a clear, authoritative, structured response.

LANGUAGE RULE (CRITICAL):
- Detect the language of the User Query.
- If the query is in Arabic (العربية), respond ENTIRELY in Arabic — all headings, labels, legal terms, explanations. Use proper Modern Standard Arabic (MSA).
- If the query is in French, respond entirely in French.
- If the query is in English, respond entirely in English.
- NEVER mix languages in the same response.

CRITICAL SCOPE RULES:
- This system's LOCAL database specializes in: digital/tech law (09-08, 05-20, 31-08, 43-20), the complete Moroccan Penal Code (Code Pénal), and Bulletin Officiel articles related to those domains.
- EXTENDED COVERAGE via official web sources: The Cour Constitutionnelle (cour-constitutionnelle.ma/Documents/Lois/) hosts consolidated PDFs of ALL major Moroccan codes — including Family Law (Moudawana), Code du Commerce, Code des Obligations et Contrats, Code du Travail, Procédure Civile, Procédure Pénale, Droit Foncier (Immobilier), Droit de l'Eau, Droit de l'Environnement, Droit des Sociétés, etc. Reference these when relevant.
- If Agent 1's local database findings are UNRELATED to the user's query, clearly state it is outside local scope, then provide the best general answer from your knowledge of Moroccan law labeled as 'General Knowledge', and direct the user to the relevant Cour Constitutionnelle PDF.
- Do NOT present irrelevant local database results as if they answer the user's question.
- When the query IS within local scope (digital/tech laws or Penal Code), give a thorough synthesis with specific article citations and amendment timelines.
- For family law, property law, labor law, commercial law — draw from your general knowledge AND point to the relevant PDF on the Cour Constitutionnelle site.
- Format responses in clean markdown with appropriate alerts."""},
            {"role": "user", "content": f"User Query: {user_query}\n\nAgent 1 (Base Laws & Amendments from local DB):\n{brief_1}\n\nAgent 2 (Web Portals & Official Resources):\n{brief_2}"}
        ],
        temperature=0.3
    )
    final_answer = agent_3_response.choices[0].message.content
    print("\n[OK] Agent 3 complete. Final Answer:")
    print("=" * 60)
    print(final_answer)
    print("=" * 60)
    return final_answer

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Moroccan Law AI 3-Agent Collaborative Search Orchestrator")
    parser.add_argument("--query", type=str, help="The query to search and answer")
    parser.add_argument("--test-search", type=str, help="Quick query on database only to test indexing")
    
    args = parser.parse_args()
    
    if args.test_search:
        print(f"Testing local DB search for: {args.test_search}")
        print(search_local_db(args.test_search))
    elif args.query:
        run_agent_workflow(args.query)
    else:
        # Interactive mode or fallback query
        fallback = "What are the requirements of data protection law 09-08 and how is it modified?"
        run_agent_workflow(fallback)
