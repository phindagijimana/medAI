#!/usr/bin/env python3
"""
MedAI Auto-Learning Scheduler
Automatically runs learning cycles based on triggers
"""

import time
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from learning.learning_engine import LearningEngine
from core.database import get_db

try:
    import schedule
    SCHEDULE_AVAILABLE = True
except ImportError:
    SCHEDULE_AVAILABLE = False

logger = logging.getLogger(__name__)


class AutoLearningScheduler:
    """Automatic learning scheduler for MedAI"""
    
    def __init__(self):
        self.engine = LearningEngine()
        self.last_validation_count = 0
        
    def check_and_learn(self):
        """Check if new validations exist and trigger learning"""
        try:
            with get_db() as db:
                current_count = db.execute(
                    "SELECT COUNT(*) as count FROM validations WHERE is_correct = TRUE"
                ).fetchone()['count']
                
                # Trigger learning if new validations available
                if current_count > self.last_validation_count:
                    new_validations = current_count - self.last_validation_count
                    logger.info(f"New validations detected: {new_validations}")
                    logger.info("Triggering automatic learning cycle...")
                    
                    result = self.engine.run_learning_cycle()
                    
                    if result['examples_added'] > 0:
                        logger.info(f"[AUTO-LEARN] Successfully added {result['examples_added']} examples")
                        logger.info(f"[AUTO-LEARN] Current agreement rate: {result['current_agreement_rate']*100:.1f}%")
                    
                    self.last_validation_count = current_count
                else:
                    logger.debug("No new validations - skipping learning cycle")
                    
        except Exception as e:
            logger.error(f"Auto-learning check failed: {e}")
    
    def run_scheduled(self, interval_minutes=60):
        """Run scheduler with periodic checks"""
        if not SCHEDULE_AVAILABLE:
            logger.error("'schedule' module not available. Install with: pip3 install schedule")
            logger.info("Falling back to simple loop...")
            while True:
                self.check_and_learn()
                time.sleep(interval_minutes * 60)
            return
        
        logger.info(f"Starting auto-learning scheduler (check every {interval_minutes} minutes)")
        
        # Initial check
        self.check_and_learn()
        
        # Schedule periodic checks
        schedule.every(interval_minutes).minutes.do(self.check_and_learn)
        
        # Run forever
        while True:
            schedule.run_pending()
            time.sleep(60)
    
    def run_on_validation_trigger(self, validation_threshold=5):
        """Run learning when N new validations accumulate"""
        logger.info(f"Auto-learning will trigger every {validation_threshold} validations")
        
        while True:
            try:
                with get_db() as db:
                    current_count = db.execute(
                        "SELECT COUNT(*) as count FROM validations WHERE is_correct = TRUE"
                    ).fetchone()['count']
                    
                    if current_count >= self.last_validation_count + validation_threshold:
                        logger.info(f"Validation threshold reached: {current_count} validations")
                        result = self.engine.run_learning_cycle()
                        self.last_validation_count = current_count
                        
                        logger.info(f"[AUTO-LEARN] Learning cycle completed - added {result['examples_added']} examples")
                
                time.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Auto-learning trigger check failed: {e}")
                time.sleep(300)


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    
    scheduler = AutoLearningScheduler()
    
    # Parse arguments
    mode = sys.argv[1] if len(sys.argv) > 1 else 'check'
    
    if mode == 'scheduled':
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        scheduler.run_scheduled(interval_minutes=interval)
    elif mode == 'threshold':
        threshold = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        scheduler.run_on_validation_trigger(validation_threshold=threshold)
    elif mode == 'check':
        # One-time check
        scheduler.check_and_learn()
    else:
        print("Usage:")
        print("  python3 auto_learn_scheduler.py check          # Check once and learn if needed")
        print("  python3 auto_learn_scheduler.py scheduled 60   # Check every 60 minutes")
        print("  python3 auto_learn_scheduler.py threshold 5    # Learn every 5 validations")
