-- Run this SQL in the Supabase SQL Editor to initialize your database tables

CREATE TABLE IF NOT EXISTS admins (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE,
    password_hash TEXT,
    role TEXT,
    created_at TIMESTAMP,
    last_login TIMESTAMP
);

CREATE TABLE IF NOT EXISTS checklist_versions (
    id TEXT PRIMARY KEY,
    client_name TEXT,
    role_name TEXT,
    google_doc_id TEXT,
    version TEXT,
    rules_json TEXT,
    hash TEXT,
    created_at TIMESTAMP,
    is_active BOOLEAN
);

CREATE TABLE IF NOT EXISTS resume_evaluations (
    id TEXT PRIMARY KEY,
    uploaded_at TIMESTAMP,
    candidate_name TEXT,
    vendor_name TEXT,
    resume_filename_original TEXT,
    resume_path TEXT,
    page_count INTEGER,
    checklist_version_id TEXT,
    rules_score REAL,
    llm_score REAL,
    overall_score REAL,
    rule_violations_json TEXT,
    section_scores_json TEXT,
    improvements_json TEXT,
    llm_output_json TEXT,
    model_name TEXT,
    prompt_version TEXT,
    human_label TEXT,
    is_training_data BOOLEAN DEFAULT FALSE,
    admin_corrected_json TEXT
);
