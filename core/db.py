import json
import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from core.config import Config

def get_supabase_client() -> Client:
    if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env or secrets")
    return create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)


def get_admin_by_username(username: str) -> Optional[Dict[str, Any]]:
    supabase = get_supabase_client()
    response = supabase.table('admins').select('*').eq('username', username).execute()
    return response.data[0] if response.data else None


def update_admin_last_login(username: str):
    supabase = get_supabase_client()
    supabase.table('admins').update({'last_login': datetime.now().isoformat()}).eq('username', username).execute()


def init_db():
    # Supabase initialization happens via the SQL editor in the dashboard.
    # We will just verify if the admin user exists.
    try:
        supabase = get_supabase_client()
        response = supabase.table('admins').select('*').execute()
        if not response.data and Config.ADMIN_PASSWORD_HASH:
            supabase.table('admins').insert({
                'id': str(uuid.uuid4()),
                'username': Config.ADMIN_USERNAME,
                'password_hash': Config.ADMIN_PASSWORD_HASH,
                'role': 'admin',
                'created_at': datetime.now().isoformat(),
                'last_login': None
            }).execute()
            print("Default admin created in Supabase.")
    except Exception as e:
        print(f"Skipping admin init (maybe tables not created yet): {e}")


def save_evaluation(data: Dict[str, Any]):
    supabase = get_supabase_client()
    payload = {
        'id': data['id'],
        'uploaded_at': data['uploaded_at'].isoformat() if isinstance(data['uploaded_at'], datetime) else data['uploaded_at'],
        'candidate_name': data['candidate_name'],
        'vendor_name': data['vendor_name'],
        'resume_filename_original': data['filename'],
        'resume_path': data['file_path'],
        'page_count': data.get('page_count', 0),
        'checklist_version_id': data.get('checklist_version_id'),
        'rules_score': data.get('rules_score', 0.0),
        'llm_score': data.get('llm_score', 0.0),
        'overall_score': data.get('overall_score', 0.0),
        'rule_violations_json': json.dumps(data.get('rule_violations', [])),
        'section_scores_json': json.dumps(data.get('section_scores', {})),
        'improvements_json': json.dumps(data.get('improvements', [])),
        'llm_output_json': json.dumps(data.get('llm_output', {})),
        'model_name': data.get('model_name'),
        'prompt_version': data.get('prompt_version'),
        'human_label': data.get('human_label'),
        'is_training_data': data.get('is_training_data', False),
        'admin_corrected_json': json.dumps(data.get('admin_corrected', {})) if data.get('admin_corrected') else None
    }
    
    try:
        supabase.table('resume_evaluations').insert(payload).execute()
    except Exception as e:
        print(f"Error saving to Supabase: {e}")


def update_human_label(submission_id: str, label: str):
    supabase = get_supabase_client()
    supabase.table('resume_evaluations').update({'human_label': label}).eq('id', submission_id).execute()


def update_training_correction(submission_id: str, corrected_json: Dict):
    supabase = get_supabase_client()
    supabase.table('resume_evaluations').update({
        'admin_corrected_json': json.dumps(corrected_json)
    }).eq('id', submission_id).execute()


def get_all_submissions() -> List[Dict]:
    supabase = get_supabase_client()
    response = supabase.table('resume_evaluations').select('*').order('uploaded_at', desc=True).execute()
    return response.data if response.data else []


def get_all_training_data() -> List[Dict]:
    supabase = get_supabase_client()
    response = supabase.table('resume_evaluations').select('*').eq('is_training_data', True).order('uploaded_at', desc=True).execute()
    return response.data if response.data else []


def get_submission_by_id(submission_id: str) -> Optional[Dict]:
    supabase = get_supabase_client()
    response = supabase.table('resume_evaluations').select('*').eq('id', submission_id).execute()
    return response.data[0] if response.data else None


def delete_submission(submission_id: str):
    supabase = get_supabase_client()
    supabase.table('resume_evaluations').delete().eq('id', submission_id).execute()


def get_training_examples() -> Dict[str, List[Dict]]:
    supabase = get_supabase_client()
    examples = {"Good": [], "Worst": [], "Supervised": []}
    
    try:
        # 1. Fetch Supervised Training Data
        resp1 = supabase.table('resume_evaluations').select('*').eq('is_training_data', True).not_.is_('admin_corrected_json', 'null').order('uploaded_at', desc=True).limit(5).execute()
        examples["Supervised"] = resp1.data if resp1.data else []

        # 2. Fetch Good (Fallback)
        resp2 = supabase.table('resume_evaluations').select('*').eq('human_label', 'Good').eq('is_training_data', False).order('uploaded_at', desc=True).limit(3).execute()
        examples["Good"] = resp2.data if resp2.data else []
        
        # 3. Fetch Worst
        resp3 = supabase.table('resume_evaluations').select('*').eq('human_label', 'Worst').eq('is_training_data', False).order('uploaded_at', desc=True).limit(3).execute()
        examples["Worst"] = resp3.data if resp3.data else []
    except Exception as e:
        print(f"Error fetching training examples: {e}")
        
    return examples


def save_checklist_version(google_doc_id: str, rules: List[Dict], content_hash: str):
    supabase = get_supabase_client()
    try:
        # Deactivate previous versions
        supabase.table('checklist_versions').update({'is_active': False}).neq('id', 'placeholder').execute()
        
        new_id = f"v_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        payload = {
            'id': new_id,
            'google_doc_id': google_doc_id,
            'version': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'rules_json': json.dumps(rules),
            'hash': content_hash,
            'created_at': datetime.now().isoformat(),
            'is_active': True
        }
        supabase.table('checklist_versions').insert(payload).execute()
    except Exception as e:
        print(f"Error saving checklist version: {e}")


def get_latest_checklist_version() -> Optional[Dict]:
    supabase = get_supabase_client()
    try:
        response = supabase.table('checklist_versions').select('*').eq('is_active', True).order('created_at', desc=True).limit(1).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        return None

# Attempt to initialize default admin if not exists
init_db()
