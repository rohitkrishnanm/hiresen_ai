from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

# --- Rules Engine Models ---

class RuleResult(BaseModel):
    rule_id: str
    passed: bool
    evidence: Optional[str] = None
    violation_message: Optional[str] = None

class RulesOutput(BaseModel):
    score: float
    violations: List[RuleResult]
    passed_rules: List[RuleResult]
    details: Dict[str, Any]

# --- LLM Evaluation Models ---

class QualityImprovement(BaseModel):
    section: str
    issue: str
    suggestion: str
    priority: str # High, Medium, Low

class LLMOutput(BaseModel):
    analysis: Optional[str] = None
    section_scores: Dict[str, float]
    quality_score: float
    strengths: List[str]
    gaps: List[str]
    improvements: List[QualityImprovement]
    rewrite_suggestions: Dict[str, str]

# --- Resume Parsing Models ---

class ResumeSection(BaseModel):
    name: str # Summary, Experience, etc.
    content: str

class ParsedResume(BaseModel):
    filename: str
    page_count: int
    text_content: str
    sections: Dict[str, str] # Key: Section Name, Value: Content

# --- DB/Submission Models ---

class SubmissionMetadata(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_name: str
    vendor_name: str
    uploaded_at: datetime = Field(default_factory=datetime.now)
    filename: str
    file_path: str
    
class EvaluationResult(BaseModel):
    submission_id: str
    rules_result: RulesOutput
    llm_result: LLMOutput
    overall_score: float
    checklist_version: str
    model_name: str
    model_config = {'protected_namespaces': ()}
