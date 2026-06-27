#!/usr/bin/env python3
"""
Test script to demonstrate the complete learning loop
Adds validated cases and runs learning cycle
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from learning.learning_engine import LearningEngine
from core.database import get_db

def add_test_validated_cases():
    """Add test validated cases to demonstrate learning"""
    print("Adding test validated cases...")
    
    # First get or add a test neurologist
    with get_db() as db:
        # Check if test neurologist exists
        neurologist = db.execute("""
            SELECT id FROM neurologists 
            WHERE name = 'Dr. Test Validator' 
            LIMIT 1
        """).fetchone()
        
        if not neurologist:
            db.execute("""
                INSERT INTO neurologists (
                    id, name, email, specialty, certification_level, 
                    institution, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                'test_validator',
                'Dr. Test Validator',
                'test@medai.ai',
                'Epileptology',
                'board_certified_epileptologist',
                'MedAI Medical Center',
                True
            ))
            db.commit()
            neurologist_id = 'test_validator'
            print(f"[OK] Created test neurologist (ID: {neurologist_id})")
        else:
            neurologist_id = neurologist['id']
            print(f"[OK] Using existing neurologist (ID: {neurologist_id})")
        
        # Get AI outputs that need validation
        ai_outputs = db.execute("""
            SELECT id, input_text, condition, specialty,
                   ai_classification, ai_confidence, ai_evidence, 
                   ai_medication_analysis
            FROM ai_outputs 
            WHERE validation_status = 'pending'
            LIMIT 3
        """).fetchall()
        
        if not ai_outputs:
            print("[ERROR] No AI outputs available for validation")
            return 0
        
        # Add validations for these cases
        validated_count = 0
        for output in ai_outputs:
            try:
                # Create a high-quality validation
                db.execute("""
                    INSERT INTO validations (
                        output_id, neurologist_id, is_correct,
                        classification_correct, confidence_appropriate,
                        evidence_accurate, medication_appropriate,
                        confidence_level, comments, clinical_pearls,
                        neurologist_name, neurologist_specialty, 
                        certification_level
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    output['id'],
                    neurologist_id,
                    True,  # is_correct
                    True,  # classification_correct
                    True,  # confidence_appropriate
                    True,  # evidence_accurate
                    True,  # medication_appropriate
                    'high',  # confidence_level
                    f'Excellent analysis of {output["condition"]}. Clear evidence and appropriate clinical reasoning.',
                    f'Key teaching point: This case demonstrates classic presentation of {output["condition"]}. The AI correctly identified critical clinical features.',
                    'Dr. Test Validator',
                    'Epileptology',
                    'board_certified_epileptologist'
                ))
                
                # Update AI output status
                db.execute("""
                    UPDATE ai_outputs 
                    SET validation_status = 'validated'
                    WHERE id = ?
                """, (output['id'],))
                
                validated_count += 1
                print(f"[OK] Validated case {output['id']}: {output['condition']}")
                
            except Exception as e:
                print(f"[ERROR] Failed to validate case {output['id']}: {e}")
        
        db.commit()
        print(f"\n[OK] Added {validated_count} validated cases")
        return validated_count


def test_full_learning_cycle():
    """Test the complete learning cycle"""
    print("\n" + "="*70)
    print("TESTING MEDAI AI SELF-IMPROVEMENT LOOP")
    print("="*70)
    
    # Step 1: Add validated test cases
    print("\nStep 1: Adding validated test cases...")
    validated_count = add_test_validated_cases()
    
    if validated_count == 0:
        print("\n⚠️ No validated cases added. Cannot test learning cycle.")
        return
    
    # Step 2: Run learning cycle
    print("\nStep 2: Running learning cycle...")
    engine = LearningEngine()
    result = engine.run_learning_cycle()
    
    # Step 3: Show results
    print("\n" + "="*70)
    print("LEARNING CYCLE TEST RESULTS")
    print("="*70)
    print(f"Cases Processed: {result['cases_processed']}")
    print(f"Examples Added: {result['examples_added']}")
    print(f"Agreement Rate: {result['current_agreement_rate']*100:.1f}%")
    print(f"Total Validations: {result['total_validations']}")
    print(f"Duration: {result['duration_seconds']:.2f}s")
    
    print("\nComponent Accuracy:")
    for component, score in result['metrics']['component_accuracy'].items():
        print(f"  {component}: {score*100:.1f}%")
    
    print(f"\nLearnable Cases Available: {result['learnable_cases_remaining']}")
    print(f"Cases with Corrections: {result['metrics']['cases_with_corrections']}")
    print(f"Clinical Pearls: {result['metrics']['clinical_pearls_count']}")
    
    # Step 4: Check few-shot examples
    print("\n" + "="*70)
    print("CHECKING FEW-SHOT EXAMPLES")
    print("="*70)
    
    import json
    few_shot_path = Path(__file__).parent / "data" / "few_shot_examples.json"
    
    if few_shot_path.exists():
        with open(few_shot_path, 'r') as f:
            examples = json.load(f)
            
        if 'validated' in examples.get('neurology_few_shot_examples', {}):
            validated_examples = examples['neurology_few_shot_examples']['validated']
            print(f"[OK] Found {len(validated_examples)} validated examples in few-shot library")
            
            if validated_examples:
                print("\nMost recent validated example:")
                latest = validated_examples[-1]
                print(f"  ID: {latest['id']}")
                print(f"  Condition: {latest['condition']}")
                print(f"  Validated by: {latest['expert_feedback']['neurologist']}")
        else:
            print("⚠️ No validated examples found yet")
    
    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)
    
    if result['examples_added'] > 0:
        print("\n[OK] Self-improvement loop is working!")
        print("   - Validated cases extracted from database")
        print("   - Examples added to few-shot library")
        print("   - Ready for automatic learning on new validations")
    else:
        print("\n⚠️ No examples were added this cycle")
        print("   (This may be normal if examples already exist)")


if __name__ == "__main__":
    test_full_learning_cycle()
