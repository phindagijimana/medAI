# Setup & Utility Scripts

Scripts for initialization, testing, and deployment.

## Files

### Setup Scripts

- **`init_validation_system.py`**: Initialize validation database
  - Creates database tables
  - Adds demo validation data
  - Sets up neurologist accounts
  
  ```bash
  python3 scripts/init_validation_system.py
  ```

### Testing Scripts

- **`test_learning_loop.py`**: Test self-improvement system
  - Creates test validated cases
  - Runs learning cycle
  - Verifies examples added to knowledge base
  
  ```bash
  python3 scripts/test_learning_loop.py
  ```

- **`test_rag.py`**: RAG + few-shot loader smoke test (no LLM, fast)
  - Verifies `sentence-transformers`, guideline index, and `data/few_shot_examples.json`
  
  ```bash
  APP_HOME=$(pwd) python3 scripts/test_rag.py
  ```

- **`test_analyze_e2e.py`**: End-to-end `POST /analyze` via Flask test client
  - Loads Med42 if not already in memory; uses RAG + few-shot in the real prompt path
  - **Slow on CPU** (many minutes); use a GPU for shorter runs
  - Exits 0 with a message if the model is unavailable (503)
  
  ```bash
  APP_HOME=$(pwd) python3 scripts/test_analyze_e2e.py
  ```

### Deployment Scripts

- **`med42_service.slurm`**: SLURM job template
  - HPC cluster job submission
  - Resource allocation
  - Module loading
  
  Use via `vecta-hpc` CLI instead of directly.

## Usage Examples

### Initialize System
```bash
# First-time setup
python3 scripts/init_validation_system.py

# Check database
python3 -c "from core.database import get_db; \
with get_db() as db: \
    print('Cases:', db.execute('SELECT COUNT(*) FROM ai_outputs').fetchone()[0])"
```

### Test Learning System
```bash
# Run full test
python3 scripts/test_learning_loop.py

# Expected output:
# - 3 test cases validated
# - Learning cycle runs
# - Examples added to few-shot library
# - 100% agreement rate (test data)
```

## Development

These scripts are primarily for development, testing, and initial setup. For production use:

- Use `vecta` CLI for local deployment
- Use `vecta-hpc` CLI for HPC deployment
- Use web interfaces for validation and learning

## Integration

Scripts can be imported as modules:

```python
from scripts.init_validation_system import add_demo_data
from scripts.test_learning_loop import test_full_learning_cycle

# Initialize
add_demo_data()

# Test
test_full_learning_cycle()
```
