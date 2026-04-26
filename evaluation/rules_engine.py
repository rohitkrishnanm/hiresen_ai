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

class RulesEngine:
    def __init__(self, rules: List[Dict] = None):
        if rules is not None:
             self.rules = rules
             self.version_id = None # Manual override, version unknown
        else:
            # Fetch active rules from DB
            checklist_data = get_latest_checklist_version()
            if checklist_data and checklist_data.get('rules_json'):
                self.rules = json.loads(checklist_data['rules_json'])
                self.version_id = checklist_data['id']
            else:
                # Fallback (or empty) if no sync yet
                print("Warning: No active checklist found. Using default empty rules.")
                self.rules = []
                self.version_id = None

    def evaluate(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs the parsing data against the active rules configurations.
        """
        violations = []
        checklist_scan = []
        total_rules = len(self.rules)
        rule_scores = 0
        
        full_text = parsed_data.get("text_content", "") or parsed_data.get("text", "")
        full_text_upper = full_text.upper()

        def contains_phrase(needle: str) -> bool:
            normalized_needle = needle.upper().strip()
            if not normalized_needle:
                return False
            if " " in normalized_needle:
                return normalized_needle in full_text_upper
            return re.search(rf"\b{re.escape(normalized_needle)}\b", full_text_upper) is not None

        for rule in self.rules:
            is_violation = False
            violation_msg = ""
            rule_id = rule.get('id', 'UNKNOWN')
            rule_desc = rule.get('description', 'No description available')
            
            # --- Rule Type Dispatch ---
            
            # 1. Regex Match (Filename)
            if rule['type'] == 'regex_match':
                target_val = parsed_data.get(rule['target'], "")
                if not re.search(rule['pattern'], target_val, re.IGNORECASE):
                    is_violation = True
                    violation_msg = f"{rule['description']} (Found: {target_val})"

            # 2. Section Presence
            elif rule['type'] == 'section_presence':
                # Check for presence of ANY valid alias for each required section
                missing_sections = []
                for sec_def in rule['required_sections']:
                    # sec_def is eq {"name": "SUMMARY", "aliases": ["SUMMARY", "PROFILE"...]}
                    found_alias = False
                    
                    aliases = sec_def.get('aliases', [sec_def.get('name')])
                    for alias in aliases:
                        if alias.upper() in full_text_upper:
                            found_alias = True
                            break
                    
                    if not found_alias:
                        missing_sections.append(sec_def['name'])
                
                if missing_sections:
                    is_violation = True
                    violation_msg = f"Missing sections: {', '.join(missing_sections)}"

            # 3. Keyword Presence (All Required)
            elif rule['type'] == 'keyword_presence':
                missing_kws = []
                for kw in rule['keywords']:
                    if not contains_phrase(kw):
                        missing_kws.append(kw)
                
                if missing_kws:
                    is_violation = True
                    violation_msg = f"Missing mandatory keywords: {', '.join(missing_kws)}"

            # 4. Keyword Any (At least one)
            elif rule['type'] == 'keyword_any':
                found_one = False
                for kw in rule['keywords']:
                    if contains_phrase(kw):
                        found_one = True
                        break
                
                if not found_one:
                    is_violation = True
                    violation_msg = rule['description']

            # 5. Numeric Range (Page Count)
            elif rule['type'] == 'range':
                val = parsed_data.get(rule['target'], 0)
                mn = rule.get('min', 0)
                mx = rule.get('max', 999)
                if not (mn <= val <= mx):
                    is_violation = True
                    violation_msg = f"Value {val} is outside valid range {mn}-{mx}"

            # 6. Specific Role Title Presence (in Experience)
            elif rule['type'] == 'role_title':
                exp_text = parsed_data.get("sections", {}).get("experience", "").upper()
                target_role = rule['title'].upper()
                if target_role not in exp_text:
                    is_violation = True
                    violation_msg = f"Role '{rule['title']}' not found in Work Experience."

            # 7. Min Bullet Points
            elif rule['type'] == 'bullet_count':
                exp_text = parsed_data.get("sections", {}).get("experience", "")
                if not exp_text:
                     count = 0 
                else:
                    # Heuristic: Count punctuation like •, -, * or simply splitting by newline chunks if parser preserved them.
                    # Since parser normalizes, splitting by sentences or bullet chars is safer.
                    # However, typical normalization reduces newlines. Inspecting parser output, we replaced \s+ with ' '.
                    # This makes bullet counting HARD on normalized text.
                    # FIX: We should rely on "long segments" or assume parser logic needs adjustment.
                    # FALLBACK: We check if text length > X chars relative to points, or regex match bullet-like patterns.
                    # Better Regex for normalized bullets: (•|-|\*) or just look for sentence endings.
                    # Given simple normalization, let's look for known bullet chars or just rough length estimate.
                    # A better way: Count "sentences" approx.
                    sentences = [s for s in re.split(r'[.!?•\n]', exp_text) if len(s.strip()) > 10]
                    count = len(sentences)
                
                if count < rule['min']:
                    is_violation = True
                    violation_msg = f"Insufficient detail in Experience. Found approx {count} points, required {rule['min']}."

            # 8. Highlighted Keywords
            elif rule['type'] == 'highlighted_keywords':
                highlighted_set = set(parsed_data.get('highlighted_tokens', []))
                # Check which of the required keywords appear in the highlighted set
                missing_highlights = []
                for kw in rule['keywords']:
                    # Simple substring match in highlights
                    found = False
                    for h_tok in highlighted_set:
                        if kw.lower() in h_tok:
                            found = True
                            break
                    if not found:
                        missing_highlights.append(kw)
                
                if missing_highlights:
                    is_violation = True
                    violation_msg = f"Keywords not highlighted (Bold/Caps): {', '.join(missing_highlights)}"

            else:
                is_violation = True
                violation_msg = f"Unsupported rule type: {rule.get('type', 'unknown')}"

            # --- Result Aggregation ---
            if is_violation:
                violations.append({
                    "rule_id": rule_id,
                    "violation_message": violation_msg,
                    "criticality": "high" # default
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

        # Calculate Score (0-100)
        final_score = (rule_scores / total_rules * 100) if total_rules > 0 else 100.0

        return {
            "score": round(final_score, 1),
            "violations": violations,
            "checklist_scan": checklist_scan,
            "checklist_version_id": self.version_id
        }
