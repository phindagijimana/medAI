"""
Validation Routes for MedAI
Neurologist validation interface
"""
from flask import Blueprint, render_template_string, request, jsonify
import random
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.database import get_db

validation_bp = Blueprint('validation', __name__, url_prefix='/validate')


def get_next_validation_case():
    """Get next case for validation"""
    with get_db() as db:
        # Get random pending case
        case = db.execute("""
            SELECT * FROM ai_outputs 
            WHERE validation_status = 'pending'
            AND selected_for_validation = TRUE
            ORDER BY validation_priority DESC, RANDOM()
            LIMIT 1
        """).fetchone()
        
        if not case:
            # If no selected cases, select from all pending
            case = db.execute("""
                SELECT * FROM ai_outputs 
                WHERE validation_status = 'pending'
                ORDER BY RANDOM()
                LIMIT 1
            """).fetchone()
        
        return dict(case) if case else None


def get_validation_stats():
    """Get validation statistics"""
    with get_db() as db:
        stats = {}
        
        # Total outputs
        stats['total_outputs'] = db.execute("SELECT COUNT(*) as count FROM ai_outputs").fetchone()['count']
        
        # Validated count
        stats['validated_count'] = db.execute(
            "SELECT COUNT(*) as count FROM ai_outputs WHERE validation_status = 'validated'"
        ).fetchone()['count']
        
        # Pending count
        stats['pending_count'] = db.execute(
            "SELECT COUNT(*) as count FROM ai_outputs WHERE validation_status = 'pending'"
        ).fetchone()['count']
        
        # Agreement rate
        result = db.execute("SELECT AVG(CAST(is_correct AS FLOAT)) as rate FROM validations").fetchone()
        stats['agreement_rate'] = result['rate'] if result['rate'] else 0.0
        
        # Today's validations
        stats['today_validations'] = db.execute("""
            SELECT COUNT(*) as count FROM validations 
            WHERE DATE(validation_timestamp) = DATE('now')
        """).fetchone()['count']
        
        return stats


