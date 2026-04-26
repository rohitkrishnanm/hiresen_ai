# Vision Board Resume X — Plan & Architecture (Complete Blueprint)

## 1) Product Definition

**Vision Board Resume X** is a **GenAI + Rules Engine** platform that evaluates resume quality against **Vision Board’s checklist** stored in **Google Docs**, provides structured scoring and improvement guidance to users, and gives administrators a monitoring dashboard with audit-ready history.

### Core Capabilities

* Resume upload (PDF/DOCX; MVP can enforce PDF)
* Resume parsing → structured sections
* Strict checklist compliance validation (rule engine)
* Quality evaluation & coaching (LLM)
* User-facing scorecard + suggestions
* Admin login + full monitoring (uploads, candidate/vendor, score, output)
* Checklist sync from Google Docs with versioning
* Open-source friendly storage (Local FS + SQLite)

### Current implementation notes

* Admin access is now backed by hashed credentials via `ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH` instead of hardcoded values.
* The upload flow captures both candidate name and vendor name again, and the persisted submission record keeps both fields.
* Overall scoring is normalized through a shared helper so the rules score and LLM score are combined consistently.

---

## 2) User Roles & Access Model

### Role: User (Candidate / Submitter)

* Upload resume
* Enter candidate name + vendor name (Vision Board requirement)
* View evaluation result (only their submission)

### Role: Admin (Devi / Vision Board Team / You)

* Login protected route
* View all submissions
* Drill-down into any evaluation
* See violations, full AI output, checklist version used
* See metrics: uploads/day, average score, top violations

**Access rule:**
Users see only their own results (session-level). Admin sees everything.

---

## 3) Architecture Overview (Layered Design)

Vision Board Resume X uses a **hybrid evaluation pipeline**:

### Layer A — Streamlit App (Presentation)

* `User Portal` page(s)
* `Admin Portal` page(s)

### Layer B — Orchestration & Business Logic

* Submission controller
* Checklist manager
* Evaluation pipeline manager
* Report generator (optional)

### Layer C — Evaluation Engine

* Deterministic Rules Engine (strict validation)
* LLM Evaluator (quality scoring + coaching)

### Layer D — Storage & Audit

* Local file system (resume PDFs)
* SQLite DB (metadata, scores, outputs)
* Checklist JSON cache + DB version history

### Layer E — External Integrations

* Google Docs API (checklist sync)
* OpenAI API (LLM evaluation) *(or later Azure OpenAI)*

---

## 4) Component-Level Architecture (What Modules Exist)

### 4.1 Streamlit UI Modules

**User UI**

* Upload widget
* Candidate details input (Name, Vendor)
* Submit button
* Results:

  * overall score
  * section scores
  * rule violations
  * prioritized improvements

**Admin UI**

* Login
* Dashboard KPIs
* Submissions table
* Search/filter (date range, vendor, score band)
* Drill-down detail view
* Checklist sync status page (version + last updated)

---

### 4.2 Checklist Sync Manager (Google Docs → JSON Rules)

**Goal:** Let Devi update checklist in Google Docs and your system uses latest rules reliably.

**Responsibilities**

* Fetch Google Docs content
* Detect changes (hash)
* Parse doc text → structured rules JSON
* Store checklist version in DB
* Maintain “active checklist” pointer

**Why not raw-doc prompting?**

* Token waste
* Inconsistent interpretation
* No audit trail
* Hard to enforce strict checks

---

### 4.3 Resume Parser

**Responsibilities**

* Validate file type
* Extract:

  * raw text
  * sections: summary, skills, experience, education, certifications
  * page count (PDF)
* Normalize formatting (remove duplicate whitespace, preserve bullet points)

**Tools**

* PDF: `pymupdf` (fast) or `pdfplumber`
* DOCX: `python-docx` (optional Phase-2)

---

### 4.4 Rules Engine (Deterministic)

**Goal:** Enforce Vision Board rules as objective validations.

Rules engine produces:

* Pass/Fail per rule
* Violations list (with evidence)
* Compliance score

**Example validations from your checklist**

* Must be PDF
* Filename must match: `RESUME AZURE DATA ENGINEER_<NAME>`
* Must include: Email, Phone, Base Location, LinkedIn
* Summary must mention:

  * “Azure Data Engineer”
  * years of experience
  * required skills keywords (ADF, SQL, Python, PySpark, Databricks)
* Work experience must include:

  * Company-Role-Period format
  * Current role as Azure Data Engineer
  * Minimum 10 responsibility bullets
  * Highlight keywords
* Certifications must include:

  * DP900, DP700, Databricks Associate, Databricks Fundamentals, Databricks GenAI Fundamentals
* Education: highest qualification only
* Page count rule based on experience years

**Important:** Keyword “highlighted” is hard to validate reliably in plain text; treat it as:

* **Rule engine:** keyword presence
* **LLM:** whether the resume emphasizes keywords effectively

---

### 4.5 LLM Evaluator (Quality + Coaching)

LLM is used only for **judgment-based** evaluation.

LLM produces:

* section quality scores
* strengths
* gaps
* rewrite suggestions
* improvements prioritized by impact

**LLM constraints**

* Must return JSON only
* Must not invent missing info
* Must reference resume content or mark missing

---

## 5) Data Storage Architecture (Open-Source Friendly)

### 5.1 File Storage (Resumes)

