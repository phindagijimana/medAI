#!/usr/bin/env python3
"""
Initialize Validation System with Demo Data
"""
import sys
import os
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import init_db, get_db

def add_demo_data():
    """Add some demo AI outputs for testing the validator"""
    print("\nAdding demo data for testing...")
    
    demo_cases = [
        {
            "input_text": "35-year-old female with history of brief staring spells lasting 10-15 seconds. EEG shows bilaterally synchronous 3Hz spike-and-wave complexes. Patient experiences loss of awareness with subtle motor arrest. No family history of seizures.",
            "input_type": "classification",
            "condition": "epilepsy",
            "ai_classification": "Generalized absence epilepsy with characteristic 3Hz spike-wave pattern per ILAE 2025",
            "ai_confidence": "High based on classic EEG findings and clinical semiology",
            "ai_evidence": "3Hz spike-wave on EEG, brief awareness loss, typical presentation",
            "ai_medication_analysis": "First-line: Ethosuximide or valproate. Avoid sodium channel blockers like carbamazepine which may worsen absence seizures",
            "ai_full_response": "Classification: Generalized absence epilepsy with characteristic 3Hz spike-wave pattern per ILAE 2025\nClinical_Confidence: High based on classic EEG findings and clinical semiology\nEvidence: 3Hz spike-wave on EEG, brief awareness loss, typical presentation\nMedication_Analysis: First-line: Ethosuximide or valproate. Avoid carbamazepine"
        },
        {
            "input_text": "68-year-old male with progressive rest tremor affecting right hand for 2 years. Bradykinesia and rigidity noted. Responds well to levodopa therapy. No cognitive impairment.",
            "input_type": "diagnosis",
            "condition": "parkinsons",
            "ai_classification": "Parkinson's disease with classic motor features",
            "ai_confidence": "High based on clinical triad and levodopa response",
            "ai_evidence": "Rest tremor, bradykinesia, rigidity, excellent levodopa response",
            "ai_medication_analysis": "Levodopa/carbidopa appropriate as first-line. Consider MAO-B inhibitor as adjunct",
            "ai_full_response": "Diagnosis Support: Parkinson's disease with classic motor features\nClinical_Confidence: High based on clinical triad and levodopa response\nEvidence: Rest tremor, bradykinesia, rigidity, excellent levodopa response\nMedication_Analysis: Levodopa/carbidopa appropriate. MAO-B inhibitor potential adjunct"
        },
        {
            "input_text": "72-year-old with sudden onset left hemiparesis 2 hours ago. NIHSS score 14. CT head shows no hemorrhage. BP 160/95. Patient alert and oriented.",
            "input_type": "classification",
            "condition": "stroke",
            "ai_classification": "Acute ischemic stroke, candidate for thrombolysis",
            "ai_confidence": "High based on timeline and imaging",
            "ai_evidence": "Sudden onset focal deficit, within window, no hemorrhage on CT",
            "ai_medication_analysis": "Consider IV tPA if no contraindications. Antiplatelet therapy after acute phase",
            "ai_full_response": "Classification: Acute ischemic stroke, candidate for thrombolysis\nClinical_Confidence: High based on timeline and imaging\nEvidence: Onset <4.5 hours, no hemorrhage\nMedication_Analysis: IV tPA candidate. Antiplatelet post-acute"
        },
        {
            "input_text": "45-year-old female with recurrent unilateral throbbing headaches lasting 4-72 hours. Associated with photophobia, phonophobia, and nausea. Relieved by triptans.",
            "input_type": "classification",
            "condition": "headache",
            "ai_classification": "Migraine without aura per ICHD-3 criteria",
            "ai_confidence": "High based on characteristic features",
            "ai_evidence": "Unilateral, throbbing, 4-72 hour duration, photo/phonophobia, triptan response",
            "ai_medication_analysis": "Acute: Triptans appropriate. Consider prophylaxis if >4 attacks/month",
            "ai_full_response": "Classification: Migraine without aura per ICHD-3 criteria\nClinical_Confidence: High based on characteristic features\nEvidence: Classic migraine features present\nMedication_Analysis: Triptans for acute. Prophylaxis if frequent"
        },
        {
            "input_text": "76-year-old with progressive memory loss over 3 years. MMSE 20/30. Difficulty with recent events and word-finding. ADLs partially impaired. MRI shows hippocampal atrophy.",
            "input_type": "diagnosis",
            "condition": "dementia",
            "ai_classification": "Alzheimer's disease, mild to moderate stage",
            "ai_confidence": "High based on clinical and imaging features",
            "ai_evidence": "Gradual onset, memory predominant, hippocampal atrophy on MRI",
            "ai_medication_analysis": "Consider cholinesterase inhibitor (donepezil, rivastigmine). Memantine for moderate stage",
            "ai_full_response": "Diagnosis Support: Alzheimer's disease, mild to moderate stage\nClinical_Confidence: High based on presentation and imaging\nEvidence: Progressive memory loss, hippocampal atrophy\nMedication_Analysis: Cholinesterase inhibitor + memantine appropriate"
        }
    ]
    
    with get_db() as db:
        for i, case in enumerate(demo_cases, 1):
            try:
                db.execute("""
                    INSERT INTO ai_outputs (
                        input_text, input_type, condition, specialty,
                        ai_classification, ai_confidence, ai_evidence,
                        ai_medication_analysis, ai_full_response,
                        model_version, validation_status, selected_for_validation,
                        validation_priority, session_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    case['input_text'],
                    case['input_type'],
                    case['condition'],
                    'neurology',
                    case['ai_classification'],
                    case['ai_confidence'],
                    case['ai_evidence'],
                    case['ai_medication_analysis'],
                    case['ai_full_response'],
                    '2.0-enhanced',
                    'pending',
                    True,
                    3,  # Medium priority
                    'demo_session'
                ))
                print(f"   [OK] Added demo case {i}: {case['condition']}")
            except Exception as e:
                print(f"   [ERROR] Failed to add case {i}: {e}")
        
        db.commit()
    
    print("\n[OK] Demo data added successfully!")

def main():
    print("="*70)
    print("MedAI Validation System - Initialization")
    print("="*70)
    
    # Initialize database
    print("\n1. Initializing database...")
    init_db()
    
    # Add demo data
    print("\n2. Adding demo validation cases...")
    add_demo_data()
    
    # Show summary
    print("\n" + "="*70)
    print("Summary")
    print("="*70)
    
    with get_db() as db:
        total_outputs = db.execute("SELECT COUNT(*) as count FROM ai_outputs").fetchone()['count']
        pending = db.execute("SELECT COUNT(*) as count FROM ai_outputs WHERE validation_status = 'pending'").fetchone()['count']
        neurologists = db.execute("SELECT COUNT(*) as count FROM neurologists").fetchone()['count']
        
        print(f"  Total AI outputs: {total_outputs}")
        print(f"  Pending validation: {pending}")
        print(f"  Neurologists: {neurologists}")
    
    print("\n" + "="*70)
    print("[OK] Validation system ready!")
    print("\nNext steps:")
    print("  1. Start the app: python app.py")
    print("  2. Main app: http://localhost:8080")
    print("  3. Validator: http://localhost:8080/validate")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
