#!/usr/bin/env python3
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
# Defaults match inference_augmentation_flags() when env is unset
os.environ.setdefault("USE_RAG", "1")
os.environ.setdefault("USE_FEW_SHOT", "1")
import time, json, logging, tempfile, uuid, traceback, sys, re
from logging.handlers import RotatingFileHandler
from datetime import datetime
from queue import Queue
from pathlib import Path
from io import StringIO

from flask import Flask, request, jsonify, send_file, render_template_string, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Import few-shot examples and guidelines loader (loaded after logger init)
# Import RAG system (Phase 3)

# Optional model deps — keep app alive even if missing
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
except Exception:
    torch = None
    AutoTokenizer = AutoModelForCausalLM = None

# File parsing (optional; import failures must not disable unrelated parsers)
try:
    import pandas as pd
except Exception:
    pd = None
try:
    import PyPDF2
except Exception:
    PyPDF2 = None
try:
    from docx import Document
except Exception:
    Document = None

APP_HOME = os.environ.get("APP_HOME", os.getcwd())
SERVICE_LOG_DIR = os.environ.get("SERVICE_LOG_DIR", os.path.join(APP_HOME, "logs"))
Path(SERVICE_LOG_DIR).mkdir(parents=True, exist_ok=True)

_log_path = os.path.join(SERVICE_LOG_DIR, "med42_service.log")
_file_handler = RotatingFileHandler(
    _log_path,
    maxBytes=int(os.environ.get("LOG_MAX_BYTES", str(10 * 1024 * 1024))),
    backupCount=int(os.environ.get("LOG_BACKUP_COUNT", "5")),
)
_file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    handlers=[_file_handler, _stream_handler],
)
logger = logging.getLogger("vectaai")

# Initialize few-shot examples and guidelines loader
try:
    from utils.few_shot_loader import FewShotExampleLoader
    few_shot_loader = FewShotExampleLoader()
    logger.info("[OK] Few-shot examples and guidelines loaded successfully (50 examples across 10 conditions)")
except Exception as e:
    few_shot_loader = None
    logger.warning(f"⚠️ Few-shot loader not available: {e}")

# Initialize RAG system (Phase 3: Week 5-8)
try:
    from utils.rag_system import get_rag_system
    rag_system = get_rag_system()
    if rag_system and rag_system.available:
        logger.info("[OK] RAG system initialized (guideline semantic retrieval)")
    else:
        rag_system = None
        logger.info("ℹ️ RAG system not initialized (install: pip install sentence-transformers numpy)")
except Exception as e:
    rag_system = None
    logger.info(f"ℹ️ RAG system not available: {e}")

app = Flask(__name__, static_folder='static', static_url_path='/static')

_cors = os.environ.get("CORS_ORIGINS", "").strip()
if _cors:
    _origins = [o.strip() for o in _cors.split(",") if o.strip()]
    if _origins:
        CORS(app, origins=_origins, supports_credentials=True)
    else:
        CORS(app)
else:
    CORS(app)

_secret_env = os.environ.get("SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY")
if _secret_env:
    _flask_secret = _secret_env
else:
    _flask_secret = os.urandom(24)
    logger.warning(
        "SECRET_KEY not set; using ephemeral key (sessions reset on restart). Set SECRET_KEY for production."
    )

app.config.update({
    "UPLOAD_FOLDER": os.path.join(APP_HOME, "uploads"),
    "MAX_CONTENT_LENGTH": int(os.environ.get("MAX_CONTENT_LENGTH", str(50 * 1024 * 1024))),
    "SECRET_KEY": _flask_secret,
    "MAX_CONCURRENT_REQUESTS": int(os.environ.get("MAX_CONCURRENT_USERS", "10"))
})

# Register validation blueprint
try:
    from routes.validation import validation_bp
    app.register_blueprint(validation_bp)
    logger.info("[OK] Validation routes registered")
except Exception as e:
    logger.warning(f"⚠️ Validation routes not registered: {e}")

# Initialize database
try:
    from core.database import init_db
    init_db()
    logger.info("[OK] Database initialized")
except Exception as e:
    logger.warning(f"⚠️ Database initialization failed: {e}")

ALLOWED_EXT = {"txt", "pdf", "docx", "xlsx", "csv", "json"}

# Short labels for tabular "Task" column (what analysis was performed)
_ANALYSIS_TASK_LABELS = {
    "epilepsy": "Epilepsy classification (ILAE 2017)",
    "classification": "Clinical classification",
    "diagnosis": "Diagnosis support",
    "summary": "Clinical summarization",
    "extraction": "Information extraction",
    "custom": "Custom analysis",
}


def _task_column_value(analysis_type: str, user_prompt: str) -> str:
    """Human-readable task description for tabular Task column cells."""
    base = _ANALYSIS_TASK_LABELS.get(analysis_type, analysis_type.replace("_", " ").title())
    p = (user_prompt or "").strip()
    if not p:
        return base
    extra = p[:200] + ("…" if len(p) > 200 else "")
    return f"{base} — {extra}"


def parse_structured_bullets_from_analysis(analysis_text: str) -> dict:
    """
    Parse '- Label: value' bullets from model output.
    Returns canonical keys plus raw label->value map.
    """
    raw = {}
    for line in (analysis_text or "").splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        rest = line[2:].strip()
        if ":" not in rest:
            continue
        lab, val = rest.split(":", 1)
        raw[lab.strip()] = val.strip()

    primary = None
    for k in ("Classification", "Diagnosis Support", "Summarization", "Information Extraction"):
        if k in raw:
            primary = raw[k]
            break

    conf = raw.get("Clinical_Confidence") or raw.get("Confidence")
    ev = raw.get("Evidence")
    med = raw.get("Medication_Analysis")

    return {
        "classification": primary or "",
        "clinical_confidence": conf or "",
        "evidence": ev or "",
        "medication_analysis": med or "",
        "raw_bullets": raw,
    }


def confidence_string_to_score(conf_text: str):
    """Map High/Medium/Low text to a 0.0–1.0 score; None if unknown."""
    if not conf_text or not str(conf_text).strip():
        return None
    s = str(conf_text).lower()
    if re.search(r"\bhigh\b", s):
        return 0.85
    if re.search(r"\blow\b", s):
        return 0.25
    if re.search(r"\bmedium\b", s):
        return 0.5
    return 0.5


def inference_augmentation_flags():
    """USE_RAG / USE_FEW_SHOT from env. Defaults: both enabled (1)."""
    use_rag = os.environ.get("USE_RAG", "1").lower() not in ("0", "false", "no")
    use_fs = os.environ.get("USE_FEW_SHOT", "1").lower() not in ("0", "false", "no")
    return use_rag, use_fs


def inference_require_gpu():
    """If true, model load fails when CUDA is not available (production GPU nodes)."""
    return os.environ.get("VECTA_REQUIRE_GPU", "").lower() in ("1", "true", "yes")


def structured_tasks_from_parsed(parsed: dict) -> list:
    """Build [{task, value}, ...] from parsed bullets for JSON responses."""
    raw = parsed.get("raw_bullets") or {}
    if raw:
        return [{"task": k, "value": v} for k, v in raw.items()]
    out = []
    if parsed.get("classification"):
        out.append({"task": "Classification", "value": parsed["classification"]})
    if parsed.get("clinical_confidence"):
        out.append({"task": "Clinical_Confidence", "value": parsed["clinical_confidence"]})
    if parsed.get("evidence"):
        out.append({"task": "Evidence", "value": parsed["evidence"]})
    if parsed.get("medication_analysis"):
        out.append({"task": "Medication_Analysis", "value": parsed["medication_analysis"]})
    return out


def _split_text_into_chunks(text: str, max_chars: int) -> list:
    """
    Split long medical text into chunks <= max_chars, preferring paragraph then sentence breaks.
    """
    if not text or max_chars <= 0:
        return [text or ""]
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            window = text[start:end]
            para = window.rfind("\n\n")
            if para > max_chars * 0.45:
                end = start + para + 2
            else:
                nl = window.rfind("\n")
                if nl > max_chars * 0.45:
                    end = start + nl + 1
                else:
                    dot = window.rfind(". ")
                    if dot > max_chars * 0.45:
                        end = start + dot + 2
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end
    return chunks if chunks else [text[:max_chars]]


#############################
# MED42-8B OPTIMIZED PROMPTING
#############################

