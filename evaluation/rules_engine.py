import re
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from core.db import get_latest_checklist_version

@dataclass
class RuleResult:
    rule_id: str
    passed: bool
    violation_message: Optional[str] = None


# ── Hardcoded fallback rules based on Vision Board checklist ──────────────────
HARDCODED_RULES = [
    {
        "id": "R001_FILENAME",
        "type": "regex_match",
        "target": "filename",
        "pattern": r"^RESUME[\s_]+AZURE[\s_]+DATA[\s_]+ENGINEER[\s_]+.+(\.(pdf|docx|PDF|DOCX))?$",
        "description": "Filename must match format: RESUME AZURE DATA ENGINEER_NAME"
    },
    {
        "id": "R002_MANDATORY_SECTIONS",
        "type": "section_presence",
        "target": "text_content",
        "required_sections": [
            {"name": "PROFESSIONAL SUMMARY", "aliases": ["SUMMARY", "PROFILE", "OBJECTIVE", "ABOUT ME"]},
            {"name": "SKILLSET",             "aliases": ["SKILLS", "TECHNICAL SKILLS", "COMPETENCIES", "CORE COMPETENCIES"]},
            {"name": "WORK EXPERIENCE",      "aliases": ["EXPERIENCE", "WORK HISTORY", "EMPLOYMENT", "PROFESSIONAL EXPERIENCE"]},
            {"name": "CERTIFICATIONS",       "aliases": ["CERTIFICATIONS", "CERTIFICATION", "CREDENTIALS", "CERTIFICATES"]},
            {"name": "EDUCATION",            "aliases": ["EDUCATION", "ACADEMIC", "QUALIFICATIONS", "ACADEMICS"]},
            {"name": "PERSONAL DETAILS",     "aliases": ["PERSONAL", "CONTACT", "DETAILS", "CONTACT INFO", "PERSONAL INFO"]},
        ],
        "description": "Resume must contain: Summary, Skills, Experience, Certifications, Education, Contact Details"
    },
    {
        "id": "R003_CONTACT_INFO",
        "type": "multi_keyword_any",
        "target": "text_content",
        "groups": [
            {"name": "Email",    "keywords": ["@gmail", "@yahoo", "@outlook", "@hotmail", ".com", "@"]},
            {"name": "Phone",    "keywords": ["+91", "+1", "mobile", "phone", "cell"]},
            {"name": "LinkedIn", "keywords": ["linkedin.com", "linkedin", "linked in"]},
        ],
        "description": "Resume must include Email, Phone number, and LinkedIn profile link"
    },
    {
        "id": "R004_MANDATORY_KEYWORDS",
        "type": "keyword_presence",
        "target": "text_content",
        "keywords": ["azure", "sql", "python", "pyspark", "databricks"],
        "description": "Resume must contain core Azure Data Engineer keywords: Azure, SQL, Python, PySpark, Databricks"
    },
    {
        "id": "R005_ROLE_TITLE",
        "type": "keyword_any",
        "target": "text_content",
        "keywords": ["azure data engineer", "data engineer"],
        "description": "Must explicitly mention the role: Azure Data Engineer"
    },
    {
        "id": "R006_CERTIFICATIONS",
        "type": "keyword_any",
        "target": "text_content",
        "keywords": [
            "dp-900", "dp 900", "azure data fundamentals", "microsoft azure data fundamentals",
            "dp-700", "dp 700", "fabric data engineer", "microsoft fabric data engineer associate",
            "databricks certified", "databricks associate", "databricks certified data engineer associate",
            "databricks fundamentals", "lakehouse fundamentals", "databricks lakehouse fundamentals",
            "databricks genai", "generative ai fundamentals", "databricks genai fundamental", "databricks generative ai fundamentals",
            "dp-900/microsoft azure data fundamentals",
            "dp-700/microsoft fabric data engineer associate",
            "databricks certified data engineer associate/databricks certified data engineer associate",
            "databricks fundamentals/databricks lakehouse fundamentals",
            "databricks genai fundamental/databricks generative ai fundamentals"
        ],
        "description": "Must contain at least one relevant certification (DP-900, DP-700, Databricks, etc.)"
    },
    {
        "id": "R007_EXPERIENCE_DETAIL",
        "type": "bullet_count",
        "target": "sections.experience",
        "min": 10,
        "description": "Work Experience must contain at least 10 detailed bullet points / responsibilities"
    },
    {
        "id": "R008_ADF_MENTIONED",
        "type": "keyword_any",
        "target": "text_content",
        "keywords": ["adf", "azure data factory", "data factory"],
        "description": "Azure Data Factory (ADF) should be mentioned in the resume"
    },
    {
        "id": "R009_PAGE_COUNT",
        "type": "range",
        "target": "page_count",
        "min": 1,
        "max": 3,
        "description": "Resume should be 1-3 pages (1pg: 0-5yrs, 2pg: 5-10yrs, 3pg: 10+yrs)"
    },
]


