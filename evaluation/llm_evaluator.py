import json
from openai import OpenAI
from typing import Dict, Any, Optional

# Adjust imports for execution context
try:
    from core.config import Config
    from core.models import LLMOutput
    from core.db import get_training_examples
except ImportError:
    import sys
    sys.path.append('..')
    from core.config import Config
    from core.models import LLMOutput
    from core.db import get_training_examples

class LLMEvaluator:
    def __init__(self):
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        self.model = Config.MODEL_NAME

    def _coerce_output(self, data: Dict[str, Any]) -> LLMOutput:
        defaults = {
            "analysis": "",
            "section_scores": {},
            "quality_score": 0.0,
            "strengths": [],
            "gaps": [],
            "improvements": [],
            "rewrite_suggestions": {},
        }
        merged = {**defaults, **data}
        return LLMOutput(**merged)

    def evaluate(self, parsed_resume: Dict[str, Any]) -> LLMOutput:
        """
        Sends resume content to LLM for qualitative analysis.
        """
        if not Config.OPENAI_API_KEY:
             # Return dummy data if no key (for testing/dev without cost)
             return self._get_dummy_output()

        # --- Fetch Training Examples (Few-Shot) ---
        training_data = get_training_examples()
        few_shot_context = ""
        
        # 1. High Priority: Supervised "Model Builder" Data
        if training_data.get('Supervised'):
             few_shot_context += "\n\n### GOLD STANDARD EXAMPLES (STRICTLY MIMIC THESE SCORES):\n"
             for ex in training_data['Supervised']:
                 # Use the Corrected JSON which has the Admin's "Weights" and Logic
                 corrected_output = ex.get('admin_corrected_json')
                 few_shot_context += f"\n[PERFECT EXAMPLE]\nInput Resume: {ex['candidate_name']}\nTarget Output: {corrected_output}\n"

        # 2. Fallback: Labeled Data
        elif training_data.get('Good') or training_data.get('Worst'):
            few_shot_context += "\n\n### REFERENCE EXAMPLES (LEARN FROM THESE):\n"
            
            for ex in training_data['Good']:
                snippet = ex['section_scores_json'] 
                few_shot_context += f"\n[GOOD EXAMPLE - MIMIC THIS STANDARD]\nInput: {ex['candidate_name']}\nExpected Quality: High\nOutput Scores: {snippet}\n"
                
            for ex in training_data['Worst']:
                snippet = ex['section_scores_json']
                few_shot_context += f"\n[BAD EXAMPLE - AVOID THESE MISTAKES]\nInput: {ex['candidate_name']}\nExpected Quality: Low (Fail)\nOutput Scores: {snippet}\n"
        
        system_prompt = f"""
        You are a strict, senior technical recruiter and hiring manager for Azure Data Engineer roles.
        Evaluate the candidate's resume against industry standards and high-bar expectations.
        Prioritize depth and accuracy over speed. Take the time needed to review the resume carefully.
        Read all available resume content before scoring. Do not rush or guess missing details.
        Treat this as a quality-only evaluation where completeness is more important than latency.
        {few_shot_context}
        
        Your Output MUST be valid JSON with the following structure:
        {{
            "analysis": "Write a complete comprehensive step-by-step analysis of the entire resume. Cover summary, experience, skills, education, certifications, and formatting quality before giving any feedback.",
            "section_scores": {{"Summary": 0-10, "Experience": 0-10, "Skills": 0-10}},
            "quality_score": 0-10,
            "strengths": ["list", "of", "strong", "points"],
            "gaps": ["list", "of", "missing", "or", "weak", "areas"],
            "improvements": [
                {{"section": "Summary", "issue": "Too generic", "suggestion": "Add metrics...", "priority": "High"}}
            ],
            "rewrite_suggestions": {{
                "Summary": "Better version..."
            }}
        }}
        """

        sections_payload = parsed_resume.get('sections', {}) or {}
        text_payload = parsed_resume.get('text_content', '') or parsed_resume.get('text', '')
        if text_payload and len(text_payload) > 12000:
            text_payload = text_payload[:12000] + "\n--TRUNCATED FOR CONTEXT WINDOW--"

        user_message = f"""
        Analyze this resume for an Azure Data Engineer position.
        Spend the necessary time to assess it fully and carefully.
        Review every visible section and infer only what is clearly supported by the resume.
        
        RESUME CONTENT:
        {json.dumps(sections_payload)}
        
        FULL TEXT:
        {text_payload}
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=2800
            )
            
            content = response.choices[0].message.content
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("LLM response was not a JSON object")

            return self._coerce_output(data)

        except Exception as e:
            print(f"LLM Evaluation Error: {e}")
            return self._get_dummy_output()

    def _get_dummy_output(self) -> LLMOutput:
        return self._coerce_output({
            "analysis": "Offline fallback output was used because no OpenAI key is configured or the request failed.",
            "section_scores": {"Summary": 5, "Experience": 5, "Skills": 5},
            "quality_score": 5.0,
            "strengths": ["Placeholder strength"],
            "gaps": ["API key missing or error occurred"],
            "improvements": [],
            "rewrite_suggestions": {},
        })