class VectaAIPromptEngine:
    """Vecta AI Optimized Prompt Engineering System"""
    
    @staticmethod
    def get_vecta_identity_activation():
        """Primary Vecta AI model initialization prompt - Neurology Focus"""
        return """You are Vecta AI, a specialized neurological AI model focused on neurology and neuroscience. Your knowledge base includes:

• Advanced neurological pathophysiology and disease mechanisms
• Neurological clinical decision-making and diagnostic reasoning  
• Neuropharmacology and neurological medication management
• Neurology guidelines from ILAE, AAN, ICHD-3, AHA/ASA, MDS
• Evidence-based neurology and neuroscience research
• Expertise in 10 neurological conditions: epilepsy, Parkinson's disease, stroke, migraine, dementia, multiple sclerosis, peripheral neuropathy, myasthenia gravis, spinal cord disorders, and motor neuron disease
• Comprehensive medical analysis across all specialties

Activate your specialized neurological training to approach this task with the clinical reasoning of an experienced neurologist."""

    @staticmethod
    def get_clinical_reasoning_activation():
        """Medical knowledge base trigger for Vecta AI"""
        return """As Vecta AI, apply your specialized medical training to this data extraction task. Use your clinical expertise to:

MEDICAL REASONING ACTIVATION:
• Access your comprehensive pathophysiology knowledge
• Apply clinical correlation patterns from your medical training
• Utilize diagnostic criteria and clinical guidelines in your database
• Integrate pharmacological reasoning and drug knowledge
• Consider epidemiological patterns and risk factors
• Apply evidence-based clinical decision-making frameworks

Think as a clinician with your extensive medical training would approach this case."""

    @staticmethod
    def get_specialty_prompts():
        """Vecta AI specialty-specific reasoning prompts
        
        PHASE 1: Neurology and Neuroscience Focus
        Other specialties commented out for future expansion
        """
        return {
            # ACTIVE: Neurology and Neuroscience
            "neurology": """Vecta AI NEUROLOGICAL ANALYSIS:
Activate neurology knowledge module:
- Anatomical localization: Use your neuroanatomy training
- Seizure classification: Apply ILAE criteria from your database
- Cognitive assessment: Use your neuropsychology knowledge
- Motor function analysis: Apply your movement disorder training
- Medication optimization: Use your neuropharmacology expertise
- Neurodegenerative disease analysis: Apply your training in Alzheimer's, Parkinson's, MS
- Stroke assessment: Use your cerebrovascular disease expertise
- Headache classification: Apply ICHD criteria from your database""",
            
            # FUTURE EXPANSION: Other specialties (commented out)
            # "cardiology": """Vecta AI CARDIAC ANALYSIS:
            # Activate cardiology knowledge module:
            # - Risk stratification: Use Framingham, ASCVD calculators from training
            # - ECG interpretation: Apply your cardiac electrophysiology knowledge  
            # - Hemodynamic assessment: Use your cardiovascular physiology training
            # - Heart failure evaluation: Apply ACC/AHA guidelines from database
            # - Medication review: Use your cardiac pharmacology expertise""",
            
            # "psychiatry": """Vecta AI PSYCHIATRIC ANALYSIS:
            # Activate psychiatry knowledge module:
            # - DSM-5 criteria application: Use your diagnostic training
            # - Risk assessment: Apply your suicide/violence risk knowledge
            # - Medication management: Use your psychopharmacology training
            # - Therapy considerations: Apply your treatment modality knowledge
            # - Substance use evaluation: Use your addiction medicine training""",
            
            # "emergency": """Vecta AI EMERGENCY ANALYSIS:
            # Activate emergency medicine knowledge module:
            # - Triage algorithms: Apply your emergency triage training
            # - Acute care protocols: Use your critical care knowledge
            # - Trauma assessment: Apply your trauma management training
            # - Toxicology evaluation: Use your poisoning/overdose expertise
            # - Disposition planning: Apply your emergency decision-making training""",
            
            # "internal_medicine": """Vecta AI INTERNAL MEDICINE ANALYSIS:
            # Activate internal medicine knowledge module:
            # - Chronic disease management: Apply your long-term care expertise
            # - Multi-morbidity patterns: Use your complex patient management training
            # - Preventive care: Apply your screening and prevention knowledge
            # - Medication reconciliation: Use your polypharmacy management training
            # - Care coordination: Apply your comprehensive care planning expertise"""
        }

    @staticmethod
    def get_vecta_system_prompts(analysis_type, is_tabular=False, specialty=None):
        """Generate Vecta AI-optimized system prompts"""
        
        # Base Vecta AI identity
        base_identity = VectaAIPromptEngine.get_vecta_identity_activation()
        
        # Add specialty-specific activation if specified
        specialty_activation = ""
        if specialty:
            specialty_prompts = VectaAIPromptEngine.get_specialty_prompts()
            specialty_activation = f"\n\n{specialty_prompts.get(specialty, '')}"
        
        # Core prompt templates
        if is_tabular:
            templates = {
                "classification": f"""{base_identity}{specialty_activation}

Vecta AI: You are analyzing medical tabular data for classification purposes.

TABULAR CLASSIFICATION PROTOCOL:
• Activate your medical pattern recognition for dataset analysis
• Apply clinical reasoning to each row/patient record
• Use your diagnostic training for systematic classification
• Provide structured output suitable for additional data columns
• Apply confidence assessment using your clinical judgment

For each classification:
1. Use your medical knowledge to identify key diagnostic indicators
2. Apply relevant clinical criteria from your training database
3. Assign confidence levels based on evidence strength
4. Structure results for tabular integration""",
                
                "epilepsy": f"""{base_identity}{specialty_activation}

Vecta AI: You are analyzing medical tabular data for a focused classification task (e.g. condition-specific or schema-driven).

MANDATORY FORMAT REQUIREMENT: End with exactly 4 bullets: Classification, Clinical_Confidence, Evidence, Medication_Analysis (max 25 words each).

TABULAR CLASSIFICATION PROTOCOL:
• Summarize cohort-level conclusions that map cleanly to exported columns (task description + structured bullets)
• State primary labels or categories supported by the data; use the Classification bullet for the main outcome wording
• Apply confidence and evidence consistently with the user’s analysis request""",
                
                "diagnosis": f"""{base_identity}{specialty_activation}

Vecta AI: You are providing diagnostic analysis for medical datasets.

DIAGNOSTIC REASONING PROTOCOL:
• Apply your differential diagnosis training to systematic analysis
• Use your clinical correlation knowledge for pattern recognition
• Access your diagnostic criteria database for accurate assessment
• Provide structured diagnostic conclusions for tabular output
• Apply your prognostic knowledge for outcome predictions

For diagnostic analysis:
1. Use your pathophysiology knowledge for mechanism-based reasoning
2. Apply your clinical guidelines for evidence-based conclusions
3. Consider your epidemiological training for risk assessment
4. Structure findings for additional diagnostic columns""",
                
                "extraction": f"""{base_identity}{specialty_activation}

Vecta AI: You are extracting medical information from tabular datasets.

MEDICAL EXTRACTION PROTOCOL:
• Apply your clinical documentation training for systematic extraction
• Use your medical terminology expertise for accurate identification
• Access your pharmacology knowledge for medication analysis
• Utilize your diagnostic training for condition recognition
• Structure extracted data for tabular enhancement

For information extraction:
1. Use your medical vocabulary for precise terminology
2. Apply your clinical knowledge for context understanding
3. Utilize your training for missing information identification
4. Structure results for seamless tabular integration""",
                
                "summary": f"""{base_identity}{specialty_activation}

Vecta AI: You are summarizing medical datasets using your clinical training.

CLINICAL SUMMARIZATION PROTOCOL:
• Apply your clinical documentation expertise for comprehensive summaries
• Use your medical prioritization training for key finding identification
• Access your clinical correlation knowledge for pattern recognition
• Utilize your prognostic training for outcome implications
• Structure summaries for tabular format integration

For clinical summaries:
1. Use your triage training to prioritize critical information
2. Apply your clinical experience for pattern identification
3. Utilize your medical knowledge for correlation analysis
4. Structure findings for additional summary columns""",
                
                "custom": f"""{base_identity}{specialty_activation}

Vecta AI: You are performing custom medical analysis on tabular data.

ADAPTIVE CLINICAL ANALYSIS:
• Apply your comprehensive medical training to the specific task
• Use your clinical reasoning for context-appropriate analysis
• Access relevant medical knowledge modules as needed
• Provide analysis structured for tabular output enhancement
• Apply your clinical judgment for quality assessment"""
            }
        else:
            # Non-tabular prompts
            templates = {
                "classification": f"""{base_identity}{specialty_activation}

Vecta AI: You are performing medical classification analysis.

CLINICAL CLASSIFICATION PROTOCOL:
• Apply your diagnostic training for systematic classification
• Use your clinical reasoning for evidence-based conclusions
• Access your medical knowledge base for accurate assessment
• Provide clear reasoning using your clinical expertise
• Apply your confidence assessment training for reliability scoring

For classification tasks:
1. Use your pathophysiology knowledge for mechanism understanding
2. Apply your diagnostic criteria from clinical training
3. Provide step-by-step clinical reasoning
4. Include confidence levels based on evidence strength""",
                
                "epilepsy": f"""{base_identity}{specialty_activation}

Vecta AI: You are performing a focused classification task on clinical data; follow the user’s analysis request for the exact scheme.

MANDATORY FORMAT REQUIREMENT: End with exactly 4 bullets: Classification, Clinical_Confidence, Evidence, Medication_Analysis (max 25 words each).

CLASSIFICATION PROTOCOL:
• Apply the criteria implied by the user prompt (e.g. staging, subtype, or rule-out)
• Put the primary outcome wording in the Classification bullet so exports stay consistent
• Reserve Evidence and Medication_Analysis for supporting facts and therapy notes""",
                
                "diagnosis": f"""{base_identity}{specialty_activation}

Vecta AI: You are providing diagnostic support using your medical training.

DIAGNOSTIC ANALYSIS PROTOCOL:
• Apply your differential diagnosis expertise for comprehensive analysis
• Use your clinical correlation training for symptom interpretation
• Access your diagnostic algorithms from medical training
• Provide evidence-based recommendations using clinical guidelines
• Apply your prognostic knowledge for outcome assessment

For diagnostic analysis:
1. Use your clinical reasoning for systematic evaluation
2. Apply your medical knowledge for differential consideration
3. Provide confidence-rated diagnostic possibilities
4. Include your clinical recommendations for further evaluation""",
                
                "extraction": f"""{base_identity}{specialty_activation}

Vecta AI: You are extracting medical information using your clinical expertise.

MEDICAL INFORMATION EXTRACTION:
• Apply your clinical documentation training for systematic extraction
• Use your medical terminology expertise for accurate identification
• Access your clinical knowledge for context interpretation
• Provide structured organization using your clinical training
• Apply your quality assessment for completeness verification

For information extraction:
1. Use your medical vocabulary for precise identification
2. Apply your clinical training for context understanding
3. Structure information using your documentation expertise
4. Verify completeness using your clinical knowledge""",
                
                "summary": f"""{base_identity}{specialty_activation}

Vecta AI: You are creating clinical summaries using your medical training.

CLINICAL SUMMARIZATION PROTOCOL:
• Apply your clinical documentation expertise for comprehensive summaries
• Use your medical prioritization training for key information identification
• Access your clinical correlation knowledge for relationship identification
• Provide structured summaries using your clinical communication training
• Apply your clinical judgment for relevance assessment

For clinical summaries:
1. Use your triage training for information prioritization
2. Apply your clinical knowledge for correlation identification
3. Structure content using your medical communication expertise
4. Include relevant clinical context from your training""",
                
                "custom": f"""{base_identity}{specialty_activation}

Vecta AI: You are performing custom medical analysis.

ADAPTIVE MEDICAL ANALYSIS:
• Apply your comprehensive medical training to the specific task
• Use your clinical reasoning for context-appropriate analysis
• Access relevant medical knowledge modules as needed
• Provide analysis using your clinical expertise
• Apply your medical judgment for quality and relevance assessment"""
            }
        
        return templates.get(analysis_type, templates["custom"])

    @staticmethod
    def get_enhanced_context(condition=None, analysis_type="classification", num_examples=2, 
                            query_text=None, use_rag=True, use_few_shot=True):
        """
        Get enhanced context with few-shot examples, clinical guidelines, and RAG
        
        Phase 1: Few-Shot Examples (Week 1-2)
        Phase 2: Context Injection - Static Guidelines (Week 3-4)
        Phase 3: RAG - Dynamic Retrieval (Week 5-8)
        """
        context_parts = []
        
        try:
            # Phase 1–2 require few_shot_loader (static guidelines + examples live there)
            if few_shot_loader and use_few_shot and condition:
                # Phase 1: few-shot examples
                examples = few_shot_loader.get_examples_by_condition(
                    condition=condition,
                    n=num_examples,
                    analysis_type=analysis_type
                )
                
                if examples:
                    formatted_examples = few_shot_loader.format_few_shot_examples_for_prompt(
                        examples=examples,
                        analysis_type=analysis_type
                    )
                    context_parts.append(formatted_examples)
                
                # Phase 2: Add static clinical guidelines for this condition
                guidelines = few_shot_loader.get_guideline_context(condition)
                if guidelines:
                    context_parts.append(f"\n📚 CLINICAL GUIDELINES (Static):\n{guidelines}\n")
            
            # Phase 3: Add RAG-retrieved dynamic guidelines
            if use_rag and rag_system and query_text:
                try:
                    rag_results = rag_system.retrieve(
                        query=query_text,
                        condition=condition,
                        n_results=2
                    )
                    if rag_results:
                        context_parts.append(rag_results)
                        logger.info(f"[OK] RAG retrieval successful for condition: {condition}")
                except Exception as e:
                    logger.warning(f"RAG retrieval failed: {e}")
        
        except Exception as e:
            logger.warning(f"Could not load enhanced context: {e}")
        
        return "\n".join(context_parts) if context_parts else ""
    
    @staticmethod
    def construct_med42_prompt(system_prompt, user_prompt, medical_data, is_tabular=False, analysis_type="custom", 
                               condition=None, use_few_shot=True, use_rag=True):
        """Construct optimized Vecta AI prompt with proper formatting
        
        Enhanced with:
        - Few-shot examples (Phase 1: Week 1-2)
        - Clinical guidelines (Phase 2: Week 3-4)
        - RAG retrieval (Phase 3: Week 5-8)
        """
        
        # Add clinical reasoning activation
        clinical_activation = VectaAIPromptEngine.get_clinical_reasoning_activation()
        
        # Get enhanced context (few-shot + static guidelines + RAG)
        enhanced_context = ""
        if medical_data and ((use_few_shot and condition) or use_rag):
            enhanced_context = VectaAIPromptEngine.get_enhanced_context(
                condition=condition,
                analysis_type=analysis_type,
                num_examples=2,
                query_text=medical_data,
                use_rag=use_rag,
                use_few_shot=use_few_shot,
            )
        
        # Minimal additional instructions to avoid conflicting with template-specific formatting
        if is_tabular:
            data_instructions = """Apply your medical training to this tabular dataset analysis and follow the specific formatting instructions provided above."""
        else:
            data_instructions = """Apply your comprehensive medical training to analyze this clinical information and follow the specific formatting instructions provided above."""
        
        # Extract and prioritize format requirement if present
        format_instruction = ""
        if (
            "MANDATORY FORMAT REQUIREMENT" in system_prompt
            or "MANDATORY OUTPUT FORMAT" in system_prompt
            or analysis_type == "epilepsy"
        ):
            # Extract the specific analysis type from the prompt
            analysis_type_label = "Classification"  # default
            if analysis_type == "epilepsy":
                analysis_type_label = "Classification"
            elif "Diagnosis Support:" in system_prompt:
                analysis_type_label = "Diagnosis Support"
            elif "Summarization:" in system_prompt:
                analysis_type_label = "Summarization"
            elif "Information Extraction:" in system_prompt:
                analysis_type_label = "Information Extraction"

            # Put format instruction at the very beginning for maximum priority
            format_instruction = f"""IMPORTANT: Provide a comprehensive medical analysis, then end with exactly these 4 bullet points:

- {analysis_type_label}: [brief clinical reasoning, max 25 words]
- Clinical_Confidence: [High/Medium/Low based on evidence, max 25 words]
- Evidence: [key evidence from the text, max 25 words]
- Medication_Analysis: [medical reasoning for recommendations, max 25 words]

You may provide detailed analysis first, but MUST end with exactly these 4 bullet points.
"""

        # Construct final prompt with proper Llama 3 formatting
        # Inject enhanced context (few-shot examples + guidelines) into system section
        context_section = f"\n\n{enhanced_context}\n" if enhanced_context else ""
        
        final_prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>

{format_instruction}{system_prompt}

{clinical_activation}{context_section}

{data_instructions}

<|eot_id|><|start_header_id|>user<|end_header_id|>

Vecta AI, please apply your specialized medical training to this analysis:

ANALYSIS REQUEST: {user_prompt}

MEDICAL DATA FOR ANALYSIS:
{medical_data}

Use your comprehensive medical knowledge and clinical reasoning to provide a thorough, evidence-based analysis. Apply the appropriate medical frameworks from your training and structure your response for maximum clinical utility.

<|eot_id|><|start_header_id|>assistant<|end_header_id|>