class RulesEngine:
    def __init__(self, rules: List[Dict] = None):
        if rules is not None:
            self.rules = rules
            self.version_id = None
        else:
            # 1. Try Supabase DB for synced rules
            checklist_data = get_latest_checklist_version()
            if checklist_data and checklist_data.get('rules_json'):
                try:
                    db_rules = json.loads(checklist_data['rules_json'])
                    if db_rules:
                        self.rules = db_rules
                        self.version_id = checklist_data['id']
                        print(f"Rules Engine: Loaded {len(self.rules)} rules from Supabase (version: {self.version_id})")
                        return
                except Exception:
                    pass

            # 2. Try fetching live from Google Docs
            try:
                from checklist.parser_google_doc import GoogleDocParser
                from core.config import Config
                if Config.GOOGLE_DOC_ID:
                    parser = GoogleDocParser()
                    result = parser.fetch_and_parse()
                    if result and result.get("rules"):
                        self.rules = result["rules"]
                        self.version_id = "live_from_google_doc"
                        print(f"Rules Engine: Loaded {len(self.rules)} rules live from Google Docs")
                        return
            except Exception as e:
                print(f"Rules Engine: Could not fetch from Google Docs: {e}")

            # 3. Use hardcoded fallback rules
            print("Rules Engine: Using hardcoded Vision Board checklist rules (fallback).")
            self.rules = HARDCODED_RULES
            self.version_id = "hardcoded_v1"

    def evaluate(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        violations = []
        checklist_scan = []
        total_rules = len(self.rules)
        rule_scores = 0

        full_text = parsed_data.get("text_content", "") or parsed_data.get("text", "")
        full_text_upper = full_text.upper()

        def contains_phrase(needle: str) -> bool:
            normalized = needle.upper().strip()
            if not normalized:
                return False
            if " " in normalized:
                return normalized in full_text_upper
            return re.search(rf"\b{re.escape(normalized)}\b", full_text_upper) is not None

        for rule in self.rules:
            is_violation = False
            violation_msg = ""
            rule_id = rule.get('id', 'UNKNOWN')
            rule_desc = rule.get('description', 'No description available')

            # 1. Regex Match (Filename)
            if rule['type'] == 'regex_match':
                target_val = parsed_data.get(rule['target'], "")
                if not re.search(rule['pattern'], target_val, re.IGNORECASE):
                    is_violation = True
                    violation_msg = f"{rule['description']} — Found: '{target_val}'"

            # 2. Section Presence
            elif rule['type'] == 'section_presence':
                missing_sections = []
                for sec_def in rule['required_sections']:
                    aliases = sec_def.get('aliases', [sec_def.get('name')])
                    found_alias = any(alias.upper() in full_text_upper for alias in aliases)
                    if not found_alias:
                        missing_sections.append(sec_def['name'])
                if missing_sections:
                    is_violation = True
                    violation_msg = f"Missing sections: {', '.join(missing_sections)}"

            # 3. Keyword Presence (ALL required)
            elif rule['type'] == 'keyword_presence':
                missing_kws = [kw for kw in rule['keywords'] if not contains_phrase(kw)]
                if missing_kws:
                    is_violation = True
                    violation_msg = f"Missing mandatory keywords: {', '.join(missing_kws)}"

            # 4. Keyword Any (at least one)
            elif rule['type'] == 'keyword_any':
                found_one = any(contains_phrase(kw) for kw in rule['keywords'])
                if not found_one:
                    is_violation = True
                    violation_msg = rule['description']

            # 5. Multi-keyword groups (each group must have at least one match)
            elif rule['type'] == 'multi_keyword_any':
                missing_groups = []
                for group in rule.get('groups', []):
                    found = any(kw.upper() in full_text_upper for kw in group['keywords'])
                    if not found:
                        missing_groups.append(group['name'])
                if missing_groups:
                    is_violation = True
                    violation_msg = f"Missing contact info: {', '.join(missing_groups)}"

            # 6. Numeric Range (Page Count)
            elif rule['type'] == 'range':
                val = parsed_data.get(rule['target'], 0)
                mn = rule.get('min', 0)
                mx = rule.get('max', 999)
                if not (mn <= val <= mx):
                    is_violation = True
                    violation_msg = f"Page count is {val} — expected between {mn} and {mx}"

            # 7. Bullet Point Count
            elif rule['type'] == 'bullet_count':
                exp_text = parsed_data.get("sections", {}).get("experience", "")
                if not exp_text:
                    count = 0
                else:
                    sentences = [s for s in re.split(r'[.!?•\n]', exp_text) if len(s.strip()) > 10]
                    count = len(sentences)
                if count < rule['min']:
                    is_violation = True
                    violation_msg = f"Only ~{count} bullet points found in Experience — need at least {rule['min']}"

            # 8. Highlighted Keywords
            elif rule['type'] == 'highlighted_keywords':
                highlighted_set = set(parsed_data.get('highlighted_tokens', []))
                missing_highlights = []
                for kw in rule['keywords']:
                    found = any(kw.lower() in h_tok for h_tok in highlighted_set)
                    if not found:
                        missing_highlights.append(kw)
                if missing_highlights:
                    is_violation = True
                    violation_msg = f"Keywords not highlighted (Bold/Caps): {', '.join(missing_highlights)}"

            else:
                is_violation = True
                violation_msg = f"Unsupported rule type: {rule.get('type', 'unknown')}"

            # Aggregate results
            if is_violation:
                violations.append({
                    "rule_id": rule_id,
                    "violation_message": violation_msg,
                    "criticality": "high"
                })
                checklist_scan.append({
                    "rule_id": rule_id,
                    "description": rule_desc,
                    "status": "FAIL",
                    "details": violation_msg,
                })
            else:
                rule_scores += 1
                checklist_scan.append({
                    "rule_id": rule_id,
                    "description": rule_desc,
                    "status": "PASS",
                    "details": "Rule passed",
                })

        final_score = (rule_scores / total_rules * 100) if total_rules > 0 else 100.0

        return {
            "score": round(final_score, 1),
            "violations": violations,
            "checklist_scan": checklist_scan,
            "checklist_version_id": self.version_id
        }
