"""
Journals Processing Blueprint
Handles the simplified Summit Installments workflow with dedicated tables
"""
from flask import Blueprint, render_template, request, jsonify, send_file
from datetime import datetime
import json
import csv
import os

# Create blueprint
journals_bp = Blueprint('journals', __name__, url_prefix='/journals')

# Import db and models from app (will be set up when registering blueprint)
db = None
FPDataset = None
FPJournalRow = None
FPSummitInstallment = None
FPProcessedJournal = None
FPMatchResult = None

def init_blueprint(app_db, models):
    """Initialize the blueprint with database and models"""
    global db, FPDataset, FPJournalRow, FPSummitInstallment, FPProcessedJournal, FPMatchResult
    db = app_db
    FPDataset = models['FPDataset']
    FPJournalRow = models['FPJournalRow']
    FPSummitInstallment = models['FPSummitInstallment']
    FPProcessedJournal = models['FPProcessedJournal']
    FPMatchResult = models['FPMatchResult']

@journals_bp.route('/')
def index():
    """Main journals processing page"""
    from flask import request
    job_id = request.args.get('job_id', 1, type=int)
    subsidiary_id = request.args.get('subsidiary_id', 3, type=int)
    return render_template('journals_processing.html', job_id=job_id, subsidiary_id=subsidiary_id)