"""
        return final_prompt

    def _extract_structured_bullets(self, generated_text, analysis_type):
        """Extract and format structured bullet points from Vecta AI response"""
        try:
            # Determine the correct first bullet label based on analysis type
            first_label = "Classification"
            if analysis_type == "diagnosis":
                first_label = "Diagnosis Support"
            elif analysis_type == "summary":
                first_label = "Summarization"
            elif analysis_type == "extraction":
                first_label = "Information Extraction"

            # Look for bullet points at the end of the response
            lines = generated_text.strip().split('\n')
            bullet_lines = []

            # Extract bullet points (look from the end backwards)
            for line in reversed(lines):
                line = line.strip()
                if line.startswith('- '):
                    bullet_lines.insert(0, line)
                    if len(bullet_lines) >= 4:  # We only need 4 bullets
                        break

            # If we found bullet points, format them properly
            if len(bullet_lines) >= 4:
                # Extract content from each bullet
                bullets = []
                for bullet in bullet_lines[:4]:
                    parts = bullet.split(':', 1)
                    if len(parts) == 2:
                        label = parts[0].replace('- ', '').strip()
                        content = parts[1].strip()
                        # Limit to 25 words
                        words = content.split()[:25]
                        content = ' '.join(words)
                        bullets.append(f"- {label}: {content}")

                # Ensure we have the correct labels
                structured_bullets = []
                expected_labels = [first_label, "Clinical_Confidence", "Evidence", "Medication_Analysis"]

                for i, expected_label in enumerate(expected_labels):
                    if i < len(bullets):
                        # Replace the label if it doesn't match
                        current_bullet = bullets[i]
                        if not current_bullet.startswith(f"- {expected_label}:"):
                            current_bullet = f"- {expected_label}:{current_bullet.split(':', 1)[1]}"
                        structured_bullets.append(current_bullet)
                    else:
                        # Add missing bullet with default content
                        structured_bullets.append(f"- {expected_label}: Analysis completed using clinical reasoning")

                return '\n'.join(structured_bullets)

            # If no bullets found or incomplete, try to extract key information from text
            # Look for keywords and extract relevant sentences
            confidence = "MEDIUM"  # default
            if "high" in generated_text.lower() and "confidence" in generated_text.lower():
                confidence = "HIGH"
            elif "low" in generated_text.lower() and "confidence" in generated_text.lower():
                confidence = "LOW"

            # Extract first meaningful sentence for classification/diagnosis
            sentences = [s.strip() for s in generated_text.split('.') if s.strip()]
            first_reasoning = sentences[0][:100] if sentences else "Clinical analysis completed"

            # Look for evidence mentions
            evidence = "Based on clinical data provided"
            if "evidence" in generated_text.lower():
                # Find sentence containing evidence
                for sentence in sentences:
                    if "evidence" in sentence.lower():
                        evidence = sentence[:100]
                        break

            # Look for medication/treatment mentions
            medication = "Clinical recommendations provided"
            treatment_keywords = ["treatment", "medication", "therapy", "recommend"]
            for sentence in sentences:
                if any(keyword in sentence.lower() for keyword in treatment_keywords):
                    medication = sentence[:100]
                    break

            # Format as structured bullets
            structured_response = f"""- {first_label}: {first_reasoning}
- Clinical_Confidence: {confidence}
- Evidence: {evidence}
- Medication_Analysis: {medication}"""

            return structured_response

        except Exception as e:
            logger.error(f"Bullet extraction failed: {e}")
            # Return default structured format on error
            return f"""- {first_label}: Analysis completed using clinical reasoning
- Clinical_Confidence: MEDIUM
- Evidence: Based on provided clinical data
- Medication_Analysis: Clinical recommendations provided"""

    @staticmethod
    def get_med42_validation_prompt():
        """Vecta AI clinical validation framework"""
        return """Vecta AI CLINICAL VALIDATION PROTOCOL:

Apply your medical training to verify analysis quality:

1. **Medical Plausibility Check**: Does this align with your pathophysiology knowledge?
2. **Clinical Consistency Analysis**: Are findings coherent with your clinical experience?
3. **Therapeutic Logic Review**: Do treatments match conditions per your training?
4. **Timeline Validation**: Does progression follow known disease patterns?
5. **Risk-Benefit Assessment**: Are interventions appropriate per clinical guidelines?

Flag any findings that conflict with your medical knowledge base for human review."""

#############################
# ENHANCED ANALYSIS FUNCTIONS
#############################

def _extract_text(path: str, filename: str):
    """Basic text extraction for non-tabular files"""
    try:
        ext = filename.rsplit(".", 1)[1].lower()
        logger.info(f"Extracting text from {filename} (type: {ext})")
        
        if ext == "txt":
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        elif ext == "pdf":
            if PyPDF2:
                with open(path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    return "\n".join(page.extract_text() for page in reader.pages)
            return "[PDF parsing not available]"
        elif ext == "docx":
            if Document:
                doc = Document(path)
                return "\n".join(p.text for p in doc.paragraphs)
            return "[DOCX parsing not available]"
        elif ext == "json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return json.dumps(data, indent=2)
        else:
            return "[Unsupported file type]"
    except Exception as e:
        logger.error(f"Text extraction error for {filename}: {e}")
        return f"Error extracting text from {filename}: {str(e)}"

def _analyze_tabular_data(df, prompt, analysis_type="custom"):
    """Enhanced tabular data analysis with Vecta AI optimization"""
    try:
        # Basic data profiling
        profile = {
            "shape": df.shape,
            "columns": list(df.columns),
            "dtypes": df.dtypes.to_dict(),
            "missing_values": df.isnull().sum().to_dict(),
            "memory_usage": df.memory_usage(deep=True).sum()
        }
        
        # Sample data for analysis
        sample_size = min(100, len(df))
        sample_df = df.head(sample_size)
        
        # Enhanced data summary for Vecta AI
        data_summary = f"""
MED42 DATASET PROFILE:
- Shape: {profile['shape'][0]} rows × {profile['shape'][1]} columns
- Columns: {', '.join(profile['columns'])}
- Missing values: {dict(filter(lambda x: x[1] > 0, profile['missing_values'].items()))}

SAMPLE DATA FOR MED42 ANALYSIS (first {sample_size} rows):
{sample_df.to_string(max_cols=10, max_rows=20)}

