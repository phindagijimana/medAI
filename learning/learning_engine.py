#!/usr/bin/env python3
"""
MedAI Self-Improvement Engine
Automatically learns from expert validations and updates prompts
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Paths
APP_DIR = Path(__file__).parent.parent  # Go up to root directory
DB_PATH = APP_DIR / "data" / "validation.db"
FEW_SHOT_PATH = APP_DIR / "data" / "few_shot_examples.json"
LEARNING_LOG_PATH = APP_DIR / "data" / "learning_history.json"


class LearningEngine:
    """MedAI Self-Improvement Engine"""
    
    def __init__(self, min_confidence_threshold=0.8, min_validations=1):
        """
        Initialize learning engine
        
        Args:
            min_confidence_threshold: Minimum neurologist confidence for learning (0.8 = High confidence)
            min_validations: Minimum validations per case before learning
        """
        self.min_confidence = min_confidence_threshold
        self.min_validations = min_validations
        self.learning_history = self._load_learning_history()
    
    def _load_learning_history(self) -> Dict:
        """Load learning history"""
        if LEARNING_LOG_PATH.exists():
            with open(LEARNING_LOG_PATH, 'r') as f:
                return json.load(f)
        return {
            "learning_events": [],
            "total_examples_added": 0,
            "last_learning_cycle": None,
            "agreement_rate_history": []
        }
    
    def _save_learning_history(self):
        """Save learning history"""
        with open(LEARNING_LOG_PATH, 'w') as f:
            json.dump(self.learning_history, indent=2, fp=f)
    
    def extract_validated_cases(self) -> List[Dict]:
        """Extract high-quality validated cases from database"""
        logger.info("Extracting validated cases for learning...")
        
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Query for cases with high-quality validation
        query = """
        SELECT 
            a.id,
            a.input_text,
            a.condition,
            a.specialty,
            a.input_type,
            a.ai_classification,
            a.ai_confidence,
            a.ai_evidence,
            a.ai_medication_analysis,
            v.is_correct,
            v.confidence_level,
            v.preferred_classification,
            v.preferred_confidence,
            v.preferred_evidence,
            v.preferred_medication,
            v.classification_correct,
            v.confidence_appropriate,
            v.evidence_accurate,
            v.medication_appropriate,
            v.comments,
            v.clinical_pearls,
            v.neurologist_name,
            v.neurologist_specialty,
            v.certification_level,
            v.validation_timestamp
        FROM ai_outputs a
        JOIN validations v ON a.id = v.output_id
        WHERE v.is_correct = TRUE
        AND (
            v.confidence_level = 'high'
            OR (v.classification_correct = TRUE 
                AND v.confidence_appropriate = TRUE
                AND v.evidence_accurate = TRUE
                AND v.medication_appropriate = TRUE)
        )
        ORDER BY v.validation_timestamp DESC
        """
        
        cases = cursor.execute(query).fetchall()
        conn.close()
        
        validated_cases = []
        for case in cases:
            case_dict = dict(case)
            
            # Use expert's preferred answers if provided, otherwise use AI's correct answers
            validated_cases.append({
                'id': f"validated_{case_dict['id']}_{datetime.now().strftime('%Y%m%d')}",
                'source': 'Expert Validated',
                'citation': f"Validated by {case_dict['neurologist_name']} ({case_dict['certification_level']})",
                'source_url': 'internal_validation',
                'condition': case_dict['condition'] or 'General',
                'specialty': case_dict['specialty'] or 'neurology',
                'input': case_dict['input_text'],
                'analysis_type': case_dict['input_type'] or 'classification',
                'expected_output': {
                    'classification': case_dict['preferred_classification'] or case_dict['ai_classification'],
                    'clinical_confidence': case_dict['preferred_confidence'] or case_dict['ai_confidence'],
                    'evidence': case_dict['preferred_evidence'] or case_dict['ai_evidence'],
                    'medication_analysis': case_dict['preferred_medication'] or case_dict['ai_medication_analysis']
                },
                'expert_feedback': {
                    'neurologist': case_dict['neurologist_name'],
                    'specialty': case_dict['neurologist_specialty'],
                    'certification': case_dict['certification_level'],
                    'comments': case_dict['comments'],
                    'clinical_pearls': case_dict['clinical_pearls'],
                    'validated_on': case_dict['validation_timestamp']
                },
                'quality_scores': {
                    'classification_correct': case_dict['classification_correct'],
                    'confidence_appropriate': case_dict['confidence_appropriate'],
                    'evidence_accurate': case_dict['evidence_accurate'],
                    'medication_appropriate': case_dict['medication_appropriate']
                }
            })
        
        logger.info(f"Extracted {len(validated_cases)} high-quality validated cases")
        return validated_cases
    
    def update_few_shot_examples(self, new_cases: List[Dict]) -> int:
        """Update few-shot examples with validated cases"""
        logger.info("Updating few-shot examples with validated cases...")
        
        # Load existing examples
        if FEW_SHOT_PATH.exists():
            with open(FEW_SHOT_PATH, 'r') as f:
                examples = json.load(f)
        else:
            examples = {"neurology_few_shot_examples": {}}
        
        # Create 'validated' category if doesn't exist
        if 'validated' not in examples['neurology_few_shot_examples']:
            examples['neurology_few_shot_examples']['validated'] = []
        
        # Track what we're adding
        added_count = 0
        existing_ids = {ex.get('id') for ex in examples['neurology_few_shot_examples'].get('validated', [])}
        
        for case in new_cases:
            if case['id'] not in existing_ids:
                # Add to validated category
                examples['neurology_few_shot_examples']['validated'].append(case)
                added_count += 1
                
                # Also add to specialty-specific category if exists
                specialty = case.get('specialty', 'neurology')
                condition = case.get('condition', '').lower().replace(' ', '_')
                
                # Try to add to condition-specific category
                for category in examples['neurology_few_shot_examples'].keys():
                    if condition in category.lower():
                        examples['neurology_few_shot_examples'][category].append(case)
                        break
        
        # Save updated examples
        if added_count > 0:
            # Backup existing file first
            if FEW_SHOT_PATH.exists():
                backup_path = FEW_SHOT_PATH.with_suffix('.json.backup')
                FEW_SHOT_PATH.rename(backup_path)
            
            with open(FEW_SHOT_PATH, 'w') as f:
                json.dump(examples, f, indent=2)
            
            logger.info(f"Added {added_count} new validated examples to few-shot library")
        else:
            logger.info("No new examples to add (all already exist)")
        
        return added_count
    
    def calculate_improvement_metrics(self) -> Dict[str, Any]:
        """Calculate learning and improvement metrics"""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Overall validation stats
        stats = {}
        
        # Total validations
        stats['total_validations'] = cursor.execute(
            "SELECT COUNT(*) as count FROM validations"
        ).fetchone()['count']
        
        # Agreement rate
        if stats['total_validations'] > 0:
            correct = cursor.execute(
                "SELECT COUNT(*) as count FROM validations WHERE is_correct = TRUE"
            ).fetchone()['count']
            stats['agreement_rate'] = round(correct / stats['total_validations'], 3)
        else:
            stats['agreement_rate'] = 0.0
        
        # Component accuracy
        stats['component_accuracy'] = {}
        for component in ['classification_correct', 'confidence_appropriate', 'evidence_accurate', 'medication_appropriate']:
            correct = cursor.execute(
                f"SELECT COUNT(*) as count FROM validations WHERE {component} = TRUE"
            ).fetchone()['count']
            stats['component_accuracy'][component] = round(correct / stats['total_validations'], 3) if stats['total_validations'] > 0 else 0.0
        
        # High-quality cases available for learning
        stats['learnable_cases'] = cursor.execute("""
            SELECT COUNT(*) as count FROM validations 
            WHERE is_correct = TRUE 
            AND confidence_level = 'high'
        """).fetchone()['count']
        
        # Cases with expert corrections
        stats['cases_with_corrections'] = cursor.execute("""
            SELECT COUNT(*) as count FROM validations 
            WHERE preferred_classification IS NOT NULL
            OR preferred_confidence IS NOT NULL
            OR preferred_evidence IS NOT NULL
            OR preferred_medication IS NOT NULL
        """).fetchone()['count']
        
        # Clinical pearls provided
        stats['clinical_pearls_count'] = cursor.execute("""
            SELECT COUNT(*) as count FROM validations 
            WHERE clinical_pearls IS NOT NULL AND clinical_pearls != ''
        """).fetchone()['count']
        
        conn.close()
        return stats
    
    def run_learning_cycle(self) -> Dict[str, Any]:
        """Execute a full learning cycle"""
        logger.info("=" * 70)
        logger.info("STARTING MEDAI AI LEARNING CYCLE")
        logger.info("=" * 70)
        
        cycle_start = datetime.now()
        
        # Step 1: Extract validated cases
        validated_cases = self.extract_validated_cases()
        
        # Step 2: Update few-shot examples
        added_count = self.update_few_shot_examples(validated_cases)
        
        # Step 3: Calculate metrics
        metrics = self.calculate_improvement_metrics()
        
        # Step 4: Record learning event
        learning_event = {
            'timestamp': cycle_start.isoformat(),
            'cases_reviewed': len(validated_cases),
            'examples_added': added_count,
            'agreement_rate': metrics['agreement_rate'],
            'learnable_cases': metrics['learnable_cases'],
            'metrics': metrics
        }
        
        self.learning_history['learning_events'].append(learning_event)
        self.learning_history['total_examples_added'] += added_count
        self.learning_history['last_learning_cycle'] = cycle_start.isoformat()
        self.learning_history['agreement_rate_history'].append({
            'timestamp': cycle_start.isoformat(),
            'rate': metrics['agreement_rate']
        })
        
        self._save_learning_history()
        
        cycle_end = datetime.now()
        duration = (cycle_end - cycle_start).total_seconds()
        
        result = {
            'success': True,
            'duration_seconds': duration,
            'cases_processed': len(validated_cases),
            'examples_added': added_count,
            'current_agreement_rate': metrics['agreement_rate'],
            'total_validations': metrics['total_validations'],
            'learnable_cases_remaining': metrics['learnable_cases'],
            'metrics': metrics,
            'timestamp': cycle_start.isoformat()
        }
        
        logger.info("=" * 70)
        logger.info(f"LEARNING CYCLE COMPLETE - Added {added_count} examples")
        logger.info(f"Agreement Rate: {metrics['agreement_rate']*100:.1f}%")
        logger.info(f"Duration: {duration:.2f}s")
        logger.info("=" * 70)
        
        return result


def run_learning_cycle_cli():
    """CLI interface for running learning cycle"""
    engine = LearningEngine()
    result = engine.run_learning_cycle()
    
    print("\n" + "=" * 70)
    print("MEDAI AI LEARNING CYCLE RESULTS")
    print("=" * 70)
    print(f"Cases Processed: {result['cases_processed']}")
    print(f"Examples Added: {result['examples_added']}")
    print(f"Agreement Rate: {result['current_agreement_rate']*100:.1f}%")
    print(f"Total Validations: {result['total_validations']}")
    print(f"Duration: {result['duration_seconds']:.2f}s")
    print("=" * 70)
    
    # Show component accuracy
    print("\nComponent Accuracy:")
    for component, score in result['metrics']['component_accuracy'].items():
        print(f"  {component}: {score*100:.1f}%")
    
    print(f"\nLearnable Cases Available: {result['learnable_cases_remaining']}")
    print(f"Cases with Expert Corrections: {result['metrics']['cases_with_corrections']}")
    print(f"Clinical Pearls Collected: {result['metrics']['clinical_pearls_count']}")
    print("")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1 and sys.argv[1] == '--metrics':
        # Just show metrics without learning
        engine = LearningEngine()
        metrics = engine.calculate_improvement_metrics()
        print(json.dumps(metrics, indent=2))
    else:
        # Run full learning cycle
        run_learning_cycle_cli()
