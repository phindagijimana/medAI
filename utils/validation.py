"""
Validation utilities for Med42 service
Input validation, security checks, and data sanitization
"""

import re
from typing import List, Dict, Any


def validate_analyze_request(request) -> List[str]:
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

    return errors


def validate_file_upload(file_obj, filename: str, allowed_extensions: set, max_size: int) -> List[str]:
    """Validate file upload for security and compatibility"""
    errors = []

    if not filename:
        errors.append("No file selected")
        return errors

    # Check file extension
    if '.' not in filename:
        errors.append("File must have an extension")
        return errors

    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in allowed_extensions:
        errors.append(f"Unsupported file type .{ext}. Supported: {list(allowed_extensions)}")

    # Check file size
    file_obj.seek(0, 2)  # Seek to end
    size = file_obj.tell()
    file_obj.seek(0)  # Reset to beginning

    if size > max_size:
        errors.append(f"File too large ({size/1024/1024:.1f}MB). Maximum: {max_size/1024/1024:.0f}MB")

    return errors


def sanitize_medical_text(text: str, enable_phi_filtering: bool = True) -> str:
    """Sanitize medical text for logging and processing"""
    if not enable_phi_filtering:
        return text

    # PHI patterns to remove/replace
    patterns = [
        # SSN
        (r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]'),
        # Phone numbers
        (r'\b\d{3}-\d{3}-\d{4}\b', '[PHONE]'),
        # Email addresses
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),
        # Medical record numbers (common patterns)
        (r'\bMRN\s*\d{6,10}\b', '[MRN]'),
        (r'\b\d{8,12}\b(?=\s*(?:MRN|Patient|Record))', '[MRN]'),
    ]

    sanitized = text
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    return sanitized


def validate_medical_content(text: str) -> Dict[str, Any]:
    """Validate medical content for appropriateness"""
    validation_result = {
        "is_valid": True,
        "warnings": [],
        "content_type": "unknown",
        "word_count": 0,
        "has_medical_terms": False
    }

    # Basic content analysis
    word_count = len(text.split())
    validation_result["word_count"] = word_count

    if word_count < 10:
        validation_result["warnings"].append("Very short content - may not provide sufficient context for analysis")

    if word_count > 10000:
        validation_result["warnings"].append("Very long content - analysis may be truncated")

    # Check for medical terminology indicators
    medical_indicators = [
        'patient', 'diagnosis', 'treatment', 'medication', 'symptoms',
        'clinical', 'medical', 'health', 'disease', 'condition',
        'therapy', 'prescription', 'dosage', 'adverse'
    ]

    text_lower = text.lower()
    has_medical = any(term in text_lower for term in medical_indicators)
    validation_result["has_medical_terms"] = has_medical

    if not has_medical:
        validation_result["warnings"].append("Content may not contain medical information")

    # Determine content type
    if any(ext in text_lower for ext in ['.csv', 'dataframe', 'table']):
        validation_result["content_type"] = "tabular"
    elif any(ext in text_lower for ext in ['.pdf', '.docx', '.txt']):
        validation_result["content_type"] = "document"
    else:
        validation_result["content_type"] = "text"

    return validation_result


def hash_user_identifier(user_id: str) -> str:
    """Create a consistent hash for user identification without exposing PII"""
    import hashlib
    return hashlib.sha256(f"med42_user_{user_id}".encode()).hexdigest()[:16]


def validate_specialty(specialty: str) -> bool:
    """Validate medical specialty parameter"""
    valid_specialties = [
        "",  # General/empty
        "cardiology",
        "neurology",
        "psychiatry",
        "emergency",
        "internal_medicine"
    ]
    return specialty in valid_specialties



