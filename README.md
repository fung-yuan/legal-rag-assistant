# ADALA AI: Moroccan Law RAG Assistant (Multi-Agent & Hybrid Search)

Welcome to **ADALA AI**, a production-grade, bilingual (French & Arabic) Retrieval-Augmented Generation (RAG) assistant designed for Moroccan legislation, administrative codes, and official bulletins.

Tailored for the **Agence Urbaine de Laâyoune-Sakia El Hamra (AULSH)**, this system enables urban planners, legal advisors, and citizens to interact with Moroccan codes, verify administrative compliance with official portals, and explore legal citation networks dynamically.

---

## 🏗️ System Architecture & Workflow

The platform operates on a **Hybrid RAG + Multi-Agent Orchestration** architecture to ensure high-accuracy responses for domain-specific queries:

```
                      ┌────────────────────────────────────────┐
                      │               User Query               │
                      └───────────────────┬────────────────────┘
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
    1. Sparse Search (SQLite FTS5)                 2. Dense Search (ChromaDB)
    - Exact keyword matching                       - Semantic vector matching
    - Acts, decree & article numbers               - Jina Embeddings v4 (512-dim)
                  │                                               │
                  └───────────────────────┬───────────────────────┘
                                          ▼
                         3. Reciprocal Rank Fusion (RRF)
                         - Fuses & reranks lexical/vector hits
                                          │
                                          ▼
                                   Fused Contexts
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  │            4. Multi-Agent Retrieval Loop      │
                  │                                               │
                  │  ┌─────────────────────────────────────────┐  │
                  │  │ Agent 1 (Internal Legal Researcher)     │  │
                  │  │ - Analyzes local DB & cross-references  │  │
                  │  └────────────────────┬────────────────────┘  │
                  │                       ▼                       │
                  │  ┌─────────────────────────────────────────┐  │
                  │  │ Agent 2 (Compliance Web Researcher)     │  │
                  │  │ - Queries official portals & resources  │  │
                  │  └────────────────────┬────────────────────┘  │
                  │                       ▼                       │
                  │  ┌─────────────────────────────────────────┐  │
                  │  │ Agent 3 (Senior Synthesizer & Resolver) │  │
                  │  │ - Consolidates & streams response       │  │
                  │  └─────────────────────────────────────────┘  │
                  └───────────────────────┬───────────────────────┘
                                          ▼
                         ┌────────────────────────────────┐
                         │      Bilingual User Output     │
                         └────────────────────────────────┘
```

---

## 🌟 Key Features

1. **Hybrid Lexical-Semantic Search**:
   * **Lexical**: Indexed using SQLite's **FTS5** virtual tables, permitting instant matching of article numbers, decrees, and exact legal terminology.
   * **Semantic**: Embedded using **Jina Embeddings v4** and stored in a persistent **ChromaDB** collection.
   * **Re-ranking**: Ranked using **Reciprocal Rank Fusion (RRF)** to combine structural references and contextual meanings.
2. **Machine Learning Article boundary Classifier**:
   * Utilizes a character n-gram TF-IDF Vectorizer + Logistic Regression model to classify article mentions as either boundaries (true splits) or inline cross-references (such as *"l'article 19"*). This prevents incorrect text cutting bugs during segmentation.
3. **Collaborative 3-Agent Orchestrator**:
   * **Agent 1 (Internal Legal Researcher)**: Summarizes local database clauses and verifies legal amendments.
   * **Agent 2 (Compliance Web Researcher)**: Dynamically maps queries to official compliance resources (e.g., CNDP, SGG, Rokhas, Cour Constitutionnelle).
   * **Agent 3 (Senior Synthesizer & Resolver)**: Adapts the response language (Arabic, French, or English) to match the user's query exactly, providing clean Markdown summaries and reference cards.
4. **Interactive Citation Graph**:
   * Utilizes a **D3.js force-directed graph** in the frontend to visualize links and amendment networks between Bulletin Officiel documents.
5. **Bilingual PDF Document Viewer & Toggle**:
   * Serves scans of Bulletins Officiels side-by-side with extracted texts, allowing a seamless toggle between French and Arabic translations of synchronized articles.

---

## 📂 Codebase Directory Layout