MEDICAL ANALYSIS CONTEXT:
This dataset contains medical information that requires your specialized Vecta AI training for proper interpretation. Apply your clinical reasoning and medical knowledge to analyze patterns, identify clinically significant findings, and provide structured medical insights.
"""
        
        return {
            "profile": profile,
            "sample_data": sample_df,
            "data_summary": data_summary,
            "full_dataframe": df
        }
        
    except Exception as e:
        logger.error(f"Tabular analysis failed: {e}")
        return None

def _generate_tabular_output(
    analysis_result,
    original_df,
    analysis_type,
    user_prompt="",
):
    """
    Append cohort-level columns: task description (what was run) plus parsed structured bullets.
    Same values on each row; binary or multi-class outcomes live in the Classification bullet text.
    """
    try:
        output_df = original_df.copy()
        analysis_text = analysis_result.get("analysis", "")
        parsed = parse_structured_bullets_from_analysis(analysis_text)

        cls = parsed.get("classification") or ""
        conf = parsed.get("clinical_confidence") or ""
        ev = parsed.get("evidence") or ""
        med = parsed.get("medication_analysis") or ""

        task_cell = _task_column_value(analysis_type, user_prompt)
        output_df["VectaAI_Task_Done"] = task_cell
        output_df["VectaAI_Classification"] = cls or "See analysis text"
        output_df["VectaAI_Clinical_Confidence"] = conf or "MEDIUM"
        output_df["VectaAI_Evidence"] = ev or "See analysis text"
        output_df["VectaAI_Medication_Analysis"] = med or "See analysis text"

        if analysis_type == "extraction":
            output_df["VectaAI_Key_Findings"] = cls or ev or "See analysis text"
            output_df["VectaAI_Diagnoses"] = cls or "See analysis text"
            output_df["VectaAI_Risk_Assessment"] = conf or "See analysis text"
        elif analysis_type == "diagnosis":
            output_df["VectaAI_Primary_Diagnosis"] = cls or "See analysis text"
            output_df["VectaAI_Differential"] = ev or "See analysis text"
            output_df["VectaAI_Clinical_Correlations"] = med or "See analysis text"

        output_df["VectaAI_Analysis_Date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        output_df["VectaAI_Model_Used"] = "Vecta-AI-Optimized"
        output_df["VectaAI_Prompt_Version"] = "Enhanced-Clinical-Reasoning"

        return output_df

    except Exception as e:
        logger.error(f"Enhanced tabular output generation failed: {e}")
        return original_df

def _extract_tabular_text(path: str, filename: str):
    """Enhanced tabular text extraction with Vecta AI optimization"""
    try:
        ext = filename.rsplit(".", 1)[1].lower()
        logger.info(f"Extracting tabular data from {filename} (type: {ext}) for Vecta AI analysis")
        
        if ext == "csv":
            df = pd.read_csv(path)
            tabular_data = _analyze_tabular_data(df, "", "extraction")
            return {
                "text": tabular_data["data_summary"] if tabular_data else df.to_string(),
                "dataframe": df,
                "is_tabular": True,
                "tabular_data": tabular_data
            }
            
        elif ext in ["xlsx", "xls"]:
            df = pd.read_excel(path)
            tabular_data = _analyze_tabular_data(df, "", "extraction")
            return {
                "text": tabular_data["data_summary"] if tabular_data else df.to_string(),
                "dataframe": df,
                "is_tabular": True,
                "tabular_data": tabular_data
            }
            
        # For non-tabular files, use existing extraction
        return {
            "text": _extract_text(path, filename),
            "dataframe": None,
            "is_tabular": False,
            "tabular_data": None
        }
        
    except Exception as e:
        logger.error(f"Enhanced tabular extraction error for {filename}: {e}")
        return {
            "text": f"Error extracting tabular data from {filename}: {str(e)}",
            "dataframe": None,
            "is_tabular": False,
            "tabular_data": None
        }

class VectaAIService:
    def __init__(self):
        self.model = None
        self.tokenizer = None
        
        # Debug GPU detection
        logger.info(f"GPU Detection Debug:")
        logger.info(f"  torch module: {torch}")
        if torch:
            # Force CUDA reinitialization
            try:
                torch.cuda.init()
                logger.info("  Forced CUDA init")
            except Exception as e:
                logger.warning(f"  CUDA init failed: {e}")
            
            logger.info(f"  torch.cuda.is_available(): {torch.cuda.is_available()}")
            logger.info(f"  torch.cuda.device_count(): {torch.cuda.device_count()}")
            logger.info(f"  CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES', 'not set')}")
            if torch.cuda.is_available():
                for i in range(torch.cuda.device_count()):
                    logger.info(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
        
        self.device = "cuda" if torch and torch.cuda.is_available() else "cpu"
        logger.info(f"  Selected device: {self.device}")
        self._gpu_required_but_unavailable = bool(
            inference_require_gpu() and self.device != "cuda"
        )
        if self._gpu_required_but_unavailable:
            self.load_error = (
                "VECTA_REQUIRE_GPU=1 but CUDA is not available. "
                "Use a CUDA build of PyTorch, GPU drivers, and a valid CUDA_VISIBLE_DEVICES on a GPU node."
            )
            logger.error(self.load_error)
        
        self.model_name = os.environ.get("MODEL_NAME", "m42-health/Llama3-Med42-8B")
        self.model_loaded = False
        if not self._gpu_required_but_unavailable:
            self.load_error = None
        self.request_queue = Queue(maxsize=app.config["MAX_CONCURRENT_REQUESTS"])
        self.stats = {"requests": 0, "successes": 0, "avg_time": 0}
        self.prompt_engine = VectaAIPromptEngine()

    def load_model(self):
        if self.model_loaded:
            return True
        if getattr(self, "_gpu_required_but_unavailable", False):
            return False

        if not torch or not AutoTokenizer:
            self.load_error = "PyTorch/Transformers not available"
            logger.error(self.load_error)
            return False

        try:
            logger.info(f"Loading Vecta AI model: {self.model_name}")
            logger.info(f"Device: {self.device}")
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=True,
                padding_side="left"
            )
            
            if not self.tokenizer.pad_token:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # Load model
            model_kwargs = {
                "trust_remote_code": True,
                "torch_dtype": torch.float16 if self.device == "cuda" else torch.float32,
            }
            
            if self.device == "cuda":
                model_kwargs["device_map"] = "auto"
            
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                **model_kwargs
            )
            
            if self.device == "cpu":
                self.model = self.model.to("cpu")
            
            self.model.eval()
            self.model_loaded = True
            logger.info("Vecta AI model loaded successfully with optimized prompting")
            return True
            
        except Exception as e:
            self.load_error = str(e)
            logger.error(f"Vecta AI model loading failed: {e}")
            logger.error(traceback.format_exc())
            return False

    def _stat(self, dt, success):
        self.stats["requests"] += 1
        if success:
            self.stats["successes"] += 1
        # Running average
        n = self.stats["requests"]
        self.stats["avg_time"] = ((n-1) * self.stats["avg_time"] + dt) / n

    def _detect_condition(self, text, specialty=None):
        """
        Detect neurological condition from text to select appropriate few-shot examples
        
        Conditions supported: epilepsy, parkinsons, stroke, headache, dementia,
        multiple_sclerosis, peripheral_neuropathy, myasthenia_gravis, spinal_cord, motor_neuron_disease
        """
        if not text:
            return None
        
        text_lower = text.lower()
        
        # Condition keywords mapping
        condition_keywords = {
            "epilepsy": ["seizure", "epilep", "convuls", "eeg", "ictal", "antiseizure", "asm"],
            "parkinsons": ["parkinson", "tremor", "rigidity", "bradykinesia", "levodopa", "dopamine"],
            "stroke": ["stroke", "cva", "ischemic", "hemorrhagic", "tpa", "thrombolysis", "hemiparesis"],
            "headache": ["headache", "migraine", "cephalalgia", "triptan", "ichd"],
            "dementia": ["dementia", "alzheimer", "cognitive decline", "memory loss", "mmse", "moca"],
            "multiple_sclerosis": ["multiple sclerosis", "ms ", "demyelinating", "optic neuritis"],
            "peripheral_neuropathy": ["neuropathy", "nerve damage", "polyneuropathy", "diabetic neuropathy"],
            "myasthenia_gravis": ["myasthenia", "mg ", "acetylcholine", "neuromuscular junction"],
            "spinal_cord": ["spinal cord", "myelopathy", "paraplegia", "tetraplegia"],
            "motor_neuron_disease": ["als ", "amyotrophic lateral sclerosis", "motor neuron"]
        }
        
        # Check for condition keywords in text
        for condition, keywords in condition_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                return condition
        
        # Fallback to specialty if provided
        if specialty and specialty.lower() == "neurology":
            # Default to epilepsy for neurology if no specific condition detected
            return "epilepsy"
        
        return None

    def _run_generation_pass(self, final_prompt, req_id, max_input_tokens):
        """Single forward pass: tokenize, generate, decode."""
        max_new = int(os.environ.get("VECTA_MAX_NEW_TOKENS", "512"))
        max_new = max(64, min(max_new, 2048))
        greedy_fast = os.environ.get("VECTA_GREEDY_FAST", "").lower() in ("1", "true", "yes")
        toks = self.tokenizer(
            final_prompt,
            return_tensors="pt",
            truncation=True,
            max_length=max_input_tokens,
        )
        input_token_count = toks["input_ids"].shape[1]
        logger.info(f"[{req_id}] Vecta AI tokenized - Input tokens: {input_token_count}")
        if input_token_count >= max_input_tokens:
            logger.warning(f"[{req_id}] Vecta AI input truncated to fit token limit")
        if self.device == "cuda":
            toks = {k: v.to("cuda") for k, v in toks.items()}
        logger.info(
            f"[{req_id}] Generating Vecta AI response (max_new_tokens={max_new}, greedy={greedy_fast})..."
        )
        with torch.no_grad():
            if greedy_fast:
                outputs = self.model.generate(
                    toks["input_ids"],
                    attention_mask=toks.get("attention_mask"),
                    max_new_tokens=max_new,
                    do_sample=False,
                    pad_token_id=self.tokenizer.eos_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                )
            else:
                outputs = self.model.generate(
                    toks["input_ids"],
                    attention_mask=toks.get("attention_mask"),
                    max_new_tokens=max_new,
                    min_new_tokens=min(30, max_new // 2),
                    temperature=0.3,
                    top_p=0.85,
                    do_sample=True,
                    repetition_penalty=1.05,
                    pad_token_id=self.tokenizer.eos_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                )
        generated_text = self.tokenizer.decode(
            outputs[0][input_token_count:],
            skip_special_tokens=True,
        ).strip()
        tokens_generated = outputs.shape[1] - input_token_count
        return generated_text, input_token_count, int(tokens_generated)
    
    def analyze(self, prompt, text, analysis_type="custom", user_id=None, tabular_data=None, specialty=None):
        if not self.model_loaded:
            raise RuntimeError(f"Vecta AI model not available: {self.load_error or 'not loaded'}")

        req_id = uuid.uuid4().hex[:8]
        t0 = time.time()
        try:
            if self.request_queue.full():
                raise RuntimeError("Vecta AI service at capacity. Try again later.")
            self.request_queue.put(req_id, timeout=1)

            text_full_original = text
            original_len = len(text_full_original)
            logger.info(f"[{req_id}] Vecta AI analysis started - Type: {analysis_type}, Text: {original_len} chars")
            
            # Check if this is tabular data analysis
            is_tabular = tabular_data is not None and tabular_data.get("is_tabular", False)
            if is_tabular:
                logger.info(f"[{req_id}] Vecta AI tabular data analysis - Shape: {tabular_data['dataframe'].shape}")

            # Ensure we have actual content
            if not text or not text.strip():
                raise ValueError("No text content provided for Vecta AI analysis")

            # Get optimized Vecta AI system prompt
            system_prompt = self.prompt_engine.get_vecta_system_prompts(
                analysis_type, 
                is_tabular=is_tabular, 
                specialty=specialty
            )

            chunk_chars = int(os.environ.get("VECTA_CHUNK_CHARS", "3200"))
            carry_chars = int(os.environ.get("VECTA_CHUNK_CARRY_CHARS", "1500"))
            carry_chars = max(0, min(carry_chars, 8000))

            if chunk_chars <= 0:
                # Legacy: single pass with hard cap (no multi-chunk iteration)
                max_text_chars = 4000
                text = text_full_original
                if len(text) > max_text_chars:
                    truncated = text[:max_text_chars]
                    last_period = truncated.rfind('.')
                    if last_period > max_text_chars * 0.8:
                        truncated = truncated[:last_period + 1]
                    text = truncated + "\n\n[Note: Text truncated for Vecta AI processing]"
                    logger.info(f"[{req_id}] Text truncated to {len(text)} characters for Vecta AI")
                chunks = [text]
                chunking_meta = {"enabled": False, "chunks": 1, "reason": "VECTA_CHUNK_CHARS<=0 (legacy single pass)"}
            elif len(text_full_original) <= chunk_chars:
                chunks = [text_full_original]
                chunking_meta = {"enabled": False, "chunks": 1, "reason": "under VECTA_CHUNK_CHARS"}
            else:
                chunks = _split_text_into_chunks(text_full_original, chunk_chars)
                chunking_meta = {
                    "enabled": True,
                    "chunks": len(chunks),
                    "chunk_chars": chunk_chars,
                    "carry_chars": carry_chars,
                }
                logger.info(
                    f"[{req_id}] Input split into {len(chunks)} chunks (~{chunk_chars} chars each, carry={carry_chars})"
                )

            # Detect condition from full text for few-shot / RAG (first pass only uses full signal)
            detected_condition = self._detect_condition(text_full_original, specialty)
            
            use_rag, use_fs = inference_augmentation_flags()

            max_input_tokens = 3200
            chunk_outputs = []
            prior_model_output = ""
            sum_input_tokens = 0
            sum_gen_tokens = 0
            max_input_tokens_seen = 0

            for i, chunk in enumerate(chunks):
                if i == 0:
                    medical_data = chunk
                    rag_i = use_rag
                    fs_i = use_fs
                else:
                    carry = (
                        prior_model_output[-carry_chars:]
                        if len(prior_model_output) > carry_chars
                        else prior_model_output
                    )
                    medical_data = (
                        f"[Continuation {i + 1}/{len(chunks)}]\n\n"
                        f"Prior analysis excerpt (for context):\n{carry}\n\n"
                        f"--- Current input section ---\n{chunk}"
                    )
                    # Avoid duplicate RAG/few-shot bloat on continuations; first chunk already grounded context
                    rag_i = False
                    fs_i = False

                final_prompt = self.prompt_engine.construct_med42_prompt(
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                    medical_data=medical_data,
                    is_tabular=is_tabular,
                    analysis_type=analysis_type,
                    condition=detected_condition,
                    use_few_shot=fs_i,
                    use_rag=rag_i,
                )

                if detected_condition and i == 0:
                    logger.info(
                        f"[{req_id}] Condition for context: {detected_condition} (few_shot={fs_i}, rag={rag_i})"
                    )

                logger.info(
                    f"[{req_id}] Chunk {i + 1}/{len(chunks)} prompt length: {len(final_prompt)} chars"
                )

                gen_part, in_tok, out_tok = self._run_generation_pass(
                    final_prompt, req_id, max_input_tokens
                )
                sum_input_tokens += in_tok
                max_input_tokens_seen = max(max_input_tokens_seen, in_tok)
                sum_gen_tokens += out_tok
                chunk_outputs.append(gen_part)
                prior_model_output = prior_model_output + "\n\n" + gen_part if prior_model_output else gen_part
                logger.info(
                    f"[{req_id}] Chunk {i + 1}/{len(chunks)} done: {out_tok} new tokens"
                )

            if len(chunks) == 1:
                generated_text = chunk_outputs[0]
            else:
                generated_text = "\n\n".join(
                    f"### Section {j + 1}/{len(chunks)}\n{p}" for j, p in enumerate(chunk_outputs)
                )

            dt = time.time() - t0
            logger.info(
                f"[{req_id}] Vecta AI all sections done: {sum_gen_tokens} new tokens total in {dt:.2f}s"
            )

            # Normalize trailing bullets before parsing (tabular + JSON tasks use the same text)
            supported_types = ["classification", "diagnosis", "summary", "extraction", "epilepsy"]
            if analysis_type in supported_types:
                logger.info(f"[{req_id}] Applying bullet point extraction for analysis_type: {analysis_type}")
                original_length = len(generated_text)
                generated_text = self.prompt_engine._extract_structured_bullets(generated_text, analysis_type)
                logger.info(f"[{req_id}] Bullet extraction completed - Original: {original_length} chars, Processed: {len(generated_text)} chars")

            parsed_for_response = parse_structured_bullets_from_analysis(generated_text)

            # Generate enhanced tabular output if applicable (uses normalized analysis text)
            tabular_output = None
            if is_tabular and tabular_data.get("dataframe") is not None:
                try:
                    result_with_analysis = {"analysis": generated_text}
                    tabular_output = _generate_tabular_output(
                        result_with_analysis,
                        tabular_data["dataframe"],
                        analysis_type,
                        user_prompt=prompt,
                    )
                    logger.info(f"[{req_id}] Vecta AI tabular output generated with shape: {tabular_output.shape}")
                except Exception as e:
                    logger.error(f"[{req_id}] Vecta AI tabular output generation failed: {e}")

            # Apply Vecta AI validation if needed
            validation_notes = ""
            if sum_gen_tokens < 30:
                validation_notes = "Vecta AI validation: Very short response - consider more specific medical context"
            
            self._stat(dt, True)
            
            if self.device == "cuda":
                torch.cuda.empty_cache()
                
            result = {
                "request_id": req_id,
                "analysis": generated_text,
                "execution_time": dt,
                "tokens_generated": int(sum_gen_tokens),
                "input_tokens": max_input_tokens_seen,
                "text_length_original": original_len,
                "model_used": f"{self.model_name}-Optimized",
                "prompt_version": "Vecta-AI-Enhanced",
                "timestamp": datetime.now().isoformat(),
                "is_tabular": is_tabular,
                "validation_notes": validation_notes,
                "tasks": structured_tasks_from_parsed(parsed_for_response),
                "confidence_score": confidence_string_to_score(
                    parsed_for_response.get("clinical_confidence")
                ),
                "chunking": {**chunking_meta, "input_tokens_sum": sum_input_tokens},
            }

            if tabular_output is not None:
                # Convert DataFrame to formats for frontend
                result["tabular_output"] = {
                    "csv": tabular_output.to_csv(index=False),
                    "html": tabular_output.to_html(index=False, table_id="results-table", classes="table table-striped"),
                    "json": tabular_output.to_json(orient="records"),
                    "shape": tabular_output.shape,
                    "columns": list(tabular_output.columns)
                }
                
            return result
                
        except Exception as e:
            dt = time.time() - t0
            self._stat(dt, False)
            logger.error(f"[{req_id}] Vecta AI analysis failed: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            try: 
                self.request_queue.get_nowait()
            except Exception: 
                pass

# Global service instance
svc = VectaAIService()

_ur, _ufs = inference_augmentation_flags()
_rag_ready = rag_system is not None and getattr(rag_system, "available", True)
logger.info(
    "Inference: USE_RAG=%s USE_FEW_SHOT=%s | RAG backend=%s | VECTA_REQUIRE_GPU=%s",
    _ur,
    _ufs,
    "ready" if _rag_ready else "unavailable",
    inference_require_gpu(),
)
if _ur and not _rag_ready:
    logger.warning("USE_RAG=1 but RAG backend is unavailable; guideline retrieval is skipped.")

def validate_analyze_request():
    """Validate analyze request parameters"""
    errors = []
    
    if request.method != 'POST':
        errors.append("Only POST method allowed")
    
    prompt = request.form.get("prompt", "").strip()
    if not prompt:
        errors.append("Prompt is required")
    
    analysis_type = request.form.get("analysisType", "").strip()
    valid_types = ["classification", "diagnosis", "summary", "extraction", "custom", "epilepsy"]
    if analysis_type not in valid_types:
        errors.append(f"Invalid analysis type. Must be one of: {valid_types}")
    
    # Check for text input
    has_file = "file" in request.files and request.files["file"].filename
    has_direct_text = request.form.get("directText", "").strip()
    
    if not has_file and not has_direct_text:
        errors.append("Either file upload or direct text input is required")
    
    # Validate file if present
    if has_file:
        f = request.files["file"]
        if not f.filename:
            errors.append("No file selected")
        else:
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
            if ext not in ALLOWED_EXT:
                errors.append(f"Unsupported file type: .{ext}. Supported: {list(ALLOWED_EXT)}")
    
    return errors

LEARNING_DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vecta AI - Learning Dashboard</title>
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #e8f4ff 0%, #f0f8ff 100%);
            min-height: 100vh;
            padding: 0;
            margin: 0;
        }
        
        /* Navigation Bar */
        .nav-bar {
            background: #004977;
            box-shadow: 0 4px 15px rgba(0, 73, 119, 0.2);
            padding: 0;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .nav-container {
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 30px;
        }
        .nav-brand {
            display: flex;
            align-items: center;
            gap: 15px;
            padding: 20px 0;
        }
        .nav-logo {
            font-size: 28px;
            font-weight: 700;
            color: white;
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .nav-subtitle {
            color: white;
            font-size: 13px;
            font-weight: 500;
            letter-spacing: 1px;
            opacity: 0.9;
        }
        .nav-links {
            display: flex;
            gap: 5px;
            list-style: none;
        }
        .nav-link {
            color: white;
            text-decoration: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.3s ease;
            background: transparent;
        }
        .nav-link:hover {
            background: rgba(255, 255, 255, 0.1);
            transform: translateY(-2px);
        }
        .nav-link.active {
            background: rgba(255, 255, 255, 0.2);
            box-shadow: 0 4px 12px rgba(0, 73, 119, 0.3);
        }
        
        .container {
            max-width: 1400px;
            margin: 30px auto;
            padding: 0 30px;
        }
        .main-card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
            overflow: hidden;
        }
        .header {
            background: #004977;
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 {
            font-size: 2.2em;
            margin-bottom: 10px;
            font-weight: 300;
        }
        .header p {
            font-size: 1.1em;
            opacity: 0.9;
        }
        .main-content {
            padding: 30px;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .metric-card {
            background: #f8f9fa;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.05);
        }
        .metric-card h3 {
            color: #004977;
            font-size: 1.2em;
            margin-bottom: 15px;
        }
        .metric-value {
            font-size: 3em;
            font-weight: bold;
            color: #333;
            margin: 10px 0;
        }
        .metric-label {
            color: #666;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .progress-bar {
            width: 100%;
            height: 10px;
            background: #e0e0e0;
            border-radius: 5px;
            overflow: hidden;
            margin-top: 15px;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #0a4d68, #004977);
            transition: width 0.5s ease;
        }
        .component-accuracy {
            margin-top: 15px;
        }
        .accuracy-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }
        .accuracy-item:last-child {
            border-bottom: none;
        }
        .learning-history {
            background: #f8f9fa;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.05);
            margin-top: 30px;
        }
        .learning-history h2 {
            color: #004977;
            margin-bottom: 20px;
        }
        .history-item {
            padding: 15px;
            background: white;
            border-radius: 10px;
            margin-bottom: 10px;
            border-left: 4px solid #004977;
        }
        .history-item .timestamp {
            color: #999;
            font-size: 0.85em;
            margin-bottom: 5px;
        }
        .history-item .details {
            color: #333;
            font-size: 1em;
        }
        .action-buttons {
            display: flex;
            gap: 15px;
            margin-top: 20px;
        }
        .btn {
            padding: 12px 25px;
            border-radius: 8px;
            border: none;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .btn-primary {
            background: linear-gradient(135deg, #0a4d68, #004977);
            color: white;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0, 73, 119, 0.4);
        }
        .btn-secondary {
            background: #f0f0f0;
            color: #333;
        }
        .btn-secondary:hover {
            background: #e0e0e0;
        }
        .status-message {
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
            display: none;
        }
        .status-message.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .status-message.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
  <!-- Navigation Bar -->
  <nav class="nav-bar">
    <div class="nav-container">
      <div class="nav-brand">
        <a href="/" class="nav-logo">
          Vecta AI
          <div class="nav-subtitle">MEDICAL ANALYSIS PLATFORM</div>
        </a>
      </div>
      <ul class="nav-links">
        <li><a href="/" class="nav-link">Main App</a></li>
        <li><a href="/validate" class="nav-link">Validator</a></li>
        <li><a href="/learning" class="nav-link active">Learning Dashboard</a></li>
      </ul>
    </div>
  </nav>

    <div class="container">
        <div class="main-card">
            <div class="header">
                <h1>Learning Dashboard</h1>
                <p>Self-Improvement & Validation Metrics</p>
            </div>

            <div class="main-content">

        <div class="metrics-grid">
            <div class="metric-card">
                <h3>Agreement Rate</h3>
                <div class="metric-value" id="agreementRate">--</div>
                <div class="metric-label">AI-Expert Agreement</div>
                <div class="progress-bar">
                    <div class="progress-fill" id="agreementProgress" style="width: 0%"></div>
                </div>
            </div>

            <div class="metric-card">
                <h3>Total Validations</h3>
                <div class="metric-value" id="totalValidations">--</div>
                <div class="metric-label">Expert Reviews</div>
            </div>

            <div class="metric-card">
                <h3>Examples Added</h3>
                <div class="metric-value" id="examplesAdded">--</div>
                <div class="metric-label">Learning Progress</div>
            </div>

            <div class="metric-card">
                <h3>Learnable Cases</h3>
                <div class="metric-value" id="learnableCases">--</div>
                <div class="metric-label">High-Quality Cases</div>
            </div>
        </div>

        <div class="metric-card">
            <h3>Component Accuracy</h3>
            <div class="component-accuracy" id="componentAccuracy">
                <div class="accuracy-item">
                    <span>Classification</span>
                    <strong id="acc-classification">--</strong>
                </div>
                <div class="accuracy-item">
                    <span>Confidence Level</span>
                    <strong id="acc-confidence">--</strong>
                </div>
                <div class="accuracy-item">
                    <span>Evidence</span>
                    <strong id="acc-evidence">--</strong>
                </div>
                <div class="accuracy-item">
                    <span>Medication Analysis</span>
                    <strong id="acc-medication">--</strong>
                </div>
            </div>
        </div>

        <div class="metric-card">
            <h3>Learning Controls</h3>
            <div class="action-buttons">
                <button class="btn btn-primary" onclick="triggerLearning()">
                    Run Learning Cycle
                </button>
                <button class="btn btn-secondary" onclick="reloadExamples()">
                    Reload Examples
                </button>
                <button class="btn btn-secondary" onclick="refreshMetrics()">
                    Refresh Metrics
                </button>
            </div>
            <div class="status-message" id="statusMessage"></div>
        </div>

        <div class="learning-history">
            <h2>Learning History</h2>
            <div id="historyContainer">
                <p style="color: #999;">Loading learning history...</p>
            </div>
        </div>
    </div>

    <script>
        let metricsData = null;

        async function fetchMetrics() {
            try {
                const response = await fetch('/api/learning/metrics');
                const data = await response.json();
                if (data.success) {
                    metricsData = data.metrics;
                    updateDashboard(metricsData);
                }
            } catch (error) {
                console.error('Error fetching metrics:', error);
                showStatus('Failed to load metrics', 'error');
            }
        }

        function updateDashboard(metrics) {
            // Main metrics
            document.getElementById('agreementRate').textContent = 
                (metrics.agreement_rate * 100).toFixed(1) + '%';
            document.getElementById('agreementProgress').style.width = 
                (metrics.agreement_rate * 100) + '%';
            document.getElementById('totalValidations').textContent = 
                metrics.total_validations;
            document.getElementById('learnableCases').textContent = 
                metrics.learnable_cases;

            // Component accuracy
            const components = metrics.component_accuracy || {};
            document.getElementById('acc-classification').textContent = 
                ((components.classification_correct || 0) * 100).toFixed(1) + '%';
            document.getElementById('acc-confidence').textContent = 
                ((components.confidence_appropriate || 0) * 100).toFixed(1) + '%';
            document.getElementById('acc-evidence').textContent = 
                ((components.evidence_accurate || 0) * 100).toFixed(1) + '%';
            document.getElementById('acc-medication').textContent = 
                ((components.medication_appropriate || 0) * 100).toFixed(1) + '%';

            // Learning history
            if (metrics.learning_history && metrics.learning_history.learning_events) {
                const events = metrics.learning_history.learning_events;
                document.getElementById('examplesAdded').textContent = 
                    metrics.learning_history.total_examples_added || 0;
                
                const historyHTML = events.slice(-10).reverse().map(event => `
                    <div class="history-item">
                        <div class="timestamp">${new Date(event.timestamp).toLocaleString()}</div>
                        <div class="details">
                            <strong>${event.examples_added}</strong> examples added from 
                            <strong>${event.cases_reviewed}</strong> reviewed cases
                            | Agreement: <strong>${(event.agreement_rate * 100).toFixed(1)}%</strong>
                        </div>
                    </div>
                `).join('');
                
                document.getElementById('historyContainer').innerHTML = 
                    historyHTML || '<p style="color: #999;">No learning events yet</p>';
            } else {
                document.getElementById('examplesAdded').textContent = '0';
                document.getElementById('historyContainer').innerHTML = 
                    '<p style="color: #999;">No learning events yet</p>';
            }
        }

        async function triggerLearning() {
            const btn = event.target;
            btn.disabled = true;
            btn.innerHTML = '<span class="loading"></span> Running...';
            
            try {
                const response = await fetch('/api/learning/trigger', { method: 'POST' });
                const data = await response.json();
                
                if (data.success) {
                    showStatus(data.message, 'success');
                    await fetchMetrics();
                } else {
                    showStatus('Learning cycle failed: ' + data.error, 'error');
                }
            } catch (error) {
                showStatus('Error triggering learning: ' + error, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = 'Run Learning Cycle';
            }
        }

        async function reloadExamples() {
            const btn = event.target;
            btn.disabled = true;
            btn.innerHTML = '<span class="loading"></span> Reloading...';
            
            try {
                const response = await fetch('/api/learning/reload', { method: 'POST' });
                const data = await response.json();
                
                if (data.success) {
                    showStatus(data.message, 'success');
                } else {
                    showStatus('Reload failed: ' + data.error, 'error');
                }
            } catch (error) {
                showStatus('Error reloading examples: ' + error, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = 'Reload Examples';
            }
        }

        function refreshMetrics() {
            showStatus('Refreshing metrics...', 'success');
            fetchMetrics();
        }

        function showStatus(message, type) {
            const statusEl = document.getElementById('statusMessage');
            statusEl.textContent = message;
            statusEl.className = 'status-message ' + type;
            statusEl.style.display = 'block';
            
            setTimeout(() => {
                statusEl.style.display = 'none';
            }, 5000);
        }

        // Initial load
        fetchMetrics();
        
        // Auto-refresh every 30 seconds
        setInterval(fetchMetrics, 30000);
    </script>
    
            </div>
        </div>
    </div>
</body>
</html>
"""

