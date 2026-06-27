"""
Database setup for MedAI Validation System
"""
import sqlite3
import os
from pathlib import Path
from contextlib import contextmanager

# Database path (go up to root directory, then to data/)
DB_DIR = Path(__file__).parent.parent / "data"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "validation.db"


@contextmanager
def get_db():
    """Get database connection with context manager"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database with required tables"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Table: ai_outputs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_outputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                input_text TEXT NOT NULL,
                input_type VARCHAR(50),
                condition VARCHAR(100),
                specialty VARCHAR(50) DEFAULT 'neurology',
                
                -- AI Output
                ai_classification TEXT,
                ai_confidence TEXT,
                ai_evidence TEXT,
                ai_medication_analysis TEXT,
                ai_full_response TEXT,
                
                -- Metadata
                model_version VARCHAR(50),
                prompt_version VARCHAR(50),
                processing_time_ms INTEGER,
                
                -- Validation status
                validation_status VARCHAR(20) DEFAULT 'pending',
                validation_priority INTEGER DEFAULT 1,
                selected_for_validation BOOLEAN DEFAULT FALSE,
                selection_date DATETIME,
                
                -- Session info
                session_id VARCHAR(100),
                user_context TEXT
            )
        """)
        
        # Table: validations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS validations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                output_id INTEGER NOT NULL,
                
                -- Neurologist info
                neurologist_id VARCHAR(100) NOT NULL,
                neurologist_name VARCHAR(200),
                neurologist_specialty VARCHAR(100),
                certification_level VARCHAR(50),
                
                -- Validation
                validation_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_correct BOOLEAN,
                confidence_level VARCHAR(20),
                
                -- Detailed ratings
                classification_correct BOOLEAN,
                confidence_appropriate BOOLEAN,
                evidence_accurate BOOLEAN,
                medication_appropriate BOOLEAN,
                
                -- Feedback
                comments TEXT,
                preferred_classification TEXT,
                preferred_confidence TEXT,
                preferred_evidence TEXT,
                preferred_medication TEXT,
                
                -- Teaching points
                clinical_pearls TEXT,
                common_pitfalls TEXT,
                
                -- Time tracking
                review_time_seconds INTEGER,
                
                FOREIGN KEY (output_id) REFERENCES ai_outputs(id)
            )
        """)
        
        # Table: neurologists (simple version for demo)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS neurologists (
                id VARCHAR(100) PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(200) NOT NULL,
                specialty VARCHAR(100),
                subspecialties TEXT,
                certification_level VARCHAR(50),
                institution VARCHAR(255),
                
                -- Stats
                total_validations INTEGER DEFAULT 0,
                agreement_rate FLOAT,
                
                -- Status
                is_active BOOLEAN DEFAULT TRUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login DATETIME
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_validation_status ON ai_outputs(validation_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_selected_validation ON ai_outputs(selected_for_validation)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_condition ON ai_outputs(condition)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_neurologist ON validations(neurologist_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_output_id ON validations(output_id)")
        
        # Create default demo neurologist
        cursor.execute("""
            INSERT OR IGNORE INTO neurologists (id, email, name, specialty, certification_level, is_active)
            VALUES ('demo_neuro', 'demo@medai.ai', 'Dr. Demo Neurologist', 'general_neurology', 'attending', 1)
        """)
        
        conn.commit()
        print("[OK] Database initialized successfully")


if __name__ == "__main__":
    init_db()
    print(f"Database created at: {DB_PATH}")