```
chat_assistent/
├── pipeline/                             <-- Core Backend Engine (Python)
│   ├── app_server.py                     <-- FastAPI Entry Point (hosts REST API, PDF viewer, SSE stream)
│   ├── agent_orchestrator.py             <-- 3-Agent Collaborative Search & Keyword Extractor
│   ├── models/                           <-- Model binaries
│   │   └── article_classifier.pkl        <-- Trained article boundary ML model
│   └── etl/                              <-- Active Data Ingestion & Ingest Pipeline
│       ├── 01_ocr_extractor.py           <-- High-speed parallel native/OCR text extractor
│       ├── 02_generate_excel.py          <-- Master page-level Excel/CSV aggregator
│       ├── 03_text_cleaner.py            <-- Normalizer, divider remover, & soft-hyphen polisher
│       ├── 04_legal_classifier.py        <-- Legal act boundary & document ID classifier
│       ├── generate_classifier_data.py   <-- Auto-labels context samples from text corpus
│       ├── train_article_classifier.py   <-- Trains and serializes the Logistic Regression model
│       ├── 05_article_segmenter.py       <-- Article-level parser, classifier predictor & boundary segmenter
│       ├── 06_database_builder.py        <-- Consolidated SQLite relational builder (with purge queries)
│       └── 07_vector_indexer.py          <-- ChromaDB visual layout indexer using Jina API
│
├── frontend/                             <-- Responsive Next.js UI Application
│   ├── src/app/page.tsx                  <-- Agent Console Chat Panel & Saved Session Manager
│   └── src/components/ForceGraph.tsx     <-- Interactive D3.js Force-Directed Citation Graph
│
├── data/                                 <-- Databases, logs, and compiled assets
│   ├── database.db                       <-- Core relational SQLite database
│   ├── chroma_db/                        <-- ChromaDB Persistent Vector Store
│   ├── raw_pdfs/                         <-- Raw Arabic Bulletin Officiel PDFs (includes moudawana.pdf)
│   ├── raw_pdfs_fr/                      <-- Raw French Bulletin Officiel PDFs
│   └── etl_intermediate/                 <-- Housing CSV intermediate datasets
│
└── .env                                  <-- Environment keys (OPENAI_API_KEY, JINA_API_KEYS)
```

---

## 🚀 Ingestion Pipeline (ETL) & Machine Learning Training

The document ingestion pipeline is structured sequentially under `pipeline/etl/`:

1. **`01_ocr_extractor.py`**: Extracts text from PDFs page-by-page. For scanned sheets, it triggers Tesseract OCR fallbacks.
2. **`02_generate_excel.py`**: Aggregates extracted pages into a single flat CSV registry.
3. **`03_text_cleaner.py`**: Polishes raw text outputs, normalizes spacing, and strips soft hyphens (`\xad`).
4. **`04_legal_classifier.py`**: Flags starting boundaries of individual decrees, laws, or acts.
5. **`generate_classifier_data.py`**: Generates weakly labeled dataset `labeled_article_context.csv` around article matches.
6. **`train_article_classifier.py`**: Trains the char-level n-gram TF-IDF + Logistic Regression model pipeline and saves it to `pipeline/models/article_classifier.pkl`.
7. **`05_article_segmenter.py`**: Loads the ML model to dynamically skip inline mentions and split text only on true article boundaries, generating `moroccan_law_articles.csv`.
8. **`06_database_builder.py`**: Purges stale Bulletin Officiel tables, ingests new articles into `database.db`, establishes cross-references, and rebuilds FTS5.
9. **`07_vector_indexer.py`**: Renders pages as images and indexes them using Jina Embeddings v4 into ChromaDB.

---

## 💻 Running the Application

### 1. Prerequisites
Ensure you have the following installed on your system:
* **Python 3.10+** (FastAPI backend)
* **Node.js 18+** (Next.js frontend)
* **Tesseract OCR Engine** (for offline scanned PDF extraction fallback)

### 2. Environment Configuration
Create a `.env` file in the root directory:
```env
OPENAI_API_KEY=your_openai_api_key_here
JINA_API_KEYS=key1,key2
```

### 3. Running the Backend Server
```bash
# From workspace root
python pipeline/app_server.py
```
The server starts locally at `http://127.0.0.1:8000`.

### 4. Running the Frontend Client
```bash
# Navigate to frontend and install dependencies
cd frontend
npm install

# Run the development server
npm run dev
```
The web application console starts locally at `http://localhost:3000`.

---

## 🔌 Key API Endpoints

* **`POST /api/chat`**: Streams collaborative multi-agent response chunks using server-sent events (SSE).
* **`GET /api/pdf-view`**: Returns the scanned Bulletin Officiel PDF for a given bulletin number, language, and year.
* **`GET /api/provisions/correspond`**: Resolves programmatic bidirectional correspondence for bilingual articles.
* **`GET /api/stats`**: Serves corpus statistics (total document count, provision count, and language distributions).