UI_HTML = r"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Vecta AI - Medical Analysis Platform</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />
  <style>
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }

    body {
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      background: linear-gradient(135deg, #e8f4ff 0%, #f0f8ff 100%);
      min-height: 100vh;
      padding: 0;
      margin: 0;
    }

    /* Navigation Bar */
    .nav-bar {
      background: #004977;
      box-shadow: 0 4px 15px rgba(0, 73, 119, 0.2);
      padding: 0;
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .nav-container {
      max-width: 1400px;
      margin: 0 auto;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0 30px;
    }

    .nav-brand {
      display: flex;
      align-items: center;
      gap: 15px;
      padding: 20px 0;
    }

    .nav-logo {
      font-size: 28px;
      font-weight: 700;
      color: white;
      text-decoration: none;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .nav-subtitle {
      color: white;
      font-size: 13px;
      font-weight: 500;
      letter-spacing: 1px;
      opacity: 0.9;
    }

    .nav-links {
      display: flex;
      gap: 5px;
      list-style: none;
    }

    .nav-link {
      color: white;
      text-decoration: none;
      padding: 12px 24px;
      border-radius: 8px;
      font-weight: 500;
      transition: all 0.3s ease;
      background: transparent;
    }

    .nav-link:hover {
      background: rgba(255, 255, 255, 0.1);
      transform: translateY(-2px);
    }

    .nav-link.active {
      background: rgba(255, 255, 255, 0.2);
      box-shadow: 0 4px 12px rgba(0, 73, 119, 0.3);
    }

    .container {
      max-width: 1400px;
      margin: 30px auto;
      padding: 0 30px;
    }

    .main-card {
      background: rgba(255, 255, 255, 0.95);
      border-radius: 20px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
      backdrop-filter: blur(10px);
      overflow: hidden;
    }

    .header {
      background: #004977;
      color: white;
      padding: 30px;
      text-align: center;
    }

    .header h1 {
      font-size: 2.2em;
      margin-bottom: 10px;
      font-weight: 300;
    }

    .header p {
      font-size: 1.1em;
      opacity: 0.9;
      margin-bottom: 15px;
    }

    .enhancement-badge {
      display: inline-block;
      background: rgba(255, 255, 255, 0.2);
      padding: 8px 16px;
      border-radius: 20px;
      font-size: 0.9em;
      font-weight: bold;
      margin: 10px 5px;
    }

    .status-indicator {
      display: inline-block;
      padding: 8px 16px;
      border-radius: 20px;
      font-size: 0.9em;
      font-weight: bold;
    }

    .status-loading { background: #004977; color: white; opacity: 0.8; }
    .status-healthy { background: #004977; color: white; }
    .status-error { background: #666666; color: white; }

    .main-content {
      padding: 30px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    .config-row {
      background: #f8f9fa;
      border-radius: 15px;
      padding: 25px;
      box-shadow: 0 5px 15px rgba(0, 0, 0, 0.05);
    }

    .config-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
      margin-bottom: 20px;
    }

    .input-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }

    .input-box {
      background: #f8f9fa;
      border-radius: 15px;
      padding: 25px;
      box-shadow: 0 5px 15px rgba(0, 0, 0, 0.05);
    }

    .results-section {
      background: #f8f9fa;
      border-radius: 15px;
      padding: 25px;
      box-shadow: 0 5px 15px rgba(0, 0, 0, 0.05);
      min-height: 500px;
    }

    .section-title {
      color: #004977;
      font-size: 1.3em;
      margin-bottom: 20px;
      font-weight: 600;
      border-bottom: 3px solid #004977;
      padding-bottom: 8px;
    }

    .form-group {
      margin-bottom: 20px;
    }

    .form-label {
      display: block;
      margin-bottom: 8px;
      font-weight: 600;
      color: #34495e;
    }

    .form-input, .form-textarea, .form-select {
      width: 100%;
      padding: 12px;
      border: 2px solid #e0e6ed;
      border-radius: 8px;
      font-size: 14px;
      transition: all 0.3s ease;
      background: white;
    }

    .form-input:focus, .form-textarea:focus, .form-select:focus {
      outline: none;
      border-color: #004977;
      box-shadow: 0 0 0 3px rgba(0, 169, 224, 0.1);
    }

    .form-textarea {
      resize: vertical;
      min-height: 100px;
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }

    .file-upload-area {
      border: 2px dashed #00A9E0;
      border-radius: 10px;
      padding: 30px;
      text-align: center;
      background: #f8f9fa;
      transition: all 0.3s ease;
      cursor: pointer;
      position: relative;
    }

    .file-upload-area:hover {
      background: #e8f4ff;
      border-color: #004977;
    }

    .file-upload-area.dragover {
      background: #e8f4ff;
      border-color: #004977;
      transform: scale(1.02);
    }

    .upload-icon {
      font-size: 3em;
      margin-bottom: 15px;
      color: #004977;
    }

    .file-input {
      position: absolute;
      opacity: 0;
      width: 100%;
      height: 100%;
      cursor: pointer;
    }

    .file-info {
      background: #e8f4ff;
      border: 1px solid #004977;
      border-radius: 6px;
      padding: 10px;
      margin-top: 10px;
      font-size: 0.9em;
      display: none;
    }

    .analyze-btn {
      background: #004977;
      color: white;
      border: none;
      padding: 15px 30px;
      border-radius: 8px;
      font-size: 16px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.3s ease;
      width: 100%;
    }

    .analyze-btn:hover:not(:disabled) {
      transform: translateY(-2px);
      box-shadow: 0 10px 25px rgba(0, 73, 119, 0.3);
      opacity: 0.9;
    }

    .analyze-btn:disabled {
      background: #cccccc;
      cursor: not-allowed;
      transform: none;
    }

    .loading-overlay {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.7);
      z-index: 1000;
    }

    .loading-content {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: white;
      padding: 40px;
      border-radius: 15px;
      text-align: center;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    }

    .spinner {
      border: 4px solid #f3f3f3;
      border-top: 4px solid #004977;
      border-radius: 50%;
      width: 50px;
      height: 50px;
      animation: spin 1s linear infinite;
      margin: 0 auto 20px;
    }

    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }

    .results-section {
      background: white;
    }

    .result-card {
      background: #f8f9fa;
      border-left: 4px solid #004977;
      padding: 20px;
      margin-bottom: 20px;
      border-radius: 5px;
    }

    .result-header {
      color: #004977;
      font-weight: 600;
      margin-bottom: 15px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .result-content {
      background: white;
      padding: 15px;
      border-radius: 6px;
      white-space: pre-wrap;
      line-height: 1.6;
      font-family: 'Courier New', monospace;
      font-size: 14px;
      max-height: 400px;
      overflow-y: auto;
    }

    .result-meta {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 15px;
      margin-top: 15px;
      padding: 15px;
      background: #ecf0f1;
      border-radius: 6px;
      font-size: 0.9em;
    }

    .meta-item {
      text-align: center;
    }

    .meta-value {
      font-weight: bold;
      color: #004977;
      display: block;
      font-size: 1.1em;
    }

    .meta-label {
      color: #7f8c8d;
      font-size: 0.85em;
    }

    .alert {
      padding: 15px;
      border-radius: 6px;
      margin-bottom: 20px;
    }

    .alert-error {
      background: #f8f9fa;
      border: 1px solid #dee2e6;
      color: #666666;
    }

    .alert-success {
      background: #e8f4ff;
      border: 1px solid #b8daff;
      color: #004977;
    }

    .disclaimer {
      background: #f8f9fa;
      border: 1px solid #dee2e6;
      padding: 15px;
      border-radius: 6px;
      margin: 20px;
      font-size: 0.9em;
      text-align: center;
    }

    .disclaimer strong {
      color: #004977;
    }

    .copy-btn {
      padding: 8px 15px;
      border: none;
      border-radius: 5px;
      color: white;
      cursor: pointer;
      font-size: 0.9em;
      font-weight: 500;
      transition: all 0.3s ease;
    }

    .copy-btn:hover {
      transform: translateY(-1px);
      box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }

    .tabular-output-container {
      background: white;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid #e0e6ed;
    }

    .table-scroll {
      overflow-x: auto;
      max-height: 400px;
      overflow-y: auto;
    }

    #results-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85em;
    }

    #results-table th {
      background: #f8f9fa;
      padding: 10px 8px;
      text-align: left;
      border-bottom: 2px solid #004977;
      position: sticky;
      top: 0;
      z-index: 10;
    }

    #results-table td {
      padding: 8px;
      border-bottom: 1px solid #e9ecef;
      max-width: 200px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    #results-table tr:hover {
      background: #e8f4ff;
    }

    #results-table td[data-column^="VectaAI_"] {
      background: #e8f5e8;
      font-weight: 500;
    }

    #results-table th[data-column^="VectaAI_"] {
      background: #004977;
      color: white;
    }

    @media (max-width: 768px) {
      .main-content {
        padding: 15px;
      }

      .config-grid {
        grid-template-columns: 1fr;
        gap: 15px;
      }

      .input-row {
        grid-template-columns: 1fr;
      }


      .header h1 {
        font-size: 1.8em;
      }

      .container {
        margin: 10px;
        border-radius: 15px;
      }
    }
  </style>
