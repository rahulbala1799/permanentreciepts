"""
EU-SPECIFIC Journals Processing Blueprint
Completely separate from USA - uses EU-specific tables only
Works with 1-8 journal files flexibly
"""

from flask import Blueprint, render_template, request, jsonify
from datetime import datetime
import json

journals_eu_bp = Blueprint('journals_eu', __name__, url_prefix='/journals-eu')

# Will be initialized by app.py
db = None
models = {}

def init_blueprint(database, eu_models):
    """Initialize blueprint with database and EU models"""
    global db, models
    db = database
    models = eu_models

@journals_eu_bp.route('/')
def index():
    """EU Journals Processing Page"""
    job_id = request.args.get('job_id', 1, type=int)
    return render_template('journals_processing_eu.html', job_id=job_id)

@journals_eu_bp.route('/api/status/<int:job_id>')
def get_status(job_id):
    """Get EU processing status - works with ANY number of uploaded files (1-8)"""
    try:
        FPDatasetEU = models['FPDatasetEU']
        FPJournalRowEU = models['FPJournalRowEU']
        FPSummitInstallmentEU = models['FPSummitInstallmentEU']
        FPMatchResultEU = models['FPMatchResultEU']
        FPProcessedJournalEU = models['FPProcessedJournalEU']
        
        dataset = FPDatasetEU.query.filter_by(job_id=job_id).first()
        
        if not dataset:
            return jsonify({
                'success': True,
                'dataset_loaded': False,
                'journals_uploaded': [],
                'summit_uploaded': False,
                'match_complete': False,
                'processing_complete': False
            })
        
        # Check which journals are uploaded
        uploaded_types = db.session.query(FPJournalRowEU.journal_type).filter_by(
            dataset_id=dataset.id
        ).distinct().all()
        uploaded_list = [t[0] for t in uploaded_types]
        
        # Check summit
        summit_count = FPSummitInstallmentEU.query.filter_by(dataset_id=dataset.id).count()
        
        # Check matches
        match_count = FPMatchResultEU.query.filter_by(dataset_id=dataset.id).count()
        
        # Check processed
        processed_count = FPProcessedJournalEU.query.filter_by(dataset_id=dataset.id).count()
        
        return jsonify({
            'success': True,
            'dataset_loaded': len(uploaded_list) > 0,
            'journals_uploaded': uploaded_list,
            'summit_uploaded': summit_count > 0,
            'summit_count': summit_count,
            'match_complete': match_count > 0,
            'match_count': match_count,
            'processing_complete': processed_count > 0
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Continue in next file due to token limits...
