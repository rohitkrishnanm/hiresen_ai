import requests
import hashlib
import re
import json
from datetime import datetime
from typing import Dict, Any, List

# Adjust import based on execution context
try:
    from core.config import Config
except ImportError:
    import sys
    sys.path.append('..')
    from core.config import Config

class GoogleDocParser:
    def __init__(self):
        self.url = Config.GOOGLE_DOC_URL

    def fetch_and_parse(self) -> Dict[str, Any]:
        """
        Fetches the public Google Doc text export and parses it into strict rules.
        Returns a dict containing 'version_hash', 'rules', 'raw_text'.
        """
        if not self.url:
            raise ValueError("GOOGLE_DOC_ID not configured.")

        try:
            response = requests.get(self.url)
            response.raise_for_status()
            text_content = response.text
            
            # Remove BOM if present
            if text_content.startswith('\ufeff'):
                text_content = text_content[1:]
                
            rules = self._parse_text_to_rules(text_content)
            content_hash = hashlib.md5(text_content.encode('utf-8')).hexdigest()
            
            return {
                "hash": content_hash,
                "rules": rules,
                "raw_text": text_content,
                "fetched_at": datetime.now().isoformat()
            }
            
        except requests.RequestException as e:
            print(f"Error fetching doc: {e}")
            return None

    def _parse_text_to_rules(self, text: str) -> List[Dict[str, Any]]:
        """
        Parses the specific 'Vision Board' checklist format into executable rules.
        """
        rules_config = []
        text_upper = text.upper()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        
        # 1. Mandatory Sections (With Aliases)
        # Map specific doc headers to broad resume synonyms
        section_aliases = {
            "PROFESSIONAL PROFILE PHOTO": [], # Hard to check text for photo
            "PERSONAL DETAILS": ["PERSONAL", "CONTACT", "DETAILS", "INFO"],
            "PROFESSIONAL SUMMARY": ["SUMMARY", "PROFILE", "OBJECTIVE", "ABOUT"],
            "SKILLSET": ["SKILLS", "TECHNICAL SKILLS", "COMPETENCIES", "STACK"],
            "WORK EXPERIENCE": ["EXPERIENCE", "WORK HISTORY", "EMPLOYMENT"],
            "CERTIFICATIONS": ["CERTIFICATIONS", "CREDENTIALS"],
            "EDUCATION": ["EDUCATION", "ACADEMIC", "QUALIFICATIONS"]
        }
        
        found_sections = []
        
        # Scan doc for these headers to see which ones are required
        # If doc says "SKILLSET", we require any of ["SKILLS", "TECHNICAL SKILLS"...]
        for doc_header, keywords in section_aliases.items():
            if any(doc_header in line.upper() for line in lines):
                if not keywords: continue # Skip photo check for text parser
                found_sections.append({
                    "name": doc_header,
                    "aliases": keywords + [doc_header] # Include the term itself
                })

        if found_sections:
            rules_config.append({
                "id": "R002_MANDATORY_SECTIONS",
                "type": "section_presence",
                "target": "text_content",
                "required_sections": found_sections,
                "description": f"Resume must contain standard sections (Summary, Skills, Experience, etc.)"
            })

        # 2. Filename Rule
        filename_match = re.search(r"RENAME THE FILE AS\s+(.+)", text, re.IGNORECASE)
        if filename_match:
            fmt = filename_match.group(1).strip()
            # Convert "RESUME AZURE DATA ENGINEER_NAME" -> Regex
            # Allow case insensitive, spaces can be underscores or spaces
            clean_fmt = re.escape(fmt).replace("_NAME", r".*") 
            # Replace literal spaces with \s+ to allow "AZURE DATA" or "AZURE_DATA" check flexibility if needed, 
            # but usually filename matching is strict on structure.
            # Let's keep it strict but allow case flags in engine.
            pattern = "^" + clean_fmt.replace(r"\ ", r"[\s_]+") + r"(\.pdf)?$"
            
            rules_config.append({
                "id": "R001_FILENAME",
                "type": "regex_match",
                "target": "filename",
                "pattern": pattern,
                "description": f"Filename must match format: {fmt}"
            })

        # 3. Keywords
        kw_match = re.search(r"KEYWORDS.+?\(([^)]+)\)", text, re.IGNORECASE | re.DOTALL)
        keywords = []
        if kw_match:
            raw_kws = kw_match.group(1)
            # Remove noise words specific to this doc using Regex for variable spacing
            # "YEARS OF    EXPERIENCE"
            noise_patterns = [
                r"YEARS\s+OF\s+EXPERIENCE",
                r"SKILLS\s+LIKE",
                r"SHOULD\s+BE\s+HIGHLIGHTED",
                r"\bAND\b"
            ]
            
            cleaned_str = raw_kws.upper()
            for pat in noise_patterns:
                cleaned_str = re.sub(pat, ",", cleaned_str, flags=re.IGNORECASE)
            
            # Split and cleanup
            for k in cleaned_str.split(','):
                k = k.strip()
                # Remove internal whitespace to single space
                k = re.sub(r'\s+', ' ', k)
                if len(k) < 2: continue
                
                # Fix "AZURE DATA ENG" mapping
                if k == "AZURE DATA ENG":
                    keywords.append("AZURE DATA")
                else:
                    keywords.append(k.lower())
            
            if keywords:
                rules_config.append({
                    "id": "R004_MANDATORY_KEYWORDS",
                    "type": "keyword_presence",
                    "target": "text_content",
                    "keywords": list(set(keywords)), # Dedup
                    "description": f"Must contain keywords: {', '.join(keywords)}"
                })

        # 4. Certifications
        cert_section_match = re.search(r"CERTIFICATIONS(.+?)EDUCATION", text_upper, re.DOTALL)
        if cert_section_match:
            cert_block = cert_section_match.group(1)
            certs = [line.strip().lower() for line in cert_block.split('\n') if line.strip() and len(line.strip()) > 2]
            certs = [re.sub(r"^[-*\d.\s]+", "", cert).strip() for cert in certs]
            certs = [cert for cert in certs if cert]
            if certs:
                rules_config.append({
                    "id": "R006_CERTIFICATIONS",
                    "type": "keyword_any",
                    "target": "text_content",
                    "keywords": certs,
                    "description": f"Should contain at least one certification: {', '.join(certs)}"
                })
        
        if "3 PAGE" in text_upper:
            max_p = 3
        elif "2 PAGE" in text_upper:
            max_p = 2
        else:
            max_p = 2
            
        rules_config.append({
             "id": "R005_PAGE_COUNT",
             "type": "range",
             "target": "page_count",
             "min": 1,
             "max": max_p,
             "description": f"Resume should be between 1 and {max_p} pages."
        })

        # 6. Specific Role Title
        role_match = re.search(r"MENTION YOUR ROLE AS\s+([^.\n]+)", text, re.IGNORECASE)
        if role_match:
            role_title = role_match.group(1).strip()
            # Clean " IN YOUR CURRENT COMPANY..."
            role_title = role_title.split(" IN ")[0].strip()
            
            rules_config.append({
                "id": "R007_ROLE_TITLE",
                "type": "role_title",
                "target": "sections.experience",
                "title": role_title,
                "description": f"Must explicitly mention role: {role_title}"
            })

        # 7. Min Points
        points_match = re.search(r"MIN\s+(\d+)\s+POINTS", text, re.IGNORECASE)
        if points_match:
            min_pts = int(points_match.group(1))
            rules_config.append({
                "id": "R008_DETAIL_DEPTH",
                "type": "bullet_count",
                "target": "sections.experience",
                "min": min_pts,
                "description": f"Work Experience must contain at least {min_pts} detailed points/sentences."
            })

        # 8. Highlighted Keywords
        # Reuse keywords list from earlier if "HIGHLIGHT" instruction is present
        highlight_instr = re.search(r"HIGHLIGHT.+?KEYWORDS", text, re.IGNORECASE)
        if highlight_instr and keywords:
             rules_config.append({
                "id": "R009_HIGHLIGHT_CHECK",
                "type": "highlighted_keywords",
                "target": "highlighted_tokens",
                "keywords": list(set(keywords)),
                "description": "Critical keywords must be visually highlighted (Bold or CAPS)."
            })

        return rules_config

if __name__ == "__main__":
    # Test
    # p = GoogleDocParser()
    # print(json.dumps(p.fetch_and_parse(), indent=2))
    pass