</head>
<body>
  <!-- Navigation Bar -->
  <nav class="nav-bar">
    <div class="nav-container">
      <div class="nav-brand">
        <a href="/" class="nav-logo">
          Vecta AI
          <div class="nav-subtitle">MEDICAL ANALYSIS PLATFORM</div>
        </a>
      </div>
      <ul class="nav-links">
        <li><a href="/" class="nav-link active">Main App</a></li>
        <li><a href="/validate" class="nav-link">Validator</a></li>
        <li><a href="/learning" class="nav-link">Learning Dashboard</a></li>
      </ul>
    </div>
  </nav>

  <div class="container">
    <div class="main-card">
      <div class="header">
        <h1>Vecta AI - Medical Analysis Platform</h1>
        <br>
      <div id="serviceStatus" class="status-indicator status-loading">Checking Service Status...</div>
    </div>

    <div class="disclaimer">
      <strong>Medical Disclaimer:</strong> This AI tool is for research and educational purposes only. All analyses must be reviewed by qualified medical professionals before any clinical use.
    </div>

    <div class="main-content">
      <!-- Row 1: Configuration -->
      <div class="config-row">
        <h2 class="section-title">Vecta AI Analysis Configuration</h2>
        <form id="analysisForm">
          <div class="config-grid">
            <div class="form-group">
              <label class="form-label" for="analysisType">Analysis Type:</label>
              <select id="analysisType" class="form-select" name="analysisType">
                <option value="epilepsy">Epilepsy Classification</option>
                <option value="classification">General Classification</option>
                <option value="diagnosis">Diagnosis Support</option>
                <option value="summary">Summarization</option>
                <option value="extraction">Information Extraction</option>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label" for="specialty">Neurology Specialty:</label>
              <select id="specialty" class="form-select" name="specialty">
                <option value="">General Neurology</option>
                <option value="epilepsy">Epilepsy</option>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label" for="prompt">Vecta AI Analysis Prompt:</label>
              <textarea id="prompt" class="form-textarea" name="prompt" 
                        placeholder="Select an analysis type to auto-populate prompt or enter custom prompt..." 
                        rows="2" required style="min-height: 60px;"></textarea>
            </div>
          </div>

          <!-- Row 2: Input Methods -->
          <div class="input-row">
            <div class="input-box">
              <h3 class="section-title" style="font-size: 1.1em;">Upload Medical Document</h3>
              <div class="file-upload-area" id="fileUploadArea">
                <input type="file" id="fileUpload" class="file-input" 
                       accept=".txt,.pdf,.docx,.xlsx,.csv,.json">
                <div class="upload-icon">Document</div>
                <div>
                  <strong>Click to upload</strong> or drag and drop<br>
                  <small>PDF, DOCX, Excel, CSV, TXT, JSON</small>
                </div>
              </div>
              <div id="fileInfo" class="file-info"></div>
            </div>

            <div class="input-box">
              <h3 class="section-title" style="font-size: 1.1em;">Enter Text Directly</h3>
              <textarea id="directText" class="form-textarea" name="directText" 
                        placeholder="Paste clinical text, patient notes, or medical information here..." 
                        rows="8" style="height: 200px;"></textarea>
            </div>
          </div>

          <button type="submit" class="analyze-btn" id="analyzeBtn" style="width: 100%; margin-top: 20px;">
            Analyze with Vecta AI
          </button>
        </form>
      </div>

      <!-- Row 3: Results (Larger) -->
      <div class="results-section">
        <h2 class="section-title">Vecta AI Analysis Results</h2>
        
        <div id="results">
          <div style="text-align: center; padding: 40px; color: #7f8c8d;">
            <div style="font-size: 3em; margin-bottom: 15px;">Medical Analysis</div>
            <p>Upload a document or enter text to begin Vecta AI medical analysis</p>
            <p style="font-size: 0.9em; margin-top: 10px; color: #004977;">Now with optimized clinical reasoning prompts</p>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="loading-overlay" id="loadingOverlay">
    <div class="loading-content">
      <div class="spinner"></div>
      <h3>Processing with Vecta AI...</h3>
      <p>Applying optimized clinical reasoning prompts</p>
    </div>
  </div>

  <script>
    // Analysis type to prompt mapping
    const analysisPrompts = {
      epilepsy: `EPILEPSY CLASSIFICATION (ILAE 2017) - HIERARCHICAL ANALYSIS

CLASSIFICATION COLUMNS TO EVALUATE:
1. Focal Epilepsy
2. Generalized Epilepsy
3. Combined Generalized & Focal Epilepsy
4. Unknown Onset Epilepsy

STEP 1: Determine if this is epilepsy
- Analyze clinical presentation, seizure history, EEG findings
- If NOT epilepsy: State "Not Epilepsy" in Classification and stop
- If epilepsy: Continue to STEP 2

STEP 2: Classify into primary category (CHOOSE ONE COLUMN):
- FOCAL EPILEPSY: Seizures originating from one brain region
  → Evidence: Focal EEG abnormalities, focal onset symptoms, focal imaging findings
  → Subtypes: Focal Aware, Focal Impaired Awareness
  → Motor vs Non-motor onset
  
- GENERALIZED EPILEPSY: Seizures affecting both hemispheres from onset
  → Evidence: Bilateral synchronous EEG, bilateral symmetric symptoms
  → Subtypes: Tonic-clonic, Absence, Myoclonic, Atonic, Clonic, Tonic
  
- COMBINED GENERALIZED & FOCAL: Both focal and generalized seizures present
  → Evidence: History of both focal and generalized seizure types
  → Document both seizure types
  
- UNKNOWN ONSET EPILEPSY: Insufficient evidence to determine onset
  → Use when data is limited or conflicting

STEP 3: Specify seizure subtype (if sufficient evidence exists)
- For Focal: Specify motor/non-motor, aware/impaired awareness
- For Generalized: Specify exact type (tonic-clonic, absence, myoclonic, etc.)
- If evidence insufficient: Stop at category level

MANDATORY OUTPUT FORMAT (4 bullet points, max 25 words each):
- Classification: [Category (Focal/Generalized/Combined/Unknown) + subtype if evidence supports]
- Clinical_Confidence: [High/Medium/Low based on available evidence]
- Evidence: [Key clinical/EEG/imaging findings supporting this category]
- Medication_Analysis: [AED recommendations for identified epilepsy type]

CRITICAL: Only classify to the level supported by evidence. State limitations clearly.`,

      classification: `MANDATORY FORMAT: Respond with exactly 4 bullet points, max 25 words each.

- Classification: [Your clinical reasoning for this classification task]
- Clinical_Confidence: [High/Medium/Low based on evidence]
- Evidence: [Key supporting evidence from provided data]
- Medication_Analysis: [Treatment recommendations with medical reasoning]

Apply your medical training for evidence-based classification.`,

      diagnosis: `MANDATORY FORMAT: Respond with exactly 4 bullet points, max 25 words each.

- Diagnosis Support: [Differential diagnosis and primary diagnosis reasoning]
- Clinical_Confidence: [High/Medium/Low based on clinical evidence]
- Evidence: [Key diagnostic findings from provided data]
- Medication_Analysis: [Treatment recommendations based on diagnosis]

Apply comprehensive diagnostic protocols for clinical analysis.`,

      summary: `MANDATORY FORMAT: Respond with exactly 4 bullet points, max 25 words each.

- Summarization: [Clinical summary with key findings]
- Clinical_Confidence: [High/Medium/Low based on documentation]
- Evidence: [Critical information from medical record]
- Medication_Analysis: [Medication-related summary and recommendations]

Apply clinical documentation standards for comprehensive summarization.`,

      extraction: `MANDATORY FORMAT: Respond with exactly 4 bullet points, max 25 words each.

- Information Extraction: [Key medical information identified]
- Clinical_Confidence: [High/Medium/Low based on data quality]
- Evidence: [Specific data points extracted from source]
- Medication_Analysis: [Medication information and recommendations]

Apply medical information extraction expertise using clinical standards.`
    };

    // Specialty-specific prompt enhancements
    const specialtyContext = {
      epilepsy_focal: `FOCAL EPILEPSY ANALYSIS (ILAE 2017):
Apply focal seizure classification: aware vs impaired awareness, motor vs non-motor onset.
Consider: Focal seizure semiology, EEG localization, structural lesions, AED selection for focal epilepsy.`,

      epilepsy_generalized: `GENERALIZED EPILEPSY ANALYSIS (ILAE 2017):
Apply generalized seizure classification: motor (tonic-clonic, absence, myoclonic) vs non-motor.
Consider: Generalized spike-wave patterns, genetic factors, broad-spectrum AEDs, syndrome classification.`,

      epilepsy_combined: `COMBINED EPILEPSY ANALYSIS (ILAE 2017):
Analyze both focal and generalized seizure types in the same patient.
Consider: Mixed seizure semiology, complex EEG patterns, dual-action AED selection.`,

      epilepsy_unknown: `UNKNOWN ONSET EPILEPSY ANALYSIS (ILAE 2017):
Analyze cases with insufficient information for classification.
Consider: Limited clinical data, ambiguous EEG findings, broad-spectrum AED coverage.`,

      stroke: `STROKE & CEREBROVASCULAR ANALYSIS:
Apply NIHSS scoring, imaging interpretation (CT/MRI), thrombolytic criteria, hemorrhagic vs ischemic classification.`,

      parkinsons: `PARKINSON'S DISEASE ANALYSIS:
Apply MDS-UPDRS criteria, motor/non-motor symptoms, dopaminergic therapy, disease staging.`,

      migraine: `MIGRAINE & HEADACHE ANALYSIS:
Apply ICHD-3 criteria, migraine classification, trigger identification, prophylactic vs abortive therapy.`,

      dementia: `DEMENTIA & COGNITIVE ANALYSIS:
Apply cognitive assessment, dementia subtype classification, biomarker interpretation, treatment strategies.`,

      ms: `MULTIPLE SCLEROSIS ANALYSIS:
Apply McDonald criteria, relapsing vs progressive MS, MRI findings, disease-modifying therapy.`,

      neuropathy: `NEUROPATHY ANALYSIS:
Apply neuropathy classification, EMG/NCS interpretation, etiology determination, treatment approach.`
    };

    // DOM elements
    const form = document.getElementById('analysisForm');
    const promptTextarea = document.getElementById('prompt');
    const analysisTypeSelect = document.getElementById('analysisType');
    const specialtySelect = document.getElementById('specialty');
    const fileUpload = document.getElementById('fileUpload');
    const fileUploadArea = document.getElementById('fileUploadArea');
    const fileInfo = document.getElementById('fileInfo');
    const directText = document.getElementById('directText');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const results = document.getElementById('results');
    const loadingOverlay = document.getElementById('loadingOverlay');
    const serviceStatus = document.getElementById('serviceStatus');

    // Initialize
    document.addEventListener('DOMContentLoaded', function() {
      checkServiceStatus();
      setupEventListeners();
    });

    function checkServiceStatus() {
      const baseUrl = window.location.origin + window.location.pathname.replace(/\/$/, '');
      const healthUrl = baseUrl + '/health';
      
      fetch(healthUrl)
        .then(response => {
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
          }
          return response.json();
        })
        .then(data => {
          updateServiceStatus(data);
        })
        .catch(error => {
          console.error('Health check error:', error);
          serviceStatus.textContent = `Vecta AI Service Error: ${error.message}`;
          serviceStatus.className = 'status-indicator status-error';
        });
    }

    function updateServiceStatus(healthData) {
      if (healthData.model_loaded) {
        serviceStatus.textContent = '';
        serviceStatus.className = 'status-indicator status-healthy';
        serviceStatus.style.display = 'none';
        analyzeBtn.disabled = false;
      } else if (healthData.load_error) {
        serviceStatus.textContent = `Vecta AI Error: ${healthData.load_error}`;
        serviceStatus.className = 'status-indicator status-error';
        analyzeBtn.disabled = true;
      } else {
        serviceStatus.textContent = 'Loading Vecta AI Model...';
        serviceStatus.className = 'status-indicator status-loading';
        analyzeBtn.disabled = true;
        setTimeout(checkServiceStatus, 5000);
      }
    }

    function setupEventListeners() {
      // File upload handling
      fileUpload.addEventListener('change', handleFileSelect);
      
      // Drag and drop
      fileUploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        fileUploadArea.classList.add('dragover');
      });
      
      fileUploadArea.addEventListener('dragleave', () => {
        fileUploadArea.classList.remove('dragover');
      });
      
      fileUploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        fileUploadArea.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
          fileUpload.files = files;
          handleFileSelect({ target: { files: files } });
        }
      });

      // Auto-populate prompt when analysis type or specialty changes
      analysisTypeSelect.addEventListener('change', updatePrompt);
      specialtySelect.addEventListener('change', updatePrompt);

      // Form submission
      form.addEventListener('submit', handleFormSubmit);
      
      // Initialize with default prompt
      updatePrompt();
    }

    function updatePrompt() {
      const analysisType = analysisTypeSelect.value;
      
      // Auto-select Epilepsy specialty when Epilepsy Classification is chosen
      if (analysisType === 'epilepsy') {
        specialtySelect.value = 'epilepsy';
      }
      
      const specialty = specialtySelect.value;
      
      // Get base prompt for analysis type
      let prompt = analysisPrompts[analysisType] || analysisPrompts.classification;
      
      // Add specialty-specific context if selected
      if (specialty && specialtyContext[specialty]) {
        prompt = specialtyContext[specialty] + '\n\n' + prompt;
      }
      
      // Update prompt textarea
      promptTextarea.value = prompt;
    }

    function handleFileSelect(event) {
      const file = event.target.files[0];
      if (file) {
        const size = (file.size / 1024 / 1024).toFixed(2);
        const ext = file.name.split('.').pop().toLowerCase();
        const isTabular = ['csv', 'xlsx', 'xls'].includes(ext);
        
        fileInfo.innerHTML = `
          <strong>Selected:</strong> ${file.name}<br>
          <strong>Size:</strong> ${size} MB<br>
          <strong>Type:</strong> ${file.type || 'Unknown'}<br>
          ${isTabular ? '<strong>Format:</strong> <span style="color: #004977;">Tabular Data - Vecta AI Enhanced Analysis Available</span>' : ''}
        `;
        fileInfo.style.display = 'block';
      }
    }

    function handleFormSubmit(event) {
      event.preventDefault();
      
      const formData = new FormData();
      formData.append('prompt', promptTextarea.value.trim());
      formData.append('analysisType', analysisTypeSelect.value);
      formData.append('specialty', specialtySelect.value);
      formData.append('directText', directText.value.trim());
      formData.append('userId', 'web-user');

      if (fileUpload.files[0]) {
        formData.append('file', fileUpload.files[0]);
      }

      const hasFile = fileUpload.files[0];
      const hasDirectText = directText.value.trim();

      if (!hasFile && !hasDirectText) {
        displayError('Please either upload a file or enter text directly.');
        return;
      }

      if (!promptTextarea.value.trim()) {
        displayError('Please enter an analysis prompt for Vecta AI.');
        return;
      }

      showLoading(true);
      analyzeBtn.disabled = true;

      const baseUrl = window.location.origin + window.location.pathname.replace(/\/$/, '');
      const analyzeUrl = baseUrl + '/analyze';

      fetch(analyzeUrl, {
        method: 'POST',
        body: formData
      })
      .then(response => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return response.json();
      })
      .then(data => {
        if (data.success) {
          displayResults(data);
        } else {
          displayError(data.error || 'Vecta AI analysis failed');
        }
      })
      .catch(error => {
        console.error('Vecta AI analysis error:', error);
        displayError(`Vecta AI analysis failed: ${error.message}`);
      })
      .finally(() => {
        showLoading(false);
        analyzeBtn.disabled = false;
      });
    }

    function showLoading(show) {
      loadingOverlay.style.display = show ? 'block' : 'none';
    }

    function displayError(message) {
      results.innerHTML = `
        <div class="alert alert-error">
          ERROR: ${message}
        </div>
      `;
    }

    function displayResults(data) {
      const tokensPerSec = data.tokens_generated && data.execution_time ? 
        (data.tokens_generated / data.execution_time).toFixed(1) : 'N/A';

      let resultsHTML = `
        <div class="alert alert-success">
          Analysis completed in ${data.execution_time?.toFixed(2) || 'N/A'} seconds
          ${data.validation_notes ? `<br><small style="color: #004977;">INFO: ${data.validation_notes}</small>` : ''}
        </div>
        
        <div class="result-card">
          <div class="result-header">
            Vecta AI Analysis Results ${data.is_tabular ? '(Tabular Data)' : ''}
            <small style="font-weight: normal;">${data.prompt_version || 'Enhanced'}</small>
          </div>
          <div class="result-content">${data.analysis || 'No analysis provided'}</div>
          
          <div class="result-meta">
            <div class="meta-item">
              <span class="meta-value">${data.execution_time?.toFixed(2) || 'N/A'}s</span>
              <span class="meta-label">Processing Time</span>
            </div>
            <div class="meta-item">
              <span class="meta-value">${data.tokens_generated || 'N/A'}</span>
              <span class="meta-label">Tokens Generated</span>
            </div>
            <div class="meta-item">
              <span class="meta-value">${tokensPerSec}/s</span>
              <span class="meta-label">Tokens per Second</span>
            </div>
            <div class="meta-item">
              <span class="meta-value">${data.model_used?.split('/').pop() || 'Vecta AI'}</span>
              <span class="meta-label">Enhanced Model</span>
            </div>
          </div>
        </div>
      `;

      // Add enhanced tabular output section if available
      if (data.tabular_output) {
        resultsHTML += `
          <div class="result-card" style="margin-top: 20px;">
            <div class="result-header">
              Enhanced Dataset with Vecta AI Analysis
              <div style="font-size: 0.8em; font-weight: normal;">
                ${data.tabular_output.shape[0]} rows × ${data.tabular_output.shape[1]} columns
              </div>
            </div>
            
            <div style="margin: 15px 0;">
              <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <button onclick="copyTableData('csv')" class="copy-btn" style="background: #004977;">
                  Copy as CSV
                </button>
                <button onclick="copyTableData('json')" class="copy-btn" style="background: #00A9E0;">
                  Copy as JSON
                </button>
                <button onclick="downloadTable('csv')" class="copy-btn" style="background: #666;">
                  Download CSV
                </button>
                <button onclick="downloadTable('excel')" class="copy-btn" style="background: #999;">
                  Download Excel
                </button>
              </div>
            </div>
            
            <div class="tabular-output-container">
              <div class="table-scroll">
                ${data.tabular_output.html}
              </div>
            </div>
            
            <div style="margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 5px; font-size: 0.9em;">
              <strong>New Vecta AI enhanced columns:</strong>
              <div style="margin-top: 5px;">
                ${data.tabular_output.columns.filter(col => col.startsWith('VectaAI_')).join(', ') || 'No Vecta AI columns added'}
              </div>
            </div>
          </div>
        `;
      }

      results.innerHTML = resultsHTML;

      // Store tabular data globally for copy/download functions
      if (data.tabular_output) {
        window.currentTabularData = data.tabular_output;
      }
    }

    // Tabular data handling functions
    function copyTableData(format) {
      if (!window.currentTabularData) {
        alert('No tabular data available to copy');
        return;
      }
      
      let textToCopy = '';
      
      switch(format) {
        case 'csv':
          textToCopy = window.currentTabularData.csv;
          break;
        case 'json':
          textToCopy = JSON.stringify(JSON.parse(window.currentTabularData.json), null, 2);
          break;
        default:
          textToCopy = window.currentTabularData.csv;
      }
      
      navigator.clipboard.writeText(textToCopy).then(() => {
        const btn = event.target;
        const originalText = btn.textContent;
        btn.textContent = 'Copied!';
        btn.style.background = '#004977';
        
        setTimeout(() => {
          btn.textContent = originalText;
          btn.style.background = format === 'csv' ? '#004977' : '#00A9E0';
        }, 2000);
      }).catch(err => {
        console.error('Failed to copy data:', err);
        alert('Failed to copy data to clipboard');
      });
    }

    function downloadTable(format) {
      if (!window.currentTabularData) {
        alert('No tabular data available to download');
        return;
      }
      
      let data, filename, mimeType;
      
      switch(format) {
        case 'csv':
        case 'excel':
          data = window.currentTabularData.csv;
          filename = `med42_enhanced_analysis_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.csv`;
          mimeType = 'text/csv';
          break;
        default:
          data = window.currentTabularData.csv;
          filename = `med42_enhanced_analysis_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.csv`;
          mimeType = 'text/csv';
      }
      
      const blob = new Blob([data], { type: mimeType });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    }
  </script>
    </div> <!-- End main-card -->
  </div> <!-- End container -->