* Local file system directory structure:

  * `storage/resumes/YYYY-MM-DD/<sanitized_filename>.pdf`

Resumes stored as files; DB stores only the relative path.

**GitHub note**

* Keep storage folder in `.gitignore`
* Provide folder scaffolding only

---

### 5.2 Database (SQLite)

Stores:

* Submission metadata
* Parsed extracted text (optional / can store reduced sections for privacy)
* Scores + violations + LLM output
* Checklist version used
* Model/prompt versions (audit trail)

---

## 6) Database Schema (Recommended)

### Table: `checklist_versions`

* `id` (UUID)
* `client_name` (“Vision Board”)
* `role_name` (“Azure Data Engineer”)
* `google_doc_id`
* `version` (e.g., v1.0, v1.1)
* `rules_json` (TEXT)
* `hash` (TEXT) — detects change
* `created_at`
* `is_active` (BOOL)

### Table: `resume_evaluations`

* `id` (UUID)
* `uploaded_at`
* `candidate_name`
* `vendor_name`
* `resume_filename_original`
* `resume_path` (local)
* `page_count`
* `experience_years_detected` (optional)
* `checklist_version_id`
* `rules_score`
* `llm_score`
* `overall_score`
* `rule_violations_json`
* `section_scores_json`
* `improvements_json`
* `llm_output_json`
* `model_name`
* `prompt_version`

### Table: `admins`

* `id`
* `username`
* `password_hash`
* `role` (admin/superadmin)
* `created_at`
* `last_login`

---

## 7) End-to-End Workflows (Data Flow)

### Workflow A — Checklist Sync

1. Admin sets Google Doc ID (config)
2. System pulls doc content
3. Compute hash:

   * If same → do nothing
   * If changed → parse → save new `checklist_versions` row and set active
4. Admin dashboard shows:

   * active checklist version
   * last sync time

---

### Workflow B — User Submission

1. User uploads resume
2. User fills: Candidate Name + Vendor
3. Resume saved to local storage
4. Resume parsed into structured sections + page count
5. Rules engine runs → violations + rules_score
6. LLM evaluator runs → llm_score + suggestions
7. Orchestrator combines:

   * `overall_score = 0.4*rules_score + 0.6*llm_score` (example; configurable)
8. Save DB record
9. Display result to user

---

### Workflow C — Admin Monitoring

1. Admin logs in
2. Sees:

   * total resumes
   * today’s uploads
   * avg score
   * top violations
3. Table view with filters
4. Drill-down view shows:

   * resume file link/path
   * violations with evidence
   * full LLM JSON output
   * checklist version used

---

## 8) Prompt Design (Governed + Versioned)

### System Prompt (stable)

* “You are a strict resume auditor for Azure Data Engineer… do not hallucinate…”

### User Prompt (dynamic)

Includes:

* Parsed resume sections
* Checklist summary derived from JSON rules
* Instructions: produce JSON only

### Output Schema (strict)

Must include:

* `section_scores`
* `strengths`
* `gaps`
* `rewrite_suggestions`
* `priority_actions`
* `confidence` (optional)

**Prompt versioning**
Store a `prompt_version` in DB so you can compare changes over time.

---

## 9) Security & Privacy Controls (Minimum Required)

* Hash admin passwords (bcrypt)
* `.env` for keys (never commit)
* `.gitignore`:

  * `.env`
  * `data/*.db`
  * `storage/resumes/`
* Avoid logging resume content
* Optional retention policy (delete resumes after N days)

---

## 10) Deployment Plan (GitHub + OSS)

### MVP deployment options

* **Local run** (best for dev)
* **Streamlit Community Cloud** (works but file persistence is limited)

### Production-ready open-source friendly hosting

* Any Linux VM + systemd
* Docker optional (later)
* PostgreSQL optional (later)

---

## 11) Recommended Repository Structure (Professional)

```
hiresense-ai/
│
├── app.py
├── pages/
│   ├── 1_User_Upload.py
│   ├── 2_User_Result.py
│   ├── 9_Admin_Login.py
│   └── 10_Admin_Dashboard.py
│
├── core/
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   └── logger.py
│
├── checklist/
│   ├── parser_google_doc.py
│   ├── rules_schema.py
│   └── cache/
│       └── vision_board_ade_v1.json
│
├── evaluation/
│   ├── resume_parser.py
│   ├── rules_engine.py
│   ├── llm_evaluator.py
│   ├── prompt_templates.py
│   └── scoring.py
│
├── storage/
│   └── resumes/   (gitignored)
│
├── data/
│   └── hiresense.db (gitignored)
│
├── .env.example
├── requirements.txt
└── README.md
```

---

## 12) Phased Execution Plan (What You Build First)

### Phase 1 — MVP (End-to-End)

* User upload page
* PDF parsing
* Rules engine (all strict checks)
* Single LLM evaluation call (JSON output)
* SQLite persistence
* Admin login + submissions table + drill-down

### Phase 2 — Google Docs Sync + Versioning

* Google Docs API connection
* Doc → JSON parser
* Checklist version table
* Admin “sync now” button + status

### Phase 3 — Reporting + Analytics

* PDF report export
* Admin export CSV
* Analytics charts (score distribution, daily uploads)

### Phase 4 — Hardening & Scale

* Add retention policy
* Add caching for LLM results
* Upgrade DB to Postgres (optional)
* Optional: multi-role checklists (BA, Data Analyst, etc.)

---