def save_validation(validation_data):
    """Save validation to database"""
    with get_db() as db:
        db.execute("""
            INSERT INTO validations (
                output_id, neurologist_id, neurologist_name, neurologist_specialty,
                certification_level, is_correct, confidence_level, comments,
                preferred_classification, preferred_confidence, preferred_evidence,
                preferred_medication, classification_correct, confidence_appropriate,
                evidence_accurate, medication_appropriate, review_time_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            validation_data['output_id'],
            validation_data.get('neurologist_id', 'demo_neuro'),
            validation_data.get('neurologist_name', 'Demo Neurologist'),
            validation_data.get('neurologist_specialty', 'general_neurology'),
            validation_data.get('certification_level', 'attending'),
            validation_data['is_correct'],
            validation_data.get('confidence_level', 'medium'),
            validation_data.get('comments', ''),
            validation_data.get('preferred_classification'),
            validation_data.get('preferred_confidence'),
            validation_data.get('preferred_evidence'),
            validation_data.get('preferred_medication'),
            validation_data.get('classification_correct'),
            validation_data.get('confidence_appropriate'),
            validation_data.get('evidence_accurate'),
            validation_data.get('medication_appropriate'),
            validation_data.get('review_time_seconds', 0)
        ))
        
        # Mark output as validated
        db.execute("""
            UPDATE ai_outputs 
            SET validation_status = 'validated'
            WHERE id = ?
        """, (validation_data['output_id'],))
        
        db.commit()


@validation_bp.route('/')
def validation_home():
    """Main validation interface"""
    case = get_next_validation_case()
    stats = get_validation_stats()
    
    return render_template_string(VALIDATOR_HTML, case=case, stats=stats)


@validation_bp.route('/api/next-case', methods=['GET'])
def api_next_case():
    """API endpoint to get next validation case"""
    case = get_next_validation_case()
    
    if not case:
        return jsonify({'status': 'complete', 'message': 'No more cases available'})
    
    return jsonify({
        'status': 'success',
        'case': case
    })


@validation_bp.route('/api/submit-validation', methods=['POST'])
def api_submit_validation():
    """Submit a validation"""
    data = request.json
    
    try:
        validation = {
            'output_id': data['case_id'],
            'neurologist_id': data.get('neurologist_id', 'demo_neuro'),
            'neurologist_name': data.get('neurologist_name', 'Demo Neurologist'),
            'neurologist_specialty': data.get('neurologist_specialty', 'general_neurology'),
            'certification_level': data.get('certification_level', 'attending'),
            'is_correct': data['is_correct'],
            'confidence_level': data.get('confidence_level', 'medium'),
            'comments': data.get('comments', ''),
            'preferred_classification': data.get('preferred_classification'),
            'preferred_confidence': data.get('preferred_confidence'),
            'preferred_evidence': data.get('preferred_evidence'),
            'preferred_medication': data.get('preferred_medication'),
            'classification_correct': data.get('classification_correct'),
            'confidence_appropriate': data.get('confidence_appropriate'),
            'evidence_accurate': data.get('evidence_accurate'),
            'medication_appropriate': data.get('medication_appropriate'),
            'review_time_seconds': data.get('review_time_seconds', 0)
        }
        
        save_validation(validation)
        
        return jsonify({'status': 'success', 'message': 'Validation saved'})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@validation_bp.route('/api/stats', methods=['GET'])
def api_stats():
    """Get validation statistics"""
    stats = get_validation_stats()
    return jsonify(stats)


# HTML Template for Validator Page
VALIDATOR_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MedAI - Validator</title>
  <style>
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      background: linear-gradient(135deg, #e8f4ff 0%, #f0f8ff 100%);
      min-height: 100vh;
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

    /* Main Container */
    .container {
      max-width: 1200px;
      margin: 40px auto;
      padding: 0 30px;
    }

    /* Stats Bar */
    .stats-bar {
      background: white;
      border-radius: 12px;
      padding: 25px;
      margin-bottom: 30px;
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 20px;
    }

    .stat-item {
      text-align: center;
    }

    .stat-value {
      font-size: 32px;
      font-weight: 700;
      color: #004977;
      margin-bottom: 5px;
    }

    .stat-label {
      font-size: 13px;
      color: #666;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    /* Validator Card */
    .validator-card {
      background: white;
      border-radius: 12px;
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
      overflow: hidden;
    }

    .validator-header {
      background: #004977;
      color: white;
      padding: 25px 30px;
      border-bottom: 3px solid rgba(255, 255, 255, 0.2);
    }

    .validator-title {
      font-size: 22px;
      font-weight: 600;
      margin-bottom: 5px;
    }

    .validator-subtitle {
      font-size: 14px;
      opacity: 0.9;
    }

    .validator-body {
      padding: 30px;
    }

    /* Case Section */
    .case-section {
      margin-bottom: 30px;
    }

    .case-label {
      font-size: 12px;
      font-weight: 600;
      color: #666;
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .case-box {
      background: #f8f9fa;
      border-left: 4px solid #004977;
      padding: 20px;
      border-radius: 8px;
      line-height: 1.6;
      color: #333;
    }

    .ai-output-box {
      background: #e8f4ff;
      border-left: 4px solid #004977;
      padding: 20px;
      border-radius: 8px;
    }

    .output-item {
      margin-bottom: 15px;
      line-height: 1.6;
    }

    .output-label {
      font-weight: 600;
      color: #004977;
      margin-bottom: 5px;
    }

    .output-content {
      color: #333;
      padding-left: 10px;
    }

    /* Validation Controls */
    .validation-section {
      background: #f0f8ff;
      border-radius: 12px;
      padding: 25px;
      margin-top: 30px;
    }

    .validation-question {
      font-size: 18px;
      font-weight: 600;
      color: #004977;
      margin-bottom: 20px;
    }

    .button-group {
      display: flex;
      gap: 15px;
      margin-bottom: 20px;
    }

    .btn {
      flex: 1;
      padding: 15px 30px;
      border: none;
      border-radius: 8px;
      font-size: 16px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.3s ease;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }

    .btn-yes {
      background: #28a745;
      color: white;
    }

    .btn-yes:hover {
      background: #218838;
      transform: translateY(-2px);
      box-shadow: 0 6px 15px rgba(40, 167, 69, 0.3);
    }

    .btn-no {
      background: #dc3545;
      color: white;
    }

    .btn-no:hover {
      background: #c82333;
      transform: translateY(-2px);
      box-shadow: 0 6px 15px rgba(220, 53, 69, 0.3);
    }

    .btn-skip {
      background: #6c757d;
      color: white;
    }

    .btn-skip:hover {
      background: #5a6268;
    }

    .form-group {
      margin-bottom: 20px;
    }

    .form-label {
      display: block;
      font-weight: 600;
      color: #004977;
      margin-bottom: 8px;
      font-size: 14px;
    }

    textarea {
      width: 100%;
      min-height: 100px;
      padding: 12px;
      border: 2px solid #ddd;
      border-radius: 8px;
      font-family: inherit;
      font-size: 14px;
      resize: vertical;
      transition: border-color 0.3s ease;
    }

    textarea:focus {
      outline: none;
      border-color: #004977;
    }

    .btn-submit {
      background: #004977;
      color: white;
      padding: 15px 40px;
      border: none;
      border-radius: 8px;
      font-size: 16px;
      font-weight: 600;
      cursor: pointer;
      width: 100%;
      transition: all 0.3s ease;
    }

    .btn-submit:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 20px rgba(0, 73, 119, 0.3);
      opacity: 0.9;
    }

    /* Empty State */
    .empty-state {
      text-align: center;
      padding: 60px 30px;
      color: #666;
    }

    .empty-icon {
      font-size: 64px;
      margin-bottom: 20px;
      opacity: 0.5;
    }

    .empty-title {
      font-size: 24px;
      font-weight: 600;
      color: #004977;
      margin-bottom: 10px;
    }

    .empty-message {
      font-size: 16px;
      color: #666;
    }

    /* Success Message */
    .success-message {
      display: none;
      background: #d4edda;
      border: 1px solid #c3e6cb;
      color: #155724;
      padding: 15px;
      border-radius: 8px;
      margin-bottom: 20px;
      text-align: center;
      font-weight: 500;
    }

    /* Loading */
    .loading {
      display: none;
      text-align: center;
      padding: 40px;
    }

    .spinner {
      border: 4px solid #f3f3f3;
      border-top: 4px solid #004977;
      border-radius: 50%;
      width: 40px;
      height: 40px;
      animation: spin 1s linear infinite;
      margin: 0 auto 15px;
    }

    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }

    /* Mobile Responsive */
    @media (max-width: 768px) {
      .nav-container {
        flex-direction: column;
        gap: 15px;
        padding: 15px;
      }

      .nav-links {
        width: 100%;
      }

      .nav-link {
        flex: 1;
        text-align: center;
        padding: 10px;
      }

      .stats-bar {
        grid-template-columns: repeat(2, 1fr);
      }

      .button-group {
        flex-direction: column;
      }

      .validator-body {
        padding: 20px;
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
          MedAI
          <div class="nav-subtitle">VALIDATOR PORTAL</div>
        </a>
      </div>
      <ul class="nav-links">
        <li><a href="/" class="nav-link">Main App</a></li>
        <li><a href="/validate" class="nav-link active">Validator</a></li>
        <li><a href="/learning" class="nav-link">Learning Dashboard</a></li>
      </ul>
    </div>
  </nav>

  <div class="container">
    <!-- Stats Bar -->
    <div class="stats-bar">
      <div class="stat-item">
        <div class="stat-value">{{ stats.total_outputs }}</div>
        <div class="stat-label">Total Cases</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ stats.validated_count }}</div>
        <div class="stat-label">Validated</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ stats.pending_count }}</div>
        <div class="stat-label">Pending</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ "%.0f"|format(stats.agreement_rate * 100) if stats.agreement_rate else "N/A" }}%</div>
        <div class="stat-label">Agreement</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ stats.today_validations }}</div>
        <div class="stat-label">Today</div>
      </div>
    </div>

    <!-- Success Message -->
    <div class="success-message" id="successMessage">
      Validation submitted successfully!
    </div>

    <!-- Loading -->
    <div class="loading" id="loading">
      <div class="spinner"></div>
      <div>Loading next case...</div>
    </div>

    <!-- Validator Card -->
    <div class="validator-card" id="validatorCard">
      {% if case %}
      <div class="validator-header">
        <div class="validator-title">Case Review #{{ case.id }}</div>
        <div class="validator-subtitle">{{ case.condition | title if case.condition else "Neurology" }} - {{ case.input_type | title }}</div>
      </div>

      <div class="validator-body">
        <!-- Patient Case -->
        <div class="case-section">
          <div class="case-label">PATIENT CASE:</div>
          <div class="case-box">
            {{ case.input_text }}
          </div>
        </div>

        <!-- AI Analysis -->
        <div class="case-section">
          <div class="case-label">MEDAI AI ANALYSIS:</div>
          <div class="ai-output-box">
            {% if case.ai_classification %}
            <div class="output-item">
              <div class="output-label">• Classification:</div>
              <div class="output-content">{{ case.ai_classification }}</div>
            </div>
            {% endif %}

            {% if case.ai_confidence %}
            <div class="output-item">
              <div class="output-label">• Clinical Confidence:</div>
              <div class="output-content">{{ case.ai_confidence }}</div>
            </div>
            {% endif %}

            {% if case.ai_evidence %}
            <div class="output-item">
              <div class="output-label">• Evidence:</div>
              <div class="output-content">{{ case.ai_evidence }}</div>
            </div>
            {% endif %}

            {% if case.ai_medication_analysis %}
            <div class="output-item">
              <div class="output-label">• Medication Analysis:</div>
              <div class="output-content">{{ case.ai_medication_analysis }}</div>
            </div>
            {% endif %}
          </div>
        </div>

        <!-- Validation Section -->
        <div class="validation-section">
          <div class="validation-question">Do you agree with this AI analysis?</div>
          
          <div class="button-group">
            <button class="btn btn-yes" onclick="setValidation(true)">
              Yes
            </button>
            <button class="btn btn-no" onclick="setValidation(false)">
              No
            </button>
            <button class="btn btn-skip" onclick="skipCase()">
              Skip
            </button>
          </div>

          <form id="validationForm" style="display:none;">
            <input type="hidden" id="caseId" value="{{ case.id }}">
            <input type="hidden" id="isCorrect" value="">
            
            <div class="form-group">
              <label class="form-label">Comments / Preferred Answer (optional):</label>
              <textarea id="comments" placeholder="E.g., Classification correct, but would add consideration for..."></textarea>
            </div>

            <button type="submit" class="btn-submit">Submit & Next Case</button>
          </form>
        </div>
      </div>
      {% else %}
      <div class="empty-state">
        <div class="empty-icon"></div>
        <div class="empty-title">No Cases Available</div>
        <div class="empty-message">All cases have been validated. Great work!</div>
        <div style="margin-top: 20px;">
          <a href="/" class="btn-submit" style="display: inline-block; text-decoration: none; width: auto; padding: 12px 30px;">
            Return to Main App
          </a>
        </div>
      </div>
      {% endif %}
    </div>
  </div>

  <script>
    let reviewStartTime = Date.now();
    let currentValidation = null;

    function setValidation(isCorrect) {
      currentValidation = isCorrect;
      document.getElementById('isCorrect').value = isCorrect;
      document.getElementById('validationForm').style.display = 'block';
      
      // Scroll to form
      document.getElementById('validationForm').scrollIntoView({ behavior: 'smooth' });
    }

    function skipCase() {
      loadNextCase();
    }

    document.getElementById('validationForm')?.addEventListener('submit', async function(e) {
      e.preventDefault();
      
      const reviewTime = Math.floor((Date.now() - reviewStartTime) / 1000);
      
      const validationData = {
        case_id: document.getElementById('caseId').value,
        is_correct: document.getElementById('isCorrect').value === 'true',
        comments: document.getElementById('comments').value,
        review_time_seconds: reviewTime
      };

      try {
        const response = await fetch('/validate/api/submit-validation', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(validationData)
        });

        const result = await response.json();
        
        if (result.status === 'success') {
          // Show success message
          document.getElementById('successMessage').style.display = 'block';
          setTimeout(() => {
            document.getElementById('successMessage').style.display = 'none';
          }, 3000);
          
          // Load next case
          loadNextCase();
        } else {
          alert('Error: ' + result.message);
        }
      } catch (error) {
        console.error('Submission error:', error);
        alert('Failed to submit validation. Please try again.');
      }
    });

    async function loadNextCase() {
      document.getElementById('loading').style.display = 'block';
      document.getElementById('validatorCard').style.display = 'none';
      
      try {
        const response = await fetch('/validate/api/next-case');
        const result = await response.json();
        
        if (result.status === 'success' && result.case) {
          // Reload page with new case
          window.location.reload();
        } else {
          // No more cases
          window.location.reload();
        }
      } catch (error) {
        console.error('Load error:', error);
        alert('Failed to load next case. Please try again.');
        document.getElementById('loading').style.display = 'none';
        document.getElementById('validatorCard').style.display = 'block';
      }
    }

    // Reset review timer on page load
    reviewStartTime = Date.now();
  </script>
</body>
</html>
"""