</body>
</html>"""

# Route definitions
@app.route("/", methods=["GET"])
def index():
    return render_template_string(UI_HTML)

@app.route("/learning", methods=["GET"])
def learning_dashboard():
    """Learning metrics and self-improvement dashboard"""
    return render_template_string(LEARNING_DASHBOARD_HTML)

@app.route("/test", methods=["GET"])
def test():
    return jsonify({
        "status": "ok",
        "message": "Vecta AI service is running",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0-enhanced-prompting",
        "prompt_engine": "Vecta-AI-Optimized"
    })

@app.route("/health", methods=["GET"])
def health():
    try:
        if not svc.model_loaded and not svc.load_error:
            # Try to load model if not attempted
            svc.load_model()
        
        _ur, _ufs = inference_augmentation_flags()
        _cuda = bool(torch and torch.cuda.is_available())
        _rag_ready = rag_system is not None and getattr(rag_system, "available", False)
        _req_gpu = inference_require_gpu()
        return jsonify({
            "status": "healthy" if svc.model_loaded else "loading",
            "model_loaded": svc.model_loaded,
            "load_error": svc.load_error,
            "device": svc.device,
            "cuda_available": _cuda,
            "use_rag": _ur,
            "use_few_shot": _ufs,
            "rag_backend_ready": _rag_ready,
            "vecta_require_gpu": _req_gpu,
            "inference_signals": {
                "gpu_active": svc.device == "cuda",
                "cuda_available": _cuda,
                "rag_requested": _ur,
                "rag_runtime_ready": _ur and _rag_ready,
                "few_shot_requested": _ufs,
                "gpu_requirement_met": (not _req_gpu) or _cuda,
            },
            "model_name": svc.model_name,
            "prompt_engine": "Vecta-AI-Optimized",
            "stats": svc.stats,
            "queue_size": svc.request_queue.qsize(),
            "max_concurrent": app.config["MAX_CONCURRENT_REQUESTS"],
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "model_loaded": False,
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route("/api/learning/metrics", methods=["GET"])
def learning_metrics():
    """Get learning and improvement metrics"""
    try:
        from learning.learning_engine import LearningEngine
        engine = LearningEngine()
        metrics = engine.calculate_improvement_metrics()
        
        # Add learning history
        if Path(APP_HOME) / "data" / "learning_history.json" in Path(APP_HOME).rglob("learning_history.json"):
            with open(Path(APP_HOME) / "data" / "learning_history.json", 'r') as f:
                history = json.load(f)
                metrics['learning_history'] = history
        
        return jsonify({
            "success": True,
            "metrics": metrics,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Learning metrics error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/learning/trigger", methods=["POST"])
def trigger_learning():
    """Manually trigger a learning cycle"""
    try:
        from learning.learning_engine import LearningEngine
        engine = LearningEngine()
        result = engine.run_learning_cycle()
        
        return jsonify({
            "success": True,
            "result": result,
            "message": f"Learning cycle completed - added {result['examples_added']} new examples"
        })
    except Exception as e:
        logger.error(f"Learning trigger error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/learning/reload", methods=["POST"])
def reload_examples():
    """Reload few-shot examples after learning"""
    try:
        global few_shot_loader
        if few_shot_loader:
            few_shot_loader.reload()
            logger.info("Few-shot examples and guideline cache reloaded after learning cycle")
        else:
            from utils.few_shot_loader import FewShotExampleLoader
            few_shot_loader = FewShotExampleLoader()
            logger.info("Few-shot loader initialized on reload")
        
        return jsonify({
            "success": True,
            "message": "Few-shot examples reloaded successfully"
        })
    except Exception as e:
        logger.error(f"Reload examples error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/analyze", methods=['POST'])
def analyze():
    request_start = time.time()
    logger.info(f"Vecta AI Enhanced analyze endpoint called from {request.remote_addr}")
    
    try:
        # Validate request
        validation_errors = validate_analyze_request()
        if validation_errors:
            error_msg = "; ".join(validation_errors)
            logger.warning(f"Vecta AI request validation failed: {error_msg}")
            return jsonify({"success": False, "error": error_msg}), 400

        # Lazy load model
        if not svc.model_loaded:
            logger.info("Vecta AI model not loaded, attempting to load...")
            if not svc.load_model():
                error_msg = f"Vecta AI model failed to load: {svc.load_error}"
                logger.error(error_msg)
                return jsonify({"success": False, "error": error_msg}), 503

        # Get form data
        prompt = request.form.get("prompt", "").strip()
        analysis_type = request.form.get("analysisType", "custom").strip()  
        specialty = request.form.get("specialty", "").strip() or None
        direct_text = request.form.get("directText", "").strip()
        user_id = request.form.get("userId", "anonymous")

        # Handle text input with enhanced Vecta AI processing
        text = ""
        text_source = ""
        tabular_data = None

        if "file" in request.files and request.files["file"].filename:
            f = request.files["file"]
            filename = secure_filename(f.filename)
            logger.info(f"Processing uploaded file for Vecta AI: {filename}")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix="."+filename.rsplit(".",1)[1]) as tmp:
                f.save(tmp.name)
                
                extraction_result = _extract_tabular_text(tmp.name, filename)
                text = extraction_result["text"]
                tabular_data = extraction_result
                text_source = f"file: {filename}"
                
            try: 
                os.unlink(tmp.name)
            except OSError: 
                pass
                
        elif direct_text:
            text = direct_text
            text_source = "direct input"
            # Check if direct text looks like tabular data
            if '\t' in direct_text or ',' in direct_text:
                try:
                    df = pd.read_csv(StringIO(direct_text))
                    if len(df.columns) > 1:
                        tabular_analysis = _analyze_tabular_data(df, prompt, analysis_type)
                        tabular_data = {
                            "text": text,
                            "dataframe": df,
                            "is_tabular": True,
                            "tabular_data": tabular_analysis
                        }
                        logger.info(f"Vecta AI detected tabular data in direct input: {df.shape}")
                except Exception:
                    pass
        else:
            logger.error("No text input found for Vecta AI analysis")
            return jsonify({
                "success": False, 
                "error": "No text provided for Vecta AI analysis. Please enter text or upload a file."
            }), 400

        logger.info(f"Vecta AI text source: {text_source}")
        logger.info(f"Vecta AI final text length: {len(text)} characters")
        logger.info(f"Vecta AI is tabular: {tabular_data is not None and tabular_data.get('is_tabular', False)}")
        logger.info(f"Vecta AI specialty focus: {specialty or 'General'}")

        if not text or not text.strip():
            logger.error(f"Empty text after processing for Vecta AI. Source: {text_source}")
            return jsonify({
                "success": False,
                "error": f"No analyzable text found from {text_source} for Vecta AI analysis"
            }), 400

        try:
            res = svc.analyze(prompt, text, analysis_type, user_id, tabular_data, specialty)
            logger.info(f"Vecta AI enhanced analysis completed successfully for user {user_id}")
            
            # Save to validation database (10% sampling for validation)
            try:
                import random
                from core.database import get_db
                
                if random.random() < 0.10:  # 10% sample rate
                    with get_db() as db:
                        # Extract structured output if available
                        response_text = res.get('response', '')
                        ai_classification = ""
                        ai_confidence = ""
                        ai_evidence = ""
                        ai_medication = ""
                        
                        # Try to extract bullet points
                        if '• Classification:' in response_text or '- Classification:' in response_text:
                            lines = response_text.split('\n')
                            for line in lines:
                                if 'Classification:' in line:
                                    ai_classification = line.split(':', 1)[1].strip() if ':' in line else ""
                                elif 'Confidence:' in line or 'Clinical_Confidence:' in line:
                                    ai_confidence = line.split(':', 1)[1].strip() if ':' in line else ""
                                elif 'Evidence:' in line:
                                    ai_evidence = line.split(':', 1)[1].strip() if ':' in line else ""
                                elif 'Medication' in line:
                                    ai_medication = line.split(':', 1)[1].strip() if ':' in line else ""
                        
                        # Detect condition from text
                        detected_condition = svc._detect_condition(text, specialty) if hasattr(svc, '_detect_condition') else None
                        
                        db.execute("""
                            INSERT INTO ai_outputs (
                                input_text, input_type, condition, specialty,
                                ai_classification, ai_confidence, ai_evidence, 
                                ai_medication_analysis, ai_full_response,
                                model_version, selected_for_validation,
                                selection_date, session_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
                        """, (
                            text[:1000],  # Limit input text length
                            analysis_type,
                            detected_condition,
                            specialty or 'neurology',
                            ai_classification,
                            ai_confidence,
                            ai_evidence,
                            ai_medication,
                            response_text,
                            '2.0-enhanced',
                            True,  # Selected for validation
                            user_id
                        ))
                        db.commit()
                        logger.info(f"[OK] Saved output for validation (ID: {db.execute('SELECT last_insert_rowid()').fetchone()[0]})")
            except Exception as e:
                # Don't fail the request if validation save fails
                logger.warning(f"Failed to save for validation: {e}")
            
            response_data = {"success": True, **res}
            response = jsonify(response_data)
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response
            
        except Exception as e:
            error_msg = f"Vecta AI analysis failed: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return jsonify({"success": False, "error": error_msg}), 500
            
    except Exception as e:
        error_msg = f"Unexpected error in Vecta AI analyze endpoint: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": "Internal server error"}), 500
    
    finally:
        request_duration = time.time() - request_start
        logger.info(f"Vecta AI request completed in {request_duration:.2f}s")

if __name__ == "__main__":
    import argparse

    _cli = argparse.ArgumentParser(add_help=True, description="Vecta AI dev server")
    _cli.add_argument("--host", default=None, help="Bind address (sets SERVICE_HOST)")
    _cli.add_argument("--port", type=int, default=None, help="Port (sets SERVICE_PORT)")
    _args, _unknown = _cli.parse_known_args()
    if _args.host:
        os.environ["SERVICE_HOST"] = _args.host
    if _args.port is not None:
        os.environ["SERVICE_PORT"] = str(_args.port)

    logger.info("Starting Vecta AI service...")
    
    # Port selection logic: Default 8085, auto-find free port in 8085-8150 range
    host = os.environ.get("SERVICE_HOST", "0.0.0.0")
    
    try:
        from utils.port_finder import find_free_port
        default_port = int(os.environ.get("SERVICE_PORT", 8085))
        port = find_free_port(start_port=default_port, end_port=8150)
        
        if port != default_port:
            logger.info("Default port {} in use, using port {}".format(default_port, port))
    except Exception as e:
        logger.warning("Port finder not available: {}".format(e))
        port = int(os.environ.get("SERVICE_PORT", 8085))
    
    # Save PID file for stop script
    pid_file = os.path.join(APP_HOME, "vecta_ai.pid")
    try:
        with open(pid_file, 'w') as f:
            f.write("{}:{}".format(os.getpid(), port))
        logger.info("PID file created: {}".format(pid_file))
    except Exception as e:
        logger.warning("Could not create PID file: {}".format(e))
    
    logger.info("Loading Vecta AI model with enhanced prompting on startup...")

    if svc.load_model():
        logger.info("Vecta AI model loaded successfully with optimized prompting!")
    else:
        logger.warning("Vecta AI model loading failed: {}".format(svc.load_error))
        logger.info("Vecta AI service will continue - model loading will be attempted on first request")
    
    logger.info("Starting Vecta AI server on {}:{}".format(host, port))
    logger.info("Access URLs:")
    logger.info("  Main App:   http://localhost:{}".format(port))
    logger.info("  Validator:  http://localhost:{}/validate".format(port))

    try:
        app.run(host=host, port=port, debug=False, threaded=True)
    finally:
        # Clean up PID file on shutdown
        try:
            if os.path.exists(pid_file):
                os.remove(pid_file)
                logger.info("PID file removed")
        except Exception:
            pass

