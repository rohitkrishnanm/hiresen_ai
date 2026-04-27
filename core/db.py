import sqlite3
import json
import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "hiresense.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Prevent write contention under concurrent users
    conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes, still crash-safe
    return conn


def get_admin_by_username(username: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        row = conn.execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_admin_last_login(username: str):
    conn = get_db_connection()
    try:
        conn.execute('UPDATE admins SET last_login = ? WHERE username = ?', (datetime.now(), username))
        conn.commit()
    finally:
        conn.close()

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Checklists Table
    c.execute('''
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
        )
    ''')
    
    # Resume Evaluations Table
    c.execute('''
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
            is_training_data BOOLEAN DEFAULT 0,
            admin_corrected_json TEXT
        )
    ''')
    
    # Admins Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE,
            password_hash TEXT,
            role TEXT,
            created_at TIMESTAMP,
            last_login TIMESTAMP
        )
    ''')
    
    # Migration: Add columns if they don't exist
    try:
        c.execute('ALTER TABLE resume_evaluations ADD COLUMN human_label TEXT')
    except sqlite3.OperationalError:
        pass 
        
    try:
        c.execute('ALTER TABLE resume_evaluations ADD COLUMN is_training_data BOOLEAN DEFAULT 0')
    except sqlite3.OperationalError:
        pass

    try:
        c.execute('ALTER TABLE resume_evaluations ADD COLUMN admin_corrected_json TEXT')
    except sqlite3.OperationalError:
        pass

    try:
        from core.config import Config

        admin_count = c.execute('SELECT COUNT(*) AS count FROM admins').fetchone()['count']
        if admin_count == 0 and Config.ADMIN_PASSWORD_HASH:
            c.execute('''
                INSERT INTO admins (
                    id, username, password_hash, role, created_at, last_login
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                str(uuid.uuid4()),
                Config.ADMIN_USERNAME,
                Config.ADMIN_PASSWORD_HASH,
                'admin',
                datetime.now(),
                None,
            ))
    except Exception:
        pass
    
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

def save_evaluation(data: Dict[str, Any]):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Check if column exists, if not handled by init
    try:
        c.execute('''
            INSERT INTO resume_evaluations (
                id, uploaded_at, candidate_name, vendor_name, resume_filename_original,
                resume_path, page_count, checklist_version_id, rules_score, llm_score,
                overall_score, rule_violations_json, section_scores_json, improvements_json,
                llm_output_json, model_name, prompt_version, human_label, is_training_data, admin_corrected_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['id'],
            data['uploaded_at'],
            data['candidate_name'],
            data['vendor_name'],
            data['filename'],
            data['file_path'],
            data.get('page_count', 0),
            data.get('checklist_version_id'),
            data.get('rules_score', 0.0),
            data.get('llm_score', 0.0),
            data.get('overall_score', 0.0),
            json.dumps(data.get('rule_violations', [])),
            json.dumps(data.get('section_scores', {})),
            json.dumps(data.get('improvements', [])),
            json.dumps(data.get('llm_output', {})),
            data.get('model_name'),
            data.get('prompt_version'),
            data.get('human_label'),
            data.get('is_training_data', False),
            json.dumps(data.get('admin_corrected', {})) if data.get('admin_corrected') else None
        ))
    except sqlite3.OperationalError:
         # Fallback for old schema if migration failed or mostly just ensuring insert works
         pass

    conn.commit()
    conn.close()

def update_human_label(submission_id: str, label: str):
    conn = get_db_connection()
    conn.execute('UPDATE resume_evaluations SET human_label = ? WHERE id = ?', (label, submission_id))
    conn.commit()
    conn.close()

def update_training_correction(submission_id: str, corrected_json: Dict):
    conn = get_db_connection()
    conn.execute('UPDATE resume_evaluations SET admin_corrected_json = ? WHERE id = ?', (json.dumps(corrected_json), submission_id))
    conn.commit()
    conn.close()

def get_all_submissions():
    conn = get_db_connection()
    submissions = conn.execute('SELECT * FROM resume_evaluations ORDER BY uploaded_at DESC').fetchall()
    conn.close()
    return [dict(s) for s in submissions]

def get_all_training_data():
    conn = get_db_connection()
    submissions = conn.execute('SELECT * FROM resume_evaluations WHERE is_training_data = 1 ORDER BY uploaded_at DESC').fetchall()
    conn.close()
    return [dict(s) for s in submissions]

def get_submission_by_id(submission_id):
    conn = get_db_connection()
    submission = conn.execute('SELECT * FROM resume_evaluations WHERE id = ?', (submission_id,)).fetchone()
    conn.close()
    return dict(submission) if submission else None

def delete_submission(submission_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM resume_evaluations WHERE id = ?', (submission_id,))
    conn.commit()
    conn.close()

def get_training_examples() -> Dict[str, List[Dict]]:
    """
    Fetches training examples.
    Priority 1: Explicitly supervised 'Model Builder' data (is_training_data=1 AND admin_corrected_json is not null).
    Priority 2: Labeled data (Good/Worst).
    """
    conn = get_db_connection()
    examples = {"Good": [], "Worst": [], "Supervised": []}
    
    try:
        # 1. Fetch Supervised Training Data (The Gold Standard)
        rows_supervised = conn.execute("SELECT * FROM resume_evaluations WHERE is_training_data = 1 AND admin_corrected_json IS NOT NULL ORDER BY uploaded_at DESC LIMIT 5").fetchall()
        examples["Supervised"] = [dict(r) for r in rows_supervised]

        # 2. Fetch Good (Fallback/Supplement)
        rows_good = conn.execute("SELECT * FROM resume_evaluations WHERE human_label = 'Good' AND is_training_data = 0 ORDER BY uploaded_at DESC LIMIT 3").fetchall()
        examples["Good"] = [dict(r) for r in rows_good]
        
        # 3. Fetch Worst
        rows_bad = conn.execute("SELECT * FROM resume_evaluations WHERE human_label = 'Worst' AND is_training_data = 0 ORDER BY uploaded_at DESC LIMIT 3").fetchall()
        examples["Worst"] = [dict(r) for r in rows_bad]
    except Exception as e:
        print(f"Error fetching training examples: {e}")
        
    conn.close()
    return examples

def save_checklist_version(google_doc_id: str, rules: List[Dict], content_hash: str):
    conn = get_db_connection()
    try:
        # Deactivate all previous versions
        conn.execute('UPDATE checklist_versions SET is_active = 0')
        
        # Insert new version
        new_id = f"v_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        conn.execute('''
            INSERT INTO checklist_versions (
                id, google_doc_id, version, rules_json, hash, created_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            new_id,
            google_doc_id,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            json.dumps(rules),
            content_hash,
            datetime.now(),
            True
        ))
        conn.commit()
    finally:
        conn.close()

def get_latest_checklist_version() -> Optional[Dict]:
    conn = get_db_connection()
    try:
        row = conn.execute('SELECT * FROM checklist_versions WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1').fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

# Initialize database automatically so it works on Streamlit Cloud
init_db()