@journals_bp.route('/api/status/<int:job_id>/<int:subsidiary_id>')
def get_status(job_id, subsidiary_id):
    """Get current status of journals processing"""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        
        if not dataset:
            return jsonify({
                'success': True,
                'status': 'no_data',
                'message': 'No dataset found'
            })
        
        # Check if summit data uploaded
        summit_count = FPSummitInstallment.query.filter_by(dataset_id=dataset.id).count()
        
        # Check if matching is complete
        match_count = FPMatchResult.query.filter_by(dataset_id=dataset.id).count()
        
        # Check if processing complete
        processed_count = FPProcessedJournal.query.filter_by(dataset_id=dataset.id).count()
        
        # Get original journal stats
        original_count = FPJournalRow.query.filter_by(dataset_id=dataset.id).count()
        original_total = db.session.query(db.func.sum(FPJournalRow.amount)).filter_by(dataset_id=dataset.id).scalar() or 0
        
        status = {
            'success': True,
            'dataset_status': dataset.status,
            'original_journals': {
                'count': original_count,
                'total': round(float(original_total), 2)
            },
            'summit_uploaded': summit_count > 0,
            'summit_count': summit_count,
            'match_complete': match_count > 0,
            'match_count': match_count,
            'processing_complete': processed_count > 0,
            'processed_count': processed_count
        }
        
        if processed_count > 0:
            # Get processed journal stats
            processed_total = db.session.query(db.func.sum(FPProcessedJournal.amount)).filter_by(dataset_id=dataset.id).scalar() or 0
            summit_total = db.session.query(db.func.sum(FPProcessedJournal.amount)).filter(
                FPProcessedJournal.dataset_id == dataset.id,
                FPProcessedJournal.journal_type == 'Salon_Summit_Installments'
            ).scalar() or 0
            
            # Count rows per journal type
            main_count = FPProcessedJournal.query.filter_by(dataset_id=dataset.id, journal_type='Main').count()
            poa_count = FPProcessedJournal.query.filter_by(dataset_id=dataset.id, journal_type='POA').count()
            cross_count = FPProcessedJournal.query.filter_by(dataset_id=dataset.id, journal_type='Cross_Subsidiary').count()
            summit_count_generated = FPProcessedJournal.query.filter_by(dataset_id=dataset.id, journal_type='Salon_Summit_Installments').count()
            
            status['processed_journals'] = {
                'total': round(float(processed_total), 2),
                'summit_total': round(float(summit_total), 2),
                'counts': {
                    'Main': main_count,
                    'POA': poa_count,
                    'Cross_Subsidiary': cross_count,
                    'Salon_Summit_Installments': summit_count_generated
                }
            }
        
        return jsonify(status)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@journals_bp.route('/api/upload-summit/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def upload_summit(job_id, subsidiary_id):
    """Upload summit installments CSV"""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': False, 'error': 'Please upload at least one journal file first'}), 400
        
        # Check if at least one journal is uploaded (more flexible)
        journal_count = FPJournalRow.query.filter_by(dataset_id=dataset.id).count()
        if journal_count == 0:
            return jsonify({'success': False, 'error': 'Please upload at least one journal file first'}), 400
        
        # Check if already uploaded
        existing = FPSummitInstallment.query.filter_by(dataset_id=dataset.id).first()
        if existing:
            return jsonify({'success': False, 'error': 'Summit data already uploaded. Clear to re-upload.'}), 409
        
        payload = request.get_json(force=True)
        summit_data = payload.get('summit_data', [])
        
        if not summit_data:
            return jsonify({'success': False, 'error': 'No summit data provided'}), 400
        
        # Store in dedicated summit table
        uploaded_count = 0
        for item in summit_data:
            client_id = str(item.get('oak_id', '')).strip()
            region = str(item.get('region', '')).strip()
            installment_amount = float(item.get('installment_amount', 0))
            
            if client_id and installment_amount != 0:
                installment = FPSummitInstallment(
                    dataset_id=dataset.id,
                    job_id=job_id,
                    subsidiary_id=subsidiary_id,
                    client_id=client_id,
                    region=region,
                    installment_amount=installment_amount
                )
                db.session.add(installment)
                uploaded_count += 1
        
        db.session.commit()
        
        return jsonify({'success': True, 'uploaded_count': uploaded_count})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@journals_bp.route('/api/match-summit/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def match_summit(job_id, subsidiary_id):
    """
    Match summit installments with combined journals.
    Creates 3 categories:
    1. Matched - sufficient funds
    2. Insufficient - client found but not enough funds
    3. Unmatched - client not found in journals
    """
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': False, 'error': 'Please upload at least one journal file first'}), 400
        
        # Check if at least one journal uploaded
        journal_count = FPJournalRow.query.filter_by(dataset_id=dataset.id).count()
        if journal_count == 0:
            return jsonify({'success': False, 'error': 'Please upload at least one journal file first'}), 400
        
        # Check if summit data uploaded
        summit_installments = FPSummitInstallment.query.filter_by(dataset_id=dataset.id).all()
        if not summit_installments:
            return jsonify({'success': False, 'error': 'No summit data uploaded'}), 400
        
        # Check if already matched
        existing_matches = FPMatchResult.query.filter_by(dataset_id=dataset.id).first()
        if existing_matches:
            return jsonify({
                'success': False,
                'error': 'Summit already matched. Clear to re-match.'
            }), 409
        
        # Get all journal rows and calculate total received per client
        journal_rows = FPJournalRow.query.filter_by(dataset_id=dataset.id).all()
        client_totals = {}
        
        for row in journal_rows:
            client_id = str(row.client_id).strip() if row.client_id else ''
            if client_id:
                if client_id not in client_totals:
                    client_totals[client_id] = 0
                client_totals[client_id] += (row.amount or 0)
        
        # Combine duplicate summit clients
        summit_by_client = {}
        for installment in summit_installments:
            client_id = installment.client_id.strip()
            if client_id not in summit_by_client:
                summit_by_client[client_id] = 0
            summit_by_client[client_id] += installment.installment_amount
        
        # Perform matching
        matched_count = 0
        insufficient_count = 0
        unmatched_count = 0
        
        for client_id, installment_amount in summit_by_client.items():
            if installment_amount <= 0:
                continue
            
            total_received = client_totals.get(client_id, 0)
            
            if client_id not in client_totals:
                # Unmatched - client not found
                match_result = FPMatchResult(
                    dataset_id=dataset.id,
                    job_id=job_id,
                    subsidiary_id=subsidiary_id,
                    client_id=client_id,
                    match_status='unmatched',
                    total_received=0,
                    installment_amount=installment_amount,
                    remaining_amount=0
                )
                unmatched_count += 1
            elif total_received < installment_amount:
                # Insufficient - found but not enough
                match_result = FPMatchResult(
                    dataset_id=dataset.id,
                    job_id=job_id,
                    subsidiary_id=subsidiary_id,
                    client_id=client_id,
                    match_status='insufficient',
                    total_received=total_received,
                    installment_amount=installment_amount,
                    remaining_amount=total_received - installment_amount  # Will be negative
                )
                insufficient_count += 1
            else:
                # Matched - sufficient funds
                match_result = FPMatchResult(
                    dataset_id=dataset.id,
                    job_id=job_id,
                    subsidiary_id=subsidiary_id,
                    client_id=client_id,
                    match_status='matched',
                    total_received=total_received,
                    installment_amount=installment_amount,
                    remaining_amount=total_received - installment_amount
                )
                matched_count += 1
            
            db.session.add(match_result)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'matched_count': matched_count,
            'insufficient_count': insufficient_count,
            'unmatched_count': unmatched_count,
            'total_processed': matched_count + insufficient_count + unmatched_count,
            'message': f'✅ Matching complete! {matched_count} matched, {insufficient_count} insufficient, {unmatched_count} unmatched'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@journals_bp.route('/match-results/<int:job_id>/<int:subsidiary_id>')
def view_match_results(job_id, subsidiary_id):
    """View matching results page"""
    return render_template('match_results.html', job_id=job_id, subsidiary_id=subsidiary_id)

@journals_bp.route('/api/match-results/<int:job_id>/<int:subsidiary_id>')
def get_match_results(job_id, subsidiary_id):
    """Get matching results data"""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        
        if not dataset:
            return jsonify({
                'success': True,
                'matched': [],
                'insufficient': [],
                'unmatched': []
            })
        
        # Get all match results
        all_matches = FPMatchResult.query.filter_by(dataset_id=dataset.id).all()
        
        matched = []
        insufficient = []
        unmatched = []
        
        for match in all_matches:
            match_data = {
                'client_id': match.client_id,
                'total_received': round(match.total_received or 0, 2),
                'installment_amount': round(match.installment_amount, 2),
                'remaining_amount': round(match.remaining_amount or 0, 2)
            }
            
            if match.match_status == 'matched':
                matched.append(match_data)
            elif match.match_status == 'insufficient':
                insufficient.append(match_data)
            elif match.match_status == 'unmatched':
                unmatched.append(match_data)
        
        return jsonify({
            'success': True,
            'matched': matched,
            'insufficient': insufficient,
            'unmatched': unmatched,
            'totals': {
                'matched_count': len(matched),
                'matched_total_received': sum(m['total_received'] for m in matched),
                'matched_installment': sum(m['installment_amount'] for m in matched),
                'matched_remaining': sum(m['remaining_amount'] for m in matched),
                'insufficient_count': len(insufficient),
                'unmatched_count': len(unmatched)
            }
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@journals_bp.route('/api/download-match-results/<int:job_id>/<int:subsidiary_id>/<match_type>')
def download_match_results(job_id, subsidiary_id, match_type):
    """Download match results as CSV"""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': False, 'error': 'No dataset found'}), 404
        
        # Get matches of specified type
        if match_type == 'all':
            matches = FPMatchResult.query.filter_by(dataset_id=dataset.id).all()
        else:
            matches = FPMatchResult.query.filter_by(dataset_id=dataset.id, match_status=match_type).all()
        
        if not matches:
            return jsonify({'success': False, 'error': f'No {match_type} results found'}), 404
        
        # Create CSV file
        output_dir = f"generated_journals/job_{job_id}_sub_{subsidiary_id}"
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"match_results_{match_type}_{timestamp}.csv"
        filepath = os.path.join(output_dir, filename)
        
        # Write CSV
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Client ID', 'Total Received', 'Installment Amount', 'Remaining Amount', 'Status']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for match in matches:
                writer.writerow({
                    'Client ID': match.client_id,
                    'Total Received': round(match.total_received or 0, 2),
                    'Installment Amount': round(match.installment_amount, 2),
                    'Remaining Amount': round(match.remaining_amount or 0, 2),
                    'Status': match.match_status
                })
        
        return send_file(filepath, as_attachment=True, download_name=filename)
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@journals_bp.route('/api/clear-matches/<int:job_id>/<int:subsidiary_id>', methods=['DELETE'])
def clear_matches(job_id, subsidiary_id):
    """Clear matching results"""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': True, 'message': 'No data to clear'})
        
        # Delete all match results
        FPMatchResult.query.filter_by(dataset_id=dataset.id).delete()
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Match results cleared successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@journals_bp.route('/api/generate-journals/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def generate_journals(job_id, subsidiary_id):
    """
    Generate 4 journals from matched results:
    1-3. Original journals with reduced amounts (from remaining_amount)
    4. Summit journal with installment amounts
    """
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': False, 'error': 'No dataset found'}), 400
        
        # Check if matching was done
        match_results = FPMatchResult.query.filter_by(dataset_id=dataset.id, match_status='matched').all()
        if not match_results:
            return jsonify({'success': False, 'error': 'No matched results found. Run matching first.'}), 400
        
        # Get original journal rows
        original_rows = FPJournalRow.query.filter_by(dataset_id=dataset.id).all()
        
        # Calculate original totals by journal type
        original_totals = {}
        for row in original_rows:
            if row.journal_type not in original_totals:
                original_totals[row.journal_type] = 0
            original_totals[row.journal_type] += (row.amount or 0)
        
        # Create lookup of matched clients with their remaining amounts
        matched_clients = {}
        for match in match_results:
            matched_clients[match.client_id] = {
                'remaining_amount': match.remaining_amount,
                'installment_amount': match.installment_amount,
                'total_received': match.total_received
            }
        
        # Generate new journals by modifying amounts for matched clients
        generated_journals = {
            'Main': [],
            'POA': [],
            'Cross_Subsidiary': [],
            'Salon_Summit_Installments': []
        }
        
        new_totals = {
            'Main': 0,
            'POA': 0,
            'Cross_Subsidiary': 0,
            'Salon_Summit_Installments': 0
        }
        
        # Process each original journal row
        for row in original_rows:
            client_id = str(row.client_id).strip() if row.client_id else ''
            row_data = json.loads(row.row_json) if row.row_json else {}
            
            if client_id in matched_clients:
                match_info = matched_clients[client_id]
                original_amount = row.amount or 0
                
                # Calculate proportion of this row's amount
                if match_info['total_received'] > 0:
                    proportion = original_amount / match_info['total_received']
                    new_amount = proportion * match_info['remaining_amount']
                else:
                    new_amount = 0
                
                # Update row data with new amount
                row_data['amount'] = new_amount
                generated_journals[row.journal_type].append(row_data)
                new_totals[row.journal_type] += new_amount
            else:
                # Not matched - keep original amount
                row_data['amount'] = row.amount or 0
                generated_journals[row.journal_type].append(row_data)
                new_totals[row.journal_type] += (row.amount or 0)
        
        # Generate Summit journal from matched clients
        for match in match_results:
            # Find any original row for this client to use as template
            template_row = None
            for row in original_rows:
                if str(row.client_id).strip() == match.client_id:
                    template_row = row
                    break
            
            if template_row:
                row_data = json.loads(template_row.row_json) if template_row.row_json else {}
                
                # Modify for summit journal
                row_data['amount'] = match.installment_amount
                row_data['billing_entity'] = 'Ndevor Systems Ltd : Phorest Ireland'
                
                # Append " - Summit" to invoice and payment numbers
                if 'invoice_number' in row_data:
                    row_data['invoice_number'] = str(row_data['invoice_number']) + ' - Summit'
                if 'payment_number' in row_data:
                    row_data['payment_number'] = str(row_data['payment_number']) + ' - Summit'
                
                generated_journals['Salon_Summit_Installments'].append(row_data)
                new_totals['Salon_Summit_Installments'] += match.installment_amount
        
        # Clear any existing processed journals
        FPProcessedJournal.query.filter_by(dataset_id=dataset.id).delete()
        db.session.commit()
        
        # Save journals to database AND as CSV files
        output_dir = f"generated_journals/job_{job_id}_sub_{subsidiary_id}"
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        generated_files = []
        
        for journal_type, rows in generated_journals.items():
            if not rows:
                continue
            
            # Save to database
            for row_data in rows:
                processed_journal = FPProcessedJournal(
                    dataset_id=dataset.id,
                    job_id=job_id,
                    subsidiary_id=subsidiary_id,
                    journal_type=journal_type,
                    client_id=row_data.get('client_number', ''),
                    invoice_number=row_data.get('invoice_number', ''),
                    amount=row_data.get('amount', 0),
                    row_json=json.dumps(row_data)
                )
                db.session.add(processed_journal)
            
            # Save to CSV file
            filename = f"{journal_type}_{subsidiary_id}_{timestamp}.csv"
            filepath = os.path.join(output_dir, filename)
            
            # Get headers from first row
            if rows:
                headers = list(rows[0].keys())
                
                with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(rows)
                
                generated_files.append({
                    'journal_type': journal_type,
                    'filename': filename,
                    'filepath': filepath,
                    'row_count': len(rows),
                    'total_amount': round(new_totals[journal_type], 2)
                })
        
        # Commit database changes
        db.session.commit()
        
        # Calculate reconciliation
        original_grand_total = sum(original_totals.values())
        new_grand_total = sum(new_totals.values())
        difference = new_grand_total - original_grand_total
        
        return jsonify({
            'success': True,
            'message': f'✅ Generated {len(generated_files)} journals',
            'generated_files': generated_files,
            'reconciliation': {
                'original_totals': {k: round(v, 2) for k, v in original_totals.items()},
                'original_grand_total': round(original_grand_total, 2),
                'new_totals': {k: round(v, 2) for k, v in new_totals.items()},
                'new_grand_total': round(new_grand_total, 2),
                'difference': round(difference, 2),
                'balanced': abs(difference) < 0.01
            }
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@journals_bp.route('/api/process/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def process_summit(job_id, subsidiary_id):
    """
    Process summit installments:
    1. Copy FPJournalRow → FPProcessedJournal (fresh, unmodified)
    2. Match summit clients against processed journal
    3. Reduce amounts in processed journal
    4. Create Salon_Summit_Installments rows
    """
    try:
        print(f"DEBUG: Starting generate_journals for job_id={job_id}, subsidiary_id={subsidiary_id}")
        
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': False, 'error': 'Please upload at least one journal file first'}), 400
        
        print(f"DEBUG: Found dataset {dataset.id}")
        
        # Check if at least one journal uploaded
        journal_count = FPJournalRow.query.filter_by(dataset_id=dataset.id).count()
        if journal_count == 0:
            return jsonify({'success': False, 'error': 'Please upload at least one journal file first'}), 400
        
        print(f"DEBUG: Found {journal_count} journal rows")
        
        # Check if summit data matched
        match_results = FPMatchResult.query.filter_by(dataset_id=dataset.id).all()
        if not match_results:
            return jsonify({'success': False, 'error': 'Please match summit data first'}), 400
        
        print(f"DEBUG: Found {len(match_results)} match results")
        
        # Get summit installments
        summit_installments = FPSummitInstallment.query.filter_by(dataset_id=dataset.id).all()
        if not summit_installments:
            return jsonify({'success': False, 'error': 'No summit data uploaded'}), 400
        
        print(f"DEBUG: Found {len(summit_installments)} summit installments")
        
        # Check if already processed
        existing_processed = FPProcessedJournal.query.filter_by(dataset_id=dataset.id).first()
        if existing_processed:
            return jsonify({
                'success': False, 
                'error': 'Summit processing already complete. Clear to reprocess.'
            }), 409
        
        # STEP 1: Copy FPJournalRow → FPProcessedJournal
        original_journal_rows = FPJournalRow.query.filter_by(dataset_id=dataset.id).all()
        if not original_journal_rows:
            return jsonify({'success': False, 'error': 'No original journal data found'}), 400
        
        for orig_row in original_journal_rows:
            processed_row = FPProcessedJournal(
                dataset_id=dataset.id,
                job_id=job_id,
                subsidiary_id=subsidiary_id,
                journal_type=orig_row.journal_type,
                client_id=orig_row.client_id,
                invoice_number=orig_row.invoice_number,
                amount=orig_row.amount,
                row_json=orig_row.row_json
            )
            db.session.add(processed_row)
        
        db.session.flush()
        
        # STEP 2: Build lookup for processed journal by client_id
        processed_rows = FPProcessedJournal.query.filter_by(dataset_id=dataset.id).all()
        processed_lookup = {}
        for row in processed_rows:
            client_id = str(row.client_id).strip() if row.client_id else ''
            if client_id:
                if client_id not in processed_lookup:
                    processed_lookup[client_id] = []
                processed_lookup[client_id].append(row)
        
        # STEP 3: Combine duplicate summit clients
        summit_by_client = {}
        for installment in summit_installments:
            client_id = installment.client_id.strip()
            if client_id not in summit_by_client:
                summit_by_client[client_id] = 0
            summit_by_client[client_id] += installment.installment_amount
        
        # STEP 4: Process each summit client
        matched_count = 0
        total_summit_amount = 0.0
        unmatched_clients = []
        
        for client_id, installment_amount in summit_by_client.items():
            if installment_amount <= 0:
                continue
            
            # Check if client exists in processed journal
            if client_id not in processed_lookup:
                unmatched_clients.append({
                    'oak_id': client_id, 
                    'installment_amount': installment_amount, 
                    'reason': 'Not found in database'
                })
                continue
            
            client_rows = processed_lookup[client_id]
            total_client_amount = sum(row.amount or 0 for row in client_rows)
            
            # Check if client has sufficient amount
            if total_client_amount < installment_amount:
                unmatched_clients.append({
                    'oak_id': client_id, 
                    'installment_amount': installment_amount, 
                    'reason': f'Insufficient amount (has ${total_client_amount:.2f})'
                })
                continue
            
            if total_client_amount <= 0:
                unmatched_clients.append({
                    'oak_id': client_id, 
                    'installment_amount': installment_amount, 
                    'reason': 'Zero amount in database'
                })
                continue
            
            # MATCH! Reduce amounts proportionally
            for row in client_rows:
                current_amount = row.amount or 0
                reduction = (current_amount / total_client_amount) * installment_amount
                row.amount = current_amount - reduction
                
                # Update row_json
                if row.row_json:
                    try:
                        row_data = json.loads(row.row_json)
                        row_data['amount'] = row.amount
                        row.row_json = json.dumps(row_data)
                    except Exception as e:
                        print(f"WARNING: Failed to update row_json for client {client_id}: {e}")
                        pass
            
            # Create summit installment row
            first_row = client_rows[0]
            summit_row_data = {}
            if first_row.row_json:
                try:
                    summit_row_data = json.loads(first_row.row_json)
                except Exception as e:
                    print(f"WARNING: Failed to parse summit row_json: {e}")
                    pass
            
            summit_row = FPProcessedJournal(
                dataset_id=dataset.id,
                job_id=job_id,
                subsidiary_id=subsidiary_id,
                journal_type='Salon_Summit_Installments',
                client_id=client_id,
                invoice_number=first_row.invoice_number,
                amount=installment_amount,
                row_json=json.dumps({
                    **summit_row_data,
                    'amount': installment_amount,
                    'journal_type': 'Salon_Summit_Installments'
                })
            )
            db.session.add(summit_row)
            
            matched_count += 1
            total_summit_amount += installment_amount
        
        db.session.commit()
        
        print("DEBUG: Committed to database successfully")
        
        # Simple response without complex reconciliation (to avoid errors)
        processed_rows_all = FPProcessedJournal.query.filter_by(dataset_id=dataset.id).all()
        
        # Group by journal type
        journal_groups = {}
        for row in processed_rows_all:
            jtype = row.journal_type
            if jtype not in journal_groups:
                journal_groups[jtype] = []
            journal_groups[jtype].append(row)
        
        # Build simple file list
        generated_files = []
        for jtype, rows in journal_groups.items():
            total = sum(r.amount or 0 for r in rows)
            generated_files.append({
                'journal_type': jtype,
                'row_count': len(rows),
                'total_amount': round(total, 2)
            })
        
        # Simple reconciliation
        original_total = sum(row.amount or 0 for row in original_journal_rows)
        processed_total = sum(row.amount or 0 for row in processed_rows_all)
        
        return jsonify({
            'success': True,
            'matched_count': matched_count,
            'message': f'✅ Generated {len(generated_files)} journals for {matched_count} matched clients',
            'generated_files': generated_files,
            'reconciliation': {
                'original_totals': {},
                'new_totals': {},
                'original_grand_total': round(original_total, 2),
                'new_grand_total': round(processed_total, 2),
                'difference': round(abs(original_total - processed_total), 2),
                'balanced': abs(original_total - processed_total) < 1
            }
        })
    
    except Exception as e:
        db.session.rollback()
        import traceback
        error_details = traceback.format_exc()
        print(f"ERROR in generate_journals: {error_details}")
        return jsonify({
            'success': False, 
            'error': str(e), 
            'traceback': error_details,
            'error_type': type(e).__name__
        }), 500

@journals_bp.route('/api/clear/<int:job_id>/<int:subsidiary_id>', methods=['DELETE'])
def clear_processing(job_id, subsidiary_id):
    """Clear summit data and processed journals (restore to original state)"""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': False, 'error': 'No dataset found'}), 400
        
        # Delete processed journals
        FPProcessedJournal.query.filter_by(dataset_id=dataset.id).delete()
        
        # Delete summit installments
        FPSummitInstallment.query.filter_by(dataset_id=dataset.id).delete()
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Cleared successfully. Original journals intact.'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@journals_bp.route('/api/download/<int:job_id>/<int:subsidiary_id>/<journal_type>')
def download_journal(job_id, subsidiary_id, journal_type):
    """Download processed journal as CSV"""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': False, 'error': 'No dataset found'}), 404
        
        # Get rows for this journal type
        rows = FPProcessedJournal.query.filter_by(
            dataset_id=dataset.id,
            journal_type=journal_type
        ).all()
        
        if not rows:
            # Check if generation was done at all
            any_generated = FPProcessedJournal.query.filter_by(dataset_id=dataset.id).first()
            if not any_generated:
                return jsonify({'success': False, 'error': f'No journals generated yet. Click "Generate Journals" button first.'}), 404
            else:
                return jsonify({'success': False, 'error': f'No rows found for {journal_type}. This journal type may be empty.'}), 404
        
        # Create CSV file
        output_dir = f"generated_journals/job_{job_id}_sub_{subsidiary_id}"
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{journal_type}_{subsidiary_id}_{timestamp}.csv"
        filepath = os.path.join(output_dir, filename)
        
        # Get headers from first row
        if rows[0].row_json:
            try:
                sample_data = json.loads(rows[0].row_json)
                headers = list(sample_data.keys())
            except:
                headers = ['client_id', 'invoice_number', 'amount', 'journal_type']
        else:
            headers = ['client_id', 'invoice_number', 'amount', 'journal_type']
        
        # Write CSV
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            
            for row in rows:
                if row.row_json:
                    try:
                        row_data = json.loads(row.row_json)
                        row_data['amount'] = row.amount  # Ensure updated amount
                        writer.writerow(row_data)
                    except:
                        writer.writerow({
                            'client_id': row.client_id,
                            'invoice_number': row.invoice_number,
                            'amount': row.amount,
                            'journal_type': row.journal_type
                        })
        
        return send_file(filepath, as_attachment=True, download_name=filename)
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@journals_bp.route('/api/list-journals/<int:job_id>/<int:subsidiary_id>')
def list_journals(job_id, subsidiary_id):
    """List all available processed journals"""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': True, 'journals': []})
        
        # Get distinct journal types
        journal_types = db.session.query(
            FPProcessedJournal.journal_type,
            db.func.count(FPProcessedJournal.id).label('count'),
            db.func.sum(FPProcessedJournal.amount).label('total')
        ).filter_by(dataset_id=dataset.id).group_by(FPProcessedJournal.journal_type).all()
        
        journals = []
        for jtype, count, total in journal_types:
            journals.append({
                'journal_type': jtype,
                'count': count,
                'total': round(float(total or 0), 2)
            })
        
        return jsonify({'success': True, 'journals': journals})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@journals_bp.route('/api/upload-journals/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def upload_journals(job_id, subsidiary_id):
    """Upload Main, POA, and Cross_Subsidiary journals"""
    try:
        # Get or create dataset
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            dataset = FPDataset(job_id=job_id, subsidiary_id=subsidiary_id, status='loaded')
            db.session.add(dataset)
            db.session.flush()
        
        payload = request.get_json(force=True)
        journal_type = payload.get('journal_type')  # 'Main' | 'POA' | 'Cross_Subsidiary' | EU variants
        filename = payload.get('filename', 'uploaded.csv')
        rows = payload.get('rows', [])
        
        # Valid journal types (includes EU-specific types)
        valid_types = [
            'Main', 'POA', 'Cross_Subsidiary',  # Non-EU
            'Main_EU', 'POA_EU', 'Cross_Subsidiary_EU', 'Refunds_EU',  # EU EUR
            'Main_AED', 'POA_AED', 'Cross_Subsidiary_AED', 'Refunds_AED'  # EU AED
        ]
        
        if journal_type not in valid_types:
            return jsonify({'success': False, 'error': f'Invalid journal_type: {journal_type}'}), 400
        
        # Check if this journal type already uploaded
        existing = FPJournalRow.query.filter_by(
            dataset_id=dataset.id,
            journal_type=journal_type
        ).first()
        
        if existing:
            return jsonify({
                'success': False, 
                'error': f'{journal_type} journal already uploaded. Clear to re-upload.'
            }), 409
        
        # Store rows
        created = 0
        for row in rows:
            amount = float(row.get('amount', 0) or 0)
            client_id = str(row.get('client_id') or row.get('Client') or '')
            invoice_number = str(row.get('invoice_number') or row.get('Invoice') or '')
            
            journal_row = FPJournalRow(
                dataset_id=dataset.id,
                job_id=job_id,
                subsidiary_id=subsidiary_id,
                journal_type=journal_type,
                client_id=client_id,
                invoice_number=invoice_number,
                amount=amount,
                row_json=json.dumps(row),
                filename=filename
            )
            db.session.add(journal_row)
            created += 1
        
        # Update dataset status to committed once all 3 journals are uploaded
        uploaded_types = db.session.query(FPJournalRow.journal_type).filter_by(
            dataset_id=dataset.id
        ).distinct().all()
        uploaded_type_names = [t[0] for t in uploaded_types]
        
        if journal_type not in uploaded_type_names:
            uploaded_type_names.append(journal_type)
        
        # Mark as committed if ANY journals are uploaded (flexible approach)
        if len(uploaded_type_names) > 0:
            dataset.status = 'committed'
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'created': created,
            'journal_type': journal_type,
            'dataset_status': dataset.status
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@journals_bp.route('/api/journals-upload-status/<int:job_id>/<int:subsidiary_id>')
def journals_upload_status(job_id, subsidiary_id):
    """Get upload status for all journal types (handles both EU and non-EU)"""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        
        # Determine expected journal types based on subsidiary
        if subsidiary_id == 4:  # EU
            journal_types = ['Main_EU', 'POA_EU', 'Cross_Subsidiary_EU', 'Refunds_EU', 
                           'Main_AED', 'POA_AED', 'Cross_Subsidiary_AED', 'Refunds_AED']
        else:  # Non-EU
            journal_types = ['Main', 'POA', 'Cross_Subsidiary']
        
        if not dataset:
            return jsonify({
                'success': True,
                'uploaded': {jtype: False for jtype in journal_types},
                'counts': {},
                'totals': {},
                'all_uploaded': False
            })
        
        # Get counts and totals for each journal type
        uploaded = {}
        counts = {}
        totals = {}
        
        for jtype in journal_types:
            count = FPJournalRow.query.filter_by(
                dataset_id=dataset.id,
                journal_type=jtype
            ).count()
            
            total = db.session.query(db.func.sum(FPJournalRow.amount)).filter_by(
                dataset_id=dataset.id,
                journal_type=jtype
            ).scalar() or 0
            
            uploaded[jtype] = count > 0
            counts[jtype] = count
            totals[jtype] = round(float(total), 2)
        
        # Consider "all uploaded" if at least ONE journal is uploaded (flexible)
        # This allows users to work with partial uploads
        any_uploaded = any(uploaded.values())
        all_uploaded = any_uploaded  # Changed logic: don't require ALL, just SOME
        
        return jsonify({
            'success': True,
            'uploaded': uploaded,
            'counts': counts,
            'totals': totals,
            'all_uploaded': all_uploaded,
            'any_uploaded': any_uploaded,
            'dataset_status': dataset.status
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@journals_bp.route('/view-data/<int:job_id>/<int:subsidiary_id>')
def view_combined_data(job_id, subsidiary_id):
    """View combined data from all 3 journals"""
    return render_template('journals_data_viewer.html', job_id=job_id, subsidiary_id=subsidiary_id)

@journals_bp.route('/api/combined-data/<int:job_id>/<int:subsidiary_id>')
def get_combined_data(job_id, subsidiary_id):
    """Get combined data from all 3 journals for display"""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        
        if not dataset:
            return jsonify({
                'success': True,
                'rows': [],
                'totals': {'count': 0, 'amount': 0.0}
            })
        
        # Get all journal rows
        rows = FPJournalRow.query.filter_by(dataset_id=dataset.id).all()
        
        # Parse and combine data
        data_rows = []
        total_amount = 0.0
        
        for row in rows:
            try:
                row_data = json.loads(row.row_json) if row.row_json else {}
                row_data['_journal_type'] = row.journal_type
                row_data['_amount'] = row.amount
                row_data['_client_id'] = row.client_id
                row_data['_invoice_number'] = row.invoice_number
                data_rows.append(row_data)
                total_amount += (row.amount or 0)
            except:
                # Fallback for rows without JSON
                data_rows.append({
                    '_journal_type': row.journal_type,
                    '_client_id': row.client_id,
                    '_invoice_number': row.invoice_number,
                    '_amount': row.amount
                })
                total_amount += (row.amount or 0)
        
        return jsonify({
            'success': True,
            'rows': data_rows,
            'totals': {
                'count': len(data_rows),
                'amount': round(total_amount, 2)
            }
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@journals_bp.route('/api/clear-journals/<int:job_id>/<int:subsidiary_id>', methods=['DELETE'])
def clear_journals(job_id, subsidiary_id):
    """Clear all uploaded journals (Main, POA, Cross_Subsidiary)"""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': True, 'message': 'No data to clear'})
        
        # Delete all journal rows
        FPJournalRow.query.filter_by(dataset_id=dataset.id).delete()
        
        # Also clear any processed data and summit data
        FPProcessedJournal.query.filter_by(dataset_id=dataset.id).delete()
        FPSummitInstallment.query.filter_by(dataset_id=dataset.id).delete()
        
        # Reset dataset status
        dataset.status = 'empty'
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'All journals cleared successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

