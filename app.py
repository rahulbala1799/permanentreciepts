from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
import json
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import text
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from config import config

# Initialize Flask app
app = Flask(__name__)

# Load configuration
config_name = os.environ.get('FLASK_ENV', 'development')
app.config.from_object(config[config_name])

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()

# Initialize extensions with app
db.init_app(app)
migrate.init_app(app, db)

# Import and create models after db is initialized
from models import create_models
Receipt, ProcessingJob, Subsidiary, StripeTransaction, CashbookTransaction, LookerCashbookTransaction, MatchedTransaction, ReconciliationResults, JournalTransaction, FPDataset, FPJournalRow, FPWorkingRow, FPSummitInstallment, FPProcessedJournal, FPMatchResult, FPDatasetEU, FPJournalRowEU, FPSummitInstallmentEU, FPMatchResultEU, FPProcessedJournalEU = create_models(db)

# Register Journals Processing Blueprint
from journals_bp import journals_bp, init_blueprint
init_blueprint(db, {
    'FPDataset': FPDataset,
    'FPJournalRow': FPJournalRow,
    'FPSummitInstallment': FPSummitInstallment,
    'FPProcessedJournal': FPProcessedJournal,
    'FPMatchResult': FPMatchResult
})
app.register_blueprint(journals_bp)

# Make models globally available
globals()['Receipt'] = Receipt
globals()['ProcessingJob'] = ProcessingJob
globals()['Subsidiary'] = Subsidiary
globals()['StripeTransaction'] = StripeTransaction
globals()['CashbookTransaction'] = CashbookTransaction
globals()['LookerCashbookTransaction'] = LookerCashbookTransaction
globals()['MatchedTransaction'] = MatchedTransaction
globals()['ReconciliationResults'] = ReconciliationResults
globals()['JournalTransaction'] = JournalTransaction

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/receipts')
def receipts_page():
    """Receipts management page"""
    return render_template('receipts.html')

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        with db.engine.connect() as conn:
            result = conn.execute(text('SELECT 1')).fetchone()
            db_status = 'connected' if result else 'disconnected'
    except Exception as e:
        db_status = f'error: {str(e)}'
    
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'database': db_status
    })

@app.route('/api/receipts', methods=['GET', 'POST'])
def receipts():
    """Handle receipt operations"""
    if request.method == 'GET':
        # Get all receipts
        receipts = Receipt.query.order_by(Receipt.created_at.desc()).all()
        return jsonify([receipt.to_dict() for receipt in receipts])
    
    elif request.method == 'POST':
        # Create new receipt
        data = request.get_json()
        receipt = Receipt(
            filename=data.get('filename'),
            file_path=data.get('file_path'),
            status=data.get('status', 'pending'),
            created_at=datetime.utcnow()
        )
        db.session.add(receipt)
        db.session.commit()
        return jsonify(receipt.to_dict()), 201

@app.route('/api/upload', methods=['POST'])
def upload_files():
    """Handle file uploads"""
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    uploaded_count = 0
    errors = []
    
    for file in files:
        if file and file.filename and allowed_file(file.filename):
            # Generate unique filename
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            try:
                # Save file
                file.save(file_path)
                
                # Create receipt record
                receipt = Receipt(
                    filename=filename,
                    file_path=file_path,
                    status='pending',
                    created_at=datetime.utcnow()
                )
                db.session.add(receipt)
                uploaded_count += 1
                
            except Exception as e:
                errors.append(f"Error saving {filename}: {str(e)}")
        else:
            errors.append(f"Invalid file: {file.filename if file else 'No filename'}")
    
    try:
        db.session.commit()
        return jsonify({
            'message': f'Successfully uploaded {uploaded_count} files',
            'uploaded_count': uploaded_count,
            'errors': errors
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Database error: {str(e)}'}), 500

@app.route('/api/jobs', methods=['GET', 'POST'])
def jobs():
    """Handle processing job operations"""
    if request.method == 'GET':
        # Get all jobs
        jobs = ProcessingJob.query.order_by(ProcessingJob.created_at.desc()).all()
        return jsonify([job.to_dict() for job in jobs])
    
    elif request.method == 'POST':
        # Create new job
        data = request.get_json()
        job = ProcessingJob(
            job_name=data.get('job_name'),
            status=data.get('status', 'pending'),
            input_files=data.get('input_files'),
            output_files=data.get('output_files'),
            job_config=data.get('job_config'),
            created_at=datetime.utcnow()
        )
        db.session.add(job)
        db.session.commit()
        return jsonify(job.to_dict()), 201

@app.route('/api/jobs/<int:job_id>', methods=['GET', 'DELETE'])
def job_detail(job_id):
    """Handle individual job operations"""
    job = ProcessingJob.query.get_or_404(job_id)
    
    if request.method == 'GET':
        return jsonify(job.to_dict())
    
    elif request.method == 'DELETE':
        db.session.delete(job)
        db.session.commit()
        return jsonify({'message': 'Job deleted successfully'})

@app.route('/api/jobs/<int:job_id>/restart', methods=['POST'])
def restart_job(job_id):
    """Restart a processing job"""
    job = ProcessingJob.query.get_or_404(job_id)
    
    job.status = 'pending'
    job.started_at = None
    job.completed_at = None
    job.error_message = None
    
    db.session.commit()
    return jsonify({'message': 'Job restarted successfully', 'job': job.to_dict()})

@app.route('/api/subsidiaries', methods=['GET', 'POST'])
def subsidiaries():
    """Handle subsidiary operations"""
    if request.method == 'GET':
        # Get all subsidiaries
        subsidiaries = Subsidiary.query.filter_by(is_active=True).order_by(Subsidiary.name).all()
        return jsonify([subsidiary.to_dict() for subsidiary in subsidiaries])
    
    elif request.method == 'POST':
        # Create new subsidiary
        data = request.get_json()
        subsidiary = Subsidiary(
            name=data.get('name'),
            code=data.get('code'),
            region=data.get('region'),
            is_active=data.get('is_active', True),
            created_at=datetime.utcnow()
        )
        db.session.add(subsidiary)
        db.session.commit()
        return jsonify(subsidiary.to_dict()), 201

@app.route('/reconciliation/<int:job_id>')
def reconciliation_page(job_id):
    """Reconciliation page for a specific job"""
    return render_template('reconciliation.html', job_id=job_id)

@app.route('/reconciliation/<int:job_id>/<int:subsidiary_id>')
def subsidiary_reconciliation_page(job_id, subsidiary_id):
    """Individual subsidiary reconciliation page"""
    return render_template('subsidiary_reconciliation.html', job_id=job_id, subsidiary_id=subsidiary_id)

@app.route('/prepare/<int:job_id>')
def file_preparation_page(job_id):
    """File preparation page for converting files to reconciliation format"""
    return render_template('file_preparation.html', job_id=job_id)

@app.route('/prepare/looker-cashbook/<int:job_id>')
def looker_cashbook_page(job_id):
    """Page for Looker Cashbook report preparation"""
    return render_template('looker_cashbook.html', job_id=job_id)

@app.route('/looker-data/<int:job_id>')
def looker_data_page(job_id):
    """Page to view Looker cashbook transaction data"""
    return render_template('looker_data.html', job_id=job_id)

@app.route('/api/looker-cashbook-upload/<int:job_id>', methods=['POST'])
def upload_looker_cashbook_excel(job_id):
    """Upload Looker Cashbook Excel file for processing"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        try:
            # Read Excel file
            import pandas as pd
            import io
            
            # Read the Excel content
            df = pd.read_excel(file)
            
            # Validate expected columns from cashbookraw.xlsx
            expected_columns = [
                'Unnamed: 0', 'Payment Date', 'Client ID', 'Invoice Number', 
                'Billing Entity', 'AR Account', 'Currency', 'Exchange Rate', 
                'Amount', 'Account', 'Location', 'Transtype', 'Comment', 
                'Reasoncode', 'SEPA Provider', 'Stripechargeid'
            ]
            
            missing_columns = [col for col in expected_columns if col not in df.columns]
            if missing_columns:
                return jsonify({
                    'error': f'Missing required columns: {missing_columns}',
                    'expected_columns': expected_columns,
                    'found_columns': list(df.columns)
                }), 400
            
            # Delete existing looker cashbook transactions for this job
            LookerCashbookTransaction.query.filter_by(job_id=job_id).delete()
            
            # Insert new transactions
            transactions_added = 0
            from datetime import datetime  # Move import outside try block
            
            for _, row in df.iterrows():
                # Convert payment date to dd/mm/yyyy format
                payment_date_str = None
                if pd.notna(row.get('Payment Date')):
                    try:
                        # Handle different date formats from Excel
                        if isinstance(row.get('Payment Date'), str):
                            # If it's already a string, try to parse it
                            parsed_date = datetime.strptime(row.get('Payment Date'), '%Y-%m-%d %H:%M:%S')
                            payment_date_str = parsed_date.strftime('%d/%m/%Y')
                        else:
                            # If it's a datetime object from pandas
                            payment_date_str = row.get('Payment Date').strftime('%d/%m/%Y')
                    except:
                        # If parsing fails, try to convert to string and format
                        try:
                            if hasattr(row.get('Payment Date'), 'strftime'):
                                payment_date_str = row.get('Payment Date').strftime('%d/%m/%Y')
                            else:
                                payment_date_str = str(row.get('Payment Date'))
                        except:
                            payment_date_str = str(row.get('Payment Date'))
                
                transaction = LookerCashbookTransaction(
                    job_id=job_id,
                    unnamed_index=int(row.get('Unnamed: 0')) if pd.notna(row.get('Unnamed: 0')) else None,
                    payment_date=payment_date_str,
                    client_id=int(row.get('Client ID')) if pd.notna(row.get('Client ID')) else None,
                    invoice_number=str(row.get('Invoice Number', '')),
                    billing_entity=str(row.get('Billing Entity', '')),
                    ar_account=str(row.get('AR Account', '')),
                    currency=str(row.get('Currency', '')),
                    exchange_rate=int(row.get('Exchange Rate')) if pd.notna(row.get('Exchange Rate')) else None,
                    amount=float(row.get('Amount', 0)) if pd.notna(row.get('Amount')) else None,
                    account=str(row.get('Account', '')),
                    location=str(row.get('Location', '')),
                    transtype=str(row.get('Transtype', '')),
                    comment=str(row.get('Comment', '')),
                    reasoncode=int(row.get('Reasoncode')) if pd.notna(row.get('Reasoncode')) else None,
                    sepa_provider=str(row.get('SEPA Provider', '')) if pd.notna(row.get('SEPA Provider')) else None,
                    stripe_charge_id=str(row.get('Stripechargeid', '')) if pd.notna(row.get('Stripechargeid')) else None,
                    filename=file.filename,
                    uploaded_at=datetime.utcnow()
                )
                db.session.add(transaction)
                transactions_added += 1
            
            db.session.commit()
            
            return jsonify({
                'message': f'Successfully uploaded {transactions_added} Looker cashbook transactions',
                'transactions_added': transactions_added,
                'filename': file.filename,
                'columns_validated': True
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Error processing Excel file: {str(e)}'}), 500
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/looker-cashbook-transactions/<int:job_id>')
def get_looker_cashbook_transactions(job_id):
    """Get Looker Cashbook transactions for a specific job"""
    transactions = LookerCashbookTransaction.query.filter_by(
        job_id=job_id
    ).order_by(LookerCashbookTransaction.uploaded_at.desc()).all()
    
    return jsonify([transaction.to_dict() for transaction in transactions])

@app.route('/api/looker-cashbook-transactions/<int:job_id>', methods=['DELETE'])
def delete_looker_cashbook_transactions(job_id):
    """Delete all Looker Cashbook transactions for a specific job"""
    try:
        # Count transactions before deletion
        transactions_count = LookerCashbookTransaction.query.filter_by(job_id=job_id).count()
        
        if transactions_count == 0:
            return jsonify({
                'message': 'No Looker Cashbook transactions found to delete',
                'deleted_count': 0
            })
        
        # Delete all transactions for this job
        LookerCashbookTransaction.query.filter_by(job_id=job_id).delete()
        db.session.commit()
        
        return jsonify({
            'message': f'Successfully deleted {transactions_count} Looker Cashbook transactions',
            'deleted_count': transactions_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error deleting Looker Cashbook transactions: {str(e)}'}), 500

@app.route('/api/looker-cashbook-fix-errors/<int:job_id>', methods=['POST'])
def fix_looker_cashbook_errors(job_id):
    """Fix DATA ERROR entries in Looker Cashbook transactions"""
    try:
        # Get all transactions for this job
        transactions = LookerCashbookTransaction.query.filter_by(job_id=job_id).all()
        
        if not transactions:
            return jsonify({'error': 'No transactions found for this job'}), 404
        
        # Count errors before fixing
        errors_before = LookerCashbookTransaction.query.filter_by(
            job_id=job_id,
            billing_entity='DATA ERROR'
        ).count()
        
        if errors_before == 0:
            return jsonify({
                'message': 'No data errors found to fix',
                'errors_fixed': 0,
                'total_transactions': len(transactions)
            })
        
        # Apply corrections for DATA ERROR entries only
        cad_fixed = 0
        aed_fixed = 0
        
        for transaction in transactions:
            if transaction.billing_entity == 'DATA ERROR':
                if transaction.currency == 'CAD':
                    transaction.billing_entity = 'Ndevor Systems Ltd : Phorest Canada'
                    cad_fixed += 1
                elif transaction.currency == 'AED':
                    transaction.billing_entity = 'Ndevor Systems Ltd : Phorest Ireland'
                    aed_fixed += 1
        
        # Commit changes
        db.session.commit()
        
        # Count errors after fixing
        errors_after = LookerCashbookTransaction.query.filter_by(
            job_id=job_id,
            billing_entity='DATA ERROR'
        ).count()
        
        return jsonify({
            'message': f'Successfully fixed {errors_before - errors_after} data errors',
            'errors_fixed': errors_before - errors_after,
            'cad_fixed': cad_fixed,
            'aed_fixed': aed_fixed,
            'errors_remaining': errors_after,
            'total_transactions': len(transactions)
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error fixing data errors: {str(e)}'}), 500

@app.route('/api/looker-cashbook-fix-locations/<int:job_id>', methods=['POST'])
def fix_looker_cashbook_locations(job_id):
    """Fix location-based billing entity and bank account corrections"""
    try:
        # Get all transactions for this job
        transactions = LookerCashbookTransaction.query.filter_by(job_id=job_id).all()
        
        if not transactions:
            return jsonify({'error': 'No transactions found for this job'}), 404
        
        # Apply location-based corrections
        location_fixed = 0
        ireland_bank_fixed = 0
        
        for transaction in transactions:
            # Fix location-based corrections for Germany, Switzerland, Austria
            if (transaction.location in ['Germany', 'Switzerland', 'Austria'] and 
                transaction.billing_entity == 'Ndevor Systems Ltd : Phorest Ireland'):
                transaction.billing_entity = 'Ndevor Systems Ltd : Phorest Germany'
                transaction.account = '10010c Bank : Dummy Interco Bank Accounts : Interco - BOI current a/c Ä # 17013705 (Germany)'
                location_fixed += 1
            
            # Fix remaining Phorest Ireland transactions to have correct EUR bank account
            elif (transaction.billing_entity == 'Ndevor Systems Ltd : Phorest Ireland' and
                  transaction.account == '10010 Bank : BOI current a/c € # 17013705'):
                transaction.account = '10010 Bank : BOI current a/c EUR # 17013705'
                ireland_bank_fixed += 1
        
        # Commit changes
        db.session.commit()
        
        total_fixed = location_fixed + ireland_bank_fixed
        
        return jsonify({
            'message': f'Successfully applied {total_fixed} location-based corrections',
            'location_corrections': location_fixed,
            'ireland_bank_corrections': ireland_bank_fixed,
            'total_transactions': len(transactions)
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error fixing location corrections: {str(e)}'}), 500

@app.route('/api/looker-cashbook-fix-bank-accounts/<int:job_id>', methods=['POST'])
def fix_looker_cashbook_bank_accounts(job_id):
    """Fix all bank accounts based on billing entities"""
    try:
        # Get all transactions for this job
        transactions = LookerCashbookTransaction.query.filter_by(job_id=job_id).all()
        
        if not transactions:
            return jsonify({'error': 'No transactions found for this job'}), 404
        
        # Define correct bank accounts for each subsidiary
        bank_accounts = {
            'Ndevor Systems Ltd : Phorest Australia': '10130 Bank : CB current a/c AU$ # 411110236694',
            'Ndevor Systems Ltd : Phorest Canada': '10150 Bank : CIBC Current Account 9066314',
            'Ndevor Systems Ltd : Phorest US': '10043 Bank : CIBC operating a/c US$ # 2605090',
            'Ndevor Systems Ltd : Phorest Ireland : Phorest UK': '10020 Bank : BOI current a/c GBP # 62100285',
            'Ndevor Systems Ltd : Phorest Ireland': '10010 Bank : BOI current a/c EUR # 17013705',
            'Ndevor Systems Ltd : Phorest Germany': '10010c Bank : Dummy Interco Bank Accounts : Interco - BOI current a/c Ä # 17013705 (Germany)'
        }
        
        # Apply bank account corrections
        corrections_made = {}
        
        for transaction in transactions:
            billing_entity = transaction.billing_entity
            if billing_entity in bank_accounts:
                correct_account = bank_accounts[billing_entity]
                if transaction.account != correct_account:
                    old_account = transaction.account
                    transaction.account = correct_account
                    
                    # Track corrections
                    key = f"{billing_entity} -> {correct_account}"
                    if key not in corrections_made:
                        corrections_made[key] = 0
                    corrections_made[key] += 1
        
        # Commit changes
        db.session.commit()
        
        total_corrections = sum(corrections_made.values())
        
        return jsonify({
            'message': f'Successfully applied {total_corrections} bank account corrections',
            'corrections': corrections_made,
            'total_corrections': total_corrections,
            'total_transactions': len(transactions)
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error fixing bank accounts: {str(e)}'}), 500

@app.route('/api/looker-cashbook-download/<int:job_id>', methods=['GET'])
def download_looker_cashbook_excel(job_id):
    """Download corrected Looker Cashbook data as Excel file"""
    try:
        import pandas as pd
        from io import BytesIO
        
        # Get all transactions for this job
        transactions = LookerCashbookTransaction.query.filter_by(job_id=job_id).all()
        
        if not transactions:
            return jsonify({'error': 'No transactions found for this job'}), 404
        
        # Convert to DataFrame
        data = []
        for transaction in transactions:
            data.append({
                'Unnamed: 0': transaction.unnamed_index,
                'Payment Date': transaction.payment_date,
                'Client ID': transaction.client_id,
                'Invoice Number': transaction.invoice_number,
                'Billing Entity': transaction.billing_entity,
                'AR Account': transaction.ar_account,
                'Currency': transaction.currency,
                'Exchange Rate': transaction.exchange_rate,
                'Amount': transaction.amount,
                'Account': transaction.account,
                'Location': transaction.location,
                'Transtype': transaction.transtype,
                'Comment': transaction.comment,
                'Reasoncode': transaction.reasoncode,
                'SEPA Provider': transaction.sepa_provider,
                'Stripe Charge ID': transaction.stripe_charge_id
            })
        
        df = pd.DataFrame(data)
        
        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Looker Cashbook', index=False)
        
        output.seek(0)
        
        # Return Excel file
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename=looker_cashbook_corrected_job_{job_id}.xlsx'}
        )
        
    except Exception as e:
        return jsonify({'error': f'Error creating Excel file: {str(e)}'}), 500

@app.route('/api/stripe-upload/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def upload_stripe_csv(job_id, subsidiary_id):
    """Upload Stripe CSV file for a specific subsidiary"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        try:
            # Read CSV file
            import pandas as pd
            import io
            
            # Read the CSV content
            csv_content = file.read().decode('utf-8')
            df = pd.read_csv(io.StringIO(csv_content))
            
            # Rename first column from "0" to "client_number"
            if '0' in df.columns:
                df = df.rename(columns={'0': 'client_number'})
            
            # Delete existing transactions for this subsidiary and job
            StripeTransaction.query.filter_by(
                subsidiary_id=subsidiary_id, 
                job_id=job_id
            ).delete()
            
            # Insert new transactions
            transactions_added = 0
            from datetime import datetime  # Move import outside try block
            
            for _, row in df.iterrows():
                # Convert created date to dd/mm/yyyy format
                created_date_str = None
                if pd.notna(row.get('Created')):
                    try:
                        created_value = row.get('Created')
                        if isinstance(created_value, str):
                            # Try to parse different date formats from Stripe
                            try:
                                # Try parsing as ISO format: 2025-10-19T14:43:00Z
                                parsed_date = datetime.fromisoformat(created_value.replace('Z', '+00:00'))
                                created_date_str = parsed_date.strftime('%d/%m/%Y')
                            except:
                                try:
                                    # Try parsing as: 19/10/2025 14:43
                                    parsed_date = datetime.strptime(created_value, '%d/%m/%Y %H:%M')
                                    created_date_str = parsed_date.strftime('%d/%m/%Y')
                                except:
                                    try:
                                        # Try parsing as: 2025-10-19 14:43:00
                                        parsed_date = datetime.strptime(created_value, '%Y-%m-%d %H:%M:%S')
                                        created_date_str = parsed_date.strftime('%d/%m/%Y')
                                    except:
                                        # If all parsing fails, try to extract just the date part
                                        if ' ' in created_value:
                                            date_part = created_value.split(' ')[0]
                                            try:
                                                parsed_date = datetime.strptime(date_part, '%Y-%m-%d')
                                                created_date_str = parsed_date.strftime('%d/%m/%Y')
                                            except:
                                                created_date_str = str(created_value)
                                        else:
                                            created_date_str = str(created_value)
                        else:
                            # If it's a datetime object from pandas
                            created_date_str = created_value.strftime('%d/%m/%Y')
                    except Exception as e:
                        # If parsing fails completely, store as string
                        created_date_str = str(row.get('Created', ''))
                
                # Extract client ID from Description column (e.g., "41823:Company Name")
                description_client_id = None
                description_value = str(row.get('Description', ''))
                if description_value:
                    import re
                    pattern = r'^(\d+):'
                    match = re.match(pattern, description_value)
                    if match:
                        description_client_id = match.group(1)
                
                transaction = StripeTransaction(
                    subsidiary_id=subsidiary_id,
                    job_id=job_id,
                    client_number=str(row.get('client_number', '')),
                    description_client_id=description_client_id,
                    type=str(row.get('Type', '')),
                    stripe_id=str(row.get('ID', '')),
                    created=created_date_str,
                    description=str(row.get('Description', '')),
                    amount=float(row.get('Amount', 0)) if pd.notna(row.get('Amount')) else None,
                    currency=str(row.get('Currency', '')),
                    converted_amount=float(row.get('Converted Amount', 0)) if pd.notna(row.get('Converted Amount')) else None,
                    fees=float(row.get('Fees', 0)) if pd.notna(row.get('Fees')) else None,
                    net=float(row.get('Net', 0)) if pd.notna(row.get('Net')) else None,
                    converted_currency=str(row.get('Converted Currency', '')),
                    details=str(row.get('Details', '')),
                    customer_id=str(row.get('Customer ID', '')),
                    customer_email=str(row.get('Customer Email', '')),
                    customer_name=str(row.get('Customer Name', '')),
                    purpose_metadata=str(row.get('purpose (metadata)', '')),
                    phorest_client_id_metadata=str(row.get('phorest_client_id (metadata)', '')),
                    filename=file.filename,
                    uploaded_at=datetime.utcnow()
                )
                db.session.add(transaction)
                transactions_added += 1
            
            db.session.commit()
            
            return jsonify({
                'message': f'Successfully uploaded {transactions_added} transactions',
                'transactions_added': transactions_added,
                'filename': file.filename
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Error processing CSV: {str(e)}'}), 500
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/stripe-transactions/<int:job_id>/<int:subsidiary_id>')
def get_stripe_transactions(job_id, subsidiary_id):
    """Get Stripe transactions for a specific subsidiary and job"""
    transactions = StripeTransaction.query.filter_by(
        subsidiary_id=subsidiary_id,
        job_id=job_id
    ).order_by(StripeTransaction.uploaded_at.desc()).all()
    
    return jsonify([transaction.to_dict() for transaction in transactions])

@app.route('/stripe-data/<int:job_id>/<int:subsidiary_id>')
def stripe_data_page(job_id, subsidiary_id):
    """Page to view Stripe transaction data"""
    return render_template('stripe_data.html', job_id=job_id, subsidiary_id=subsidiary_id)

@app.route('/api/cashbook-upload/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def upload_cashbook_excel(job_id, subsidiary_id):
    """Upload Cashbook Excel file for a specific subsidiary"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        try:
            # Read Excel file
            import pandas as pd
            import io
            
            # Read the Excel content
            df = pd.read_excel(file)
            
            # Define correct bank accounts for each subsidiary
            BANK_ACCOUNTS = {
                1: "10130 Bank : CB current a/c AU$ # 411110236694",  # Australia
                2: "10150 Bank : CIBC Current Account 9066314",      # Canada  
                3: "10043 Bank : CIBC operating a/c US$ # 2605090",  # USA
                4: None,  # EU - no validation
                5: "10020 Bank : BOI current a/c GBP # 62100285"     # UK
            }
            
            # Validate bank accounts if subsidiary has predefined accounts
            if subsidiary_id in BANK_ACCOUNTS and BANK_ACCOUNTS[subsidiary_id] is not None:
                correct_account = BANK_ACCOUNTS[subsidiary_id]
                
                # Check if 'account' column exists and validate
                if 'account' in df.columns:
                    unique_accounts = df['account'].dropna().unique()
                    invalid_accounts = [acc for acc in unique_accounts if acc != correct_account]
                    
                    if invalid_accounts:
                        return jsonify({
                            'error': f'Invalid bank account(s) found. Expected: "{correct_account}". Found: {invalid_accounts}',
                            'expected_account': correct_account,
                            'invalid_accounts': invalid_accounts
                        }), 400
                else:
                    return jsonify({'error': 'No "account" column found in the Excel file'}), 400
            
            # Delete existing cashbook transactions for this subsidiary and job
            CashbookTransaction.query.filter_by(
                subsidiary_id=subsidiary_id, 
                job_id=job_id
            ).delete()
            
            # Insert new transactions
            transactions_added = 0
            from datetime import datetime  # Move import outside try block
            
            for _, row in df.iterrows():
                # Convert payment date to dd/mm/yyyy format
                payment_date_str = None
                if pd.notna(row.get('payment_date')):
                    try:
                        # Handle different date formats from Excel
                        if isinstance(row.get('payment_date'), str):
                            # If it's already a string, try to parse it
                            parsed_date = datetime.strptime(row.get('payment_date'), '%Y-%m-%d %H:%M:%S')
                            payment_date_str = parsed_date.strftime('%d/%m/%Y')
                        else:
                            # If it's a datetime object from pandas
                            payment_date_str = row.get('payment_date').strftime('%d/%m/%Y')
                    except:
                        # If parsing fails, try to convert to string and format
                        try:
                            if hasattr(row.get('payment_date'), 'strftime'):
                                payment_date_str = row.get('payment_date').strftime('%d/%m/%Y')
                            else:
                                payment_date_str = str(row.get('payment_date'))
                        except:
                            payment_date_str = str(row.get('payment_date'))
                
                transaction = CashbookTransaction(
                    subsidiary_id=subsidiary_id,
                    job_id=job_id,
                    payment_date=payment_date_str,
                    client_id=int(row.get('client_id')) if pd.notna(row.get('client_id')) else None,
                    invoice_number=str(row.get('invoice_number', '')),
                    billing_entity=str(row.get('billing_entity', '')),
                    ar_account=str(row.get('ar_account', '')),
                    currency=str(row.get('currency', '')),
                    exchange_rate=float(row.get('exchange_rate', 0)) if pd.notna(row.get('exchange_rate')) else None,
                    amount=float(row.get('amount', 0)) if pd.notna(row.get('amount')) else None,
                    account=str(row.get('account', '')),
                    location=str(row.get('Location', '')),
                    transtype=str(row.get('transtype', '')),
                    comment=str(row.get('comment', '')),
                    card_reference=float(row.get('Card Reference', 0)) if pd.notna(row.get('Card Reference')) else None,
                    reasoncode=float(row.get('reasoncode', 0)) if pd.notna(row.get('reasoncode')) else None,
                    sepaprovider=str(row.get('sepaprovider', '')),
                    invoice_hash=str(row.get('invoice #', '')),
                    payment_hash=str(row.get('payment #', '')),
                    memo=float(row.get('Memo', 0)) if pd.notna(row.get('Memo')) else None,
                    filename=file.filename,
                    uploaded_at=datetime.utcnow()
                )
                db.session.add(transaction)
                transactions_added += 1
            
            db.session.commit()
            
            return jsonify({
                'message': f'Successfully uploaded {transactions_added} cashbook transactions',
                'transactions_added': transactions_added,
                'filename': file.filename,
                'bank_account_validated': BANK_ACCOUNTS.get(subsidiary_id) is not None
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Error processing Excel file: {str(e)}'}), 500
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/cashbook-transactions/<int:job_id>/<int:subsidiary_id>')
def get_cashbook_transactions(job_id, subsidiary_id):
    """Get Cashbook transactions for a specific subsidiary and job"""
    transactions = CashbookTransaction.query.filter_by(
        subsidiary_id=subsidiary_id,
        job_id=job_id
    ).order_by(CashbookTransaction.uploaded_at.desc()).all()
    
    return jsonify([transaction.to_dict() for transaction in transactions])

@app.route('/cashbook-data/<int:job_id>/<int:subsidiary_id>')
def cashbook_data_page(job_id, subsidiary_id):
    """Page to view Cashbook transaction data"""
    return render_template('cashbook_data.html', job_id=job_id, subsidiary_id=subsidiary_id)

@app.route('/api/cashbook-transactions/<int:job_id>/<int:subsidiary_id>', methods=['DELETE'])
def delete_cashbook_transactions(job_id, subsidiary_id):
    """Delete all Cashbook transactions for a specific subsidiary and job"""
    try:
        deleted_count = CashbookTransaction.query.filter_by(
            subsidiary_id=subsidiary_id,
            job_id=job_id
        ).delete()
        
        db.session.commit()
        
        return jsonify({
            'message': f'Successfully deleted {deleted_count} cashbook transactions',
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error deleting cashbook transactions: {str(e)}'}), 500

@app.route('/api/stripe-transactions/<int:job_id>/<int:subsidiary_id>', methods=['DELETE'])
def delete_stripe_transactions(job_id, subsidiary_id):
    """Delete all Stripe transactions for a specific subsidiary and job"""
    try:
        deleted_count = StripeTransaction.query.filter_by(
            subsidiary_id=subsidiary_id,
            job_id=job_id
        ).delete()
        
        db.session.commit()
        
        return jsonify({
            'message': f'Successfully deleted {deleted_count} stripe transactions',
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error deleting stripe transactions: {str(e)}'}), 500

@app.route('/reconciliation-process/<int:job_id>/<int:subsidiary_id>')
def reconciliation_process_page(job_id, subsidiary_id):
    """Reconciliation process page"""
    return render_template('reconciliation_process.html', job_id=job_id, subsidiary_id=subsidiary_id)

@app.route('/journal-preparation/<int:job_id>/<int:subsidiary_id>')
def journal_preparation_page(job_id, subsidiary_id):
    """Journal preparation page"""
    return render_template('journal_preparation.html', job_id=job_id, subsidiary_id=subsidiary_id)

@app.route('/reconciliation-results/<int:job_id>/<int:subsidiary_id>/<process_name>')
def reconciliation_results_page(job_id, subsidiary_id, process_name):
    """Detailed reconciliation results page"""
    return render_template('reconciliation_results.html', job_id=job_id, subsidiary_id=subsidiary_id, process_name=process_name)

@app.route('/api/matched-transactions-full/<int:job_id>/<int:subsidiary_id>', methods=['GET'])
def get_matched_transactions_full(job_id, subsidiary_id):
    """Get all matched transactions with FULL data from both files"""
    try:
        matches = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        return jsonify({
            'count': len(matches),
            'transactions': [match.to_dict() for match in matches]
        })
    except Exception as e:
        return jsonify({'error': f'Error fetching matched transactions: {str(e)}'}), 500

@app.route('/api/process2-match/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def process2_match(job_id, subsidiary_id):
    """Process 2: Match by Date and Amount only (ignoring client number)"""
    try:
        # Get unmatched Stripe transactions from Process 1
        stripe_transactions = StripeTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        # Get unmatched Cashbook transactions from Process 1
        cashbook_transactions = CashbookTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        if not stripe_transactions:
            return jsonify({'error': 'No Stripe transactions found'}), 400
        
        if not cashbook_transactions:
            return jsonify({'error': 'No Cashbook transactions found'}), 400
        
        # Route to EU-specific or standard Process 2 matching
        if subsidiary_id == 4:  # EU
            print("[DEBUG] Using EU-specific Process 2 matching")
            matching_results = perform_process2_matching_eu(stripe_transactions, cashbook_transactions, job_id, subsidiary_id)
        else:
            # Standard matching for other subsidiaries
            matching_results = perform_process2_matching(stripe_transactions, cashbook_transactions, job_id, subsidiary_id)
        
        return jsonify({
            'message': 'Process 2 matching completed',
            'matching_results': matching_results
        })
        
    except Exception as e:
        return jsonify({'error': f'Error in Process 2 matching: {str(e)}'}), 500

@app.route('/api/resolve-multiple-match', methods=['POST'])
def resolve_multiple_match():
    """Resolve a multiple match by selecting the correct Cashbook transaction"""
    try:
        data = request.get_json()
        stripe_id = data.get('stripe_id')
        selected_cashbook_id = data.get('selected_cashbook_id')
        job_id = data.get('job_id')
        subsidiary_id = data.get('subsidiary_id')
        
        if not all([stripe_id, selected_cashbook_id, job_id, subsidiary_id]):
            return jsonify({'error': 'Missing required parameters'}), 400
        
        # Get the transactions
        stripe_tx = StripeTransaction.query.get(stripe_id)
        cashbook_tx = CashbookTransaction.query.get(selected_cashbook_id)
        
        if not stripe_tx or not cashbook_tx:
            return jsonify({'error': 'Transaction not found'}), 404
        
        # Create matched transaction with ALL columns from BOTH files
        matched_transaction = create_matched_transaction(
            stripe_tx, cashbook_tx, job_id, subsidiary_id, 'date_amount_resolved', 2
        )
        
        db.session.add(matched_transaction)
        db.session.commit()
        
        return jsonify({
            'message': 'Multiple match resolved successfully',
            'matched_transaction_id': matched_transaction.id
        })
        
    except Exception as e:
        return jsonify({'error': f'Error resolving multiple match: {str(e)}'}), 500

@app.route('/api/process3-match/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def process3_match(job_id, subsidiary_id):
    """Process 3: Fee and Refund Detection"""
    try:
        # Get unmatched Stripe transactions from previous processes
        stripe_transactions = StripeTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        if not stripe_transactions:
            return jsonify({'error': 'No Stripe transactions found'}), 400
        
        # Perform Process 3 analysis
        analysis_results = perform_process3_analysis(stripe_transactions, job_id, subsidiary_id)
        
        return jsonify({
            'message': 'Process 3 analysis completed',
            'analysis_results': analysis_results
        })
        
    except Exception as e:
        return jsonify({'error': f'Error in Process 3 analysis: {str(e)}'}), 500

def perform_process2_matching_eu(stripe_transactions, cashbook_transactions, job_id, subsidiary_id):
    """
    EU-SPECIFIC Process 2: Advanced matching with ±5 day tolerance
    EU requires flexible date matching due to batch processing and delays
    """
    from datetime import datetime, timedelta
    
    matches = []
    unmatched_stripe_p2 = []
    unmatched_cashbook_p2 = []
    
    # Get already matched transaction IDs from Process 1
    matched_stripe_ids = set()
    matched_cashbook_ids = set()
    
    existing_matches = MatchedTransaction.query.filter_by(
        job_id=job_id,
        subsidiary_id=subsidiary_id
    ).all()
    
    for match in existing_matches:
        matched_stripe_ids.add(match.stripe_id)
        matched_cashbook_ids.add(match.cashbook_id)
    
    # Filter out already matched transactions
    unmatched_stripe_tx = [tx for tx in stripe_transactions if tx.id not in matched_stripe_ids]
    unmatched_cashbook_tx = [tx for tx in cashbook_transactions if tx.id not in matched_cashbook_ids]
    
    print(f"[EU DEBUG] Process 2: {len(unmatched_stripe_tx)} unmatched Stripe, {len(unmatched_cashbook_tx)} unmatched Cashbook")
    
    # Build Cashbook lookup for faster matching
    cashbook_by_client_amount = {}
    for cashbook_tx in unmatched_cashbook_tx:
        client = str(cashbook_tx.client_id) if cashbook_tx.client_id else "0"
        amount = round(cashbook_tx.amount, 2) if cashbook_tx.amount else None
        
        # Parse date - Cashbook stores as 'dd/mm/yyyy' string
        if isinstance(cashbook_tx.payment_date, str):
            try:
                # Correct format: dd/mm/yyyy (NOT mm/dd/yyyy!)
                cb_date = datetime.strptime(cashbook_tx.payment_date, '%d/%m/%Y').date()
            except:
                print(f"[EU WARNING] Failed to parse Cashbook date: {cashbook_tx.payment_date}")
                continue
        else:
            cb_date = cashbook_tx.payment_date.date() if cashbook_tx.payment_date else None
        
        if not cb_date or amount is None:
            continue
        
        key = (client, amount)
        if key not in cashbook_by_client_amount:
            cashbook_by_client_amount[key] = []
        cashbook_by_client_amount[key].append((cashbook_tx, cb_date))
    
    print(f"[EU DEBUG] Built lookup with {len(cashbook_by_client_amount)} client+amount keys")
    
    # Available cashbook for matching
    available_cashbook = set(tx.id for tx in unmatched_cashbook_tx)
    
    # Build Cashbook lookup by date+amount (for fallback matching)
    cashbook_by_date_amount = {}
    for cashbook_tx in unmatched_cashbook_tx:
        amount = round(cashbook_tx.amount, 2) if cashbook_tx.amount else None
        
        # Parse date
        if isinstance(cashbook_tx.payment_date, str):
            try:
                cb_date = datetime.strptime(cashbook_tx.payment_date, '%d/%m/%Y').date()
            except:
                continue
        else:
            cb_date = cashbook_tx.payment_date.date() if cashbook_tx.payment_date else None
        
        if not cb_date or amount is None:
            continue
        
        key = (cb_date, amount)
        if key not in cashbook_by_date_amount:
            cashbook_by_date_amount[key] = []
        cashbook_by_date_amount[key].append(cashbook_tx)
    
    print(f"[EU DEBUG] Built date+amount lookup with {len(cashbook_by_date_amount)} keys")
    
    # Process 2 Strategy: Multi-PASS matching (prioritized)
    # We do multiple passes to ensure correct matches happen before fallback matches
    
    # Parse all Stripe transactions first
    stripe_tx_data = []
    for stripe_tx in unmatched_stripe_tx:
        # Skip Payment Failure Refund transactions - they should not be matched
        if stripe_tx.type == 'Payment Failure Refund':
            continue
        
        stripe_client = str(stripe_tx.client_number) if stripe_tx.client_number else "0"
        stripe_desc_client = str(stripe_tx.description_client_id) if stripe_tx.description_client_id else None
        
        # Parse Stripe date
        if isinstance(stripe_tx.created, str):
            try:
                stripe_date = datetime.strptime(stripe_tx.created, '%d/%m/%Y %H:%M').date()
            except:
                try:
                    stripe_date = datetime.strptime(stripe_tx.created, '%d/%m/%Y').date()
                except Exception as e:
                    print(f"[EU WARNING] Failed to parse Stripe date '{stripe_tx.created}': {e}")
                    continue
        else:
            stripe_date = stripe_tx.created.date() if stripe_tx.created else None
        
        stripe_currency = (stripe_tx.currency or '').upper()
        stripe_amount = stripe_tx.amount
        
        if not stripe_date or stripe_amount is None:
            continue
        
        stripe_amount_rounded = round(stripe_amount, 2)
        
        stripe_tx_data.append({
            'tx': stripe_tx,
            'client': stripe_client,
            'desc_client': stripe_desc_client,
            'date': stripe_date,
            'amount': stripe_amount,
            'amount_rounded': stripe_amount_rounded,
            'currency': stripe_currency,
            'matched': False
        })
    
    print(f"[EU DEBUG] Parsed {len(stripe_tx_data)} Stripe transactions for matching")
    
    match_count = 0
    
    # PASS 1: Match using description_client_id + Amount + Date (±5 days)
    print(f"[EU DEBUG] PASS 1: Matching by description_client_id + amount + date...")
    pass1_matches = 0
    for stripe_data in stripe_tx_data:
        if stripe_data['matched']:
            continue
        
        if not stripe_data['desc_client']:
            continue
        
        stripe_tx = stripe_data['tx']
        key = (stripe_data['desc_client'], stripe_data['amount_rounded'])
        candidates = cashbook_by_client_amount.get(key, [])
        
        for cashbook_tx, cb_date in candidates:
            if cashbook_tx.id not in available_cashbook:
                continue
            
            date_diff = abs((cb_date - stripe_data['date']).days)
            if date_diff <= 5:
                # Currency check for AED
                cashbook_currency = (cashbook_tx.currency or '').upper()
                if stripe_data['currency'] == 'AED' and cashbook_currency != 'AED':
                    continue
                
                # Create match
                match_type = f'desc_client_amount_±{date_diff}d'
                matched_transaction = create_matched_transaction(
                    stripe_tx, cashbook_tx, job_id, subsidiary_id, 
                    match_type, 2
                )
                db.session.add(matched_transaction)
                
                matches.append({
                    'stripe_id': stripe_tx.id,
                    'cashbook_id': cashbook_tx.id,
                    'client_number': stripe_data['client'],
                    'date': stripe_data['date'],
                    'amount': stripe_data['amount'],
                    'match_type': match_type
                })
                
                available_cashbook.remove(cashbook_tx.id)
                stripe_data['matched'] = True
                match_count += 1
                pass1_matches += 1
                print(f"[EU DEBUG] PASS 1: Matched Stripe {stripe_data['client']} → Cashbook {cashbook_tx.client_id} (desc: {stripe_data['desc_client']})")
                break
    
    print(f"[EU DEBUG] PASS 1 complete: {pass1_matches} matches")
    
    # PASS 2: Match using regular client_number + Amount + Date (±5 days)
    print(f"[EU DEBUG] PASS 2: Matching by client_number + amount + date...")
    pass2_matches = 0
    for stripe_data in stripe_tx_data:
        if stripe_data['matched']:
            continue
        
        stripe_tx = stripe_data['tx']
        key = (stripe_data['client'], stripe_data['amount_rounded'])
        candidates = cashbook_by_client_amount.get(key, [])
        
        for cashbook_tx, cb_date in candidates:
            if cashbook_tx.id not in available_cashbook:
                continue
            
            date_diff = abs((cb_date - stripe_data['date']).days)
            if date_diff <= 5:
                # Currency check for AED
                cashbook_currency = (cashbook_tx.currency or '').upper()
                if stripe_data['currency'] == 'AED' and cashbook_currency != 'AED':
                    continue
                
                # Create match
                match_type = f'client_amount_±{date_diff}d'
                matched_transaction = create_matched_transaction(
                    stripe_tx, cashbook_tx, job_id, subsidiary_id, 
                    match_type, 2
                )
                db.session.add(matched_transaction)
                
                matches.append({
                    'stripe_id': stripe_tx.id,
                    'cashbook_id': cashbook_tx.id,
                    'client_number': stripe_data['client'],
                    'date': stripe_data['date'],
                    'amount': stripe_data['amount'],
                    'match_type': match_type
                })
                
                available_cashbook.remove(cashbook_tx.id)
                stripe_data['matched'] = True
                match_count += 1
                pass2_matches += 1
                break
    
    print(f"[EU DEBUG] PASS 2 complete: {pass2_matches} matches")
    
    # PASS 3: Match using Date + Amount only (ignore client, with ±5 day tolerance)
    print(f"[EU DEBUG] PASS 3: Matching by date + amount only (fallback)...")
    pass3_matches = 0
    for stripe_data in stripe_tx_data:
        if stripe_data['matched']:
            continue
        
        stripe_tx = stripe_data['tx']
        
        # Check dates within ±5 days
        matched = False
        for days_offset in range(6):
            for direction in [0, 1, -1]:
                if days_offset == 0 and direction != 0:
                    continue
                
                check_date = stripe_data['date'] + timedelta(days=days_offset * direction)
                key = (check_date, stripe_data['amount_rounded'])
                candidates = cashbook_by_date_amount.get(key, [])
                
                if candidates:
                    for cashbook_tx in candidates:
                        if cashbook_tx.id not in available_cashbook:
                            continue
                        
                        # Currency check for AED
                        cashbook_currency = (cashbook_tx.currency or '').upper()
                        if stripe_data['currency'] == 'AED' and cashbook_currency != 'AED':
                            continue
                        
                        # Create match
                        date_diff = abs(days_offset)
                        match_type = f'date_amount_only_±{date_diff}d'
                        matched_transaction = create_matched_transaction(
                            stripe_tx, cashbook_tx, job_id, subsidiary_id, 
                            match_type, 2
                        )
                        db.session.add(matched_transaction)
                        
                        matches.append({
                            'stripe_id': stripe_tx.id,
                            'cashbook_id': cashbook_tx.id,
                            'client_number': stripe_data['client'],
                            'date': stripe_data['date'],
                            'amount': stripe_data['amount'],
                            'match_type': match_type
                        })
                        
                        available_cashbook.remove(cashbook_tx.id)
                        stripe_data['matched'] = True
                        match_count += 1
                        pass3_matches += 1
                        matched = True
                        break
                
                if matched:
                    break
            
            if matched:
                break
    
    print(f"[EU DEBUG] PASS 3 complete: {pass3_matches} matches")
    print(f"[EU DEBUG] Total Process 2 matches: {match_count}")
    
    # Collect unmatched
    for stripe_data in stripe_tx_data:
        if not stripe_data['matched']:
            unmatched_stripe_p2.append({
                'id': stripe_data['tx'].id,
                'client_number': stripe_data['client'],
                'description_client_id': stripe_data['desc_client'],
                'date': stripe_data['date'],
                'amount': stripe_data['amount']
            })
    
    # Remaining Cashbook are unmatched
    for cashbook_tx in unmatched_cashbook_tx:
        if cashbook_tx.id in available_cashbook:
            unmatched_cashbook_p2.append({
                'id': cashbook_tx.id,
                'client_id': cashbook_tx.client_id,
                'date': cashbook_tx.payment_date,
                'amount': cashbook_tx.amount,
                'transtype': cashbook_tx.transtype
            })
    
    # Commit matches
    db.session.commit()
    
    # Get ALL matched transactions (Process 1 + Process 2)
    all_matches = MatchedTransaction.query.filter_by(
        job_id=job_id,
        subsidiary_id=subsidiary_id
    ).all()
    
    all_matches_list = [{
        'stripe_id': match.stripe_id,
        'cashbook_id': match.cashbook_id,
        'client_number': match.stripe_client_number,
        'date': match.stripe_created,
        'amount': float(match.stripe_amount) if match.stripe_amount else None,
        'match_type': match.match_type,
        'process': match.process_number
    } for match in all_matches]
    
    print(f"[EU DEBUG] Process 2 complete: {len(matches)} new matches, {len(all_matches)} total")
    
    # Save results metadata
    reconciliation_result = ReconciliationResults(
        job_id=job_id,
        subsidiary_id=subsidiary_id,
        process_number=2,
        cutoff_date=None,
        unmatched_stripe_count=0,
        unmatched_cashbook_count=0,
        out_of_cutoff_count=0,
        multiple_matches_count=0,
        unmatched_stripe_p2_count=len(unmatched_stripe_p2),
        unmatched_cashbook_p2_count=len(unmatched_cashbook_p2)
    )
    db.session.add(reconciliation_result)
    db.session.commit()
    
    return {
        'perfect_matches': {
            'count': len(all_matches_list),
            'transactions': all_matches_list
        },
        'process2_new_matches': {
            'count': len(matches),
            'transactions': matches
        },
        'unmatched_stripe': {
            'count': len(unmatched_stripe_p2),
            'transactions': unmatched_stripe_p2
        },
        'unmatched_cashbook': {
            'count': len(unmatched_cashbook_p2),
            'transactions': unmatched_cashbook_p2
        },
        'summary': {
            'total_stripe': len(stripe_transactions),
            'total_cashbook': len(cashbook_transactions),
            'perfect_matches': len(all_matches_list),
            'process2_new_matches': len(matches),
            'unmatched_stripe': len(unmatched_stripe_p2),
            'unmatched_cashbook': len(unmatched_cashbook_p2),
            'out_of_cutoff_cashbook': 0
        }
    }

def perform_process2_matching(stripe_transactions, cashbook_transactions, job_id, subsidiary_id):
    """Process 2: Try multiple matching strategies to match ALL Stripe transactions"""
    matches = []
    unmatched_stripe_p2 = []
    unmatched_cashbook_p2 = []
    
    # Get already matched transaction IDs from ALL processes
    matched_stripe_ids = set()
    matched_cashbook_ids = set()
    
    existing_matches = MatchedTransaction.query.filter_by(
        job_id=job_id,
        subsidiary_id=subsidiary_id
    ).all()
    
    for match in existing_matches:
        matched_stripe_ids.add(match.stripe_id)
        matched_cashbook_ids.add(match.cashbook_id)
    
    # Filter out already matched transactions
    unmatched_stripe_tx = [tx for tx in stripe_transactions if tx.id not in matched_stripe_ids]
    unmatched_cashbook_tx = [tx for tx in cashbook_transactions if tx.id not in matched_cashbook_ids]
    
    print(f"[DEBUG] Process 2: {len(unmatched_stripe_tx)} unmatched Stripe, {len(unmatched_cashbook_tx)} unmatched Cashbook")
    
    # Create a copy of unmatched cashbook transactions for matching
    available_cashbook = unmatched_cashbook_tx.copy()
    
    # Subsidiary mapping for cross-subsidiary detection
    subsidiary_mapping = {
        1: "Ndevor Systems Ltd : Phorest Australia",
        2: "Ndevor Systems Ltd : Phorest Canada", 
        3: "Ndevor Systems Ltd : Phorest US",
        4: "Ndevor Systems Ltd : Phorest Ireland",  # EU
        5: "Ndevor Systems Ltd : Phorest Ireland : Phorest UK"
    }
    current_subsidiary_name = subsidiary_mapping.get(subsidiary_id, "")
    
    # Process each unmatched Stripe transaction with multiple strategies
    for stripe_tx in unmatched_stripe_tx:
        # Skip Payment Failure Refund transactions - they should not be matched
        if stripe_tx.type == 'Payment Failure Refund':
            continue
        
        matched = False
        match_strategy = None
        
        # Strategy 1: Date + Amount match (with 2-day tolerance)
        for i, cashbook_tx in enumerate(available_cashbook):
            if is_date_amount_match(stripe_tx, cashbook_tx):
                match_strategy = 'date_amount'
                matched_cashbook_tx = cashbook_tx
                matched_index = i
                matched = True
                break
        
        # Strategy 2: Client + Amount match (ignoring date)
        if not matched:
            for i, cashbook_tx in enumerate(available_cashbook):
                if is_client_amount_match(stripe_tx, cashbook_tx):
                    match_strategy = 'client_amount'
                    matched_cashbook_tx = cashbook_tx
                    matched_index = i
                    matched = True
                    break
        
        # Strategy 3: Check for cross-subsidiary transactions in Cashbook
        if not matched:
            for i, cashbook_tx in enumerate(available_cashbook):
                # Check if this cashbook transaction belongs to a different subsidiary
                if cashbook_tx.billing_entity and cashbook_tx.billing_entity != current_subsidiary_name:
                    # Check if date and amount match
                    if is_date_amount_match(stripe_tx, cashbook_tx):
                        match_strategy = 'cross_subsidiary'
                        matched_cashbook_tx = cashbook_tx
                        matched_index = i
                        matched = True
                        break
        
        # If matched by any strategy, save it
        if matched:
            print(f"[DEBUG] MATCH ({match_strategy})! Stripe {stripe_tx.id} <-> Cashbook {matched_cashbook_tx.id}")
            
            # Save match to database with ALL columns from BOTH files
            matched_transaction = create_matched_transaction(
                stripe_tx, matched_cashbook_tx, job_id, subsidiary_id, match_strategy, 2
            )
            db.session.add(matched_transaction)
            
            matches.append({
                'stripe_id': stripe_tx.id,
                'cashbook_id': matched_cashbook_tx.id,
                'client_number': stripe_tx.client_number,
                'date': stripe_tx.created,
                'amount': stripe_tx.amount,
                'match_type': match_strategy
            })
            
            # Remove matched cashbook transaction
            available_cashbook.pop(matched_index)
        else:
            unmatched_stripe_p2.append({
                'id': stripe_tx.id,
                'client_number': stripe_tx.client_number,
                'date': stripe_tx.created,
                'amount': stripe_tx.amount
            })
    
    print(f"[DEBUG] Process 2 complete: {len(matches)} matches found using multiple strategies")
    
    # Remaining cashbook transactions are unmatched
    for cashbook_tx in available_cashbook:
        unmatched_cashbook_p2.append({
            'id': cashbook_tx.id,
            'client_id': cashbook_tx.client_id,
            'date': cashbook_tx.payment_date,
            'amount': cashbook_tx.amount,
            'transtype': cashbook_tx.transtype
        })
    
    # Commit all changes to database
    db.session.commit()
    
    # Get ALL matched transactions (Process 1 + Process 2) to show cumulative results
    all_matches = MatchedTransaction.query.filter_by(
        job_id=job_id,
        subsidiary_id=subsidiary_id
    ).all()
    
    all_matches_list = [{
        'stripe_id': match.stripe_id,
        'cashbook_id': match.cashbook_id,
        'client_number': match.stripe_client_number,
        'date': match.stripe_created,
        'amount': float(match.stripe_amount) if match.stripe_amount else None,
        'match_type': match.match_type,
        'process': match.process_number
    } for match in all_matches]
    
    # Save reconciliation results metadata for Process 2
    reconciliation_result = ReconciliationResults(
        job_id=job_id,
        subsidiary_id=subsidiary_id,
        process_number=2,
        cutoff_date=None,
        unmatched_stripe_count=0,
        unmatched_cashbook_count=0,
        out_of_cutoff_count=0,
        multiple_matches_count=0,
        unmatched_stripe_p2_count=len(unmatched_stripe_p2),
        unmatched_cashbook_p2_count=len(unmatched_cashbook_p2)
    )
    db.session.add(reconciliation_result)
    db.session.commit()
    
    return {
        'perfect_matches': {
            'count': len(all_matches_list),
            'transactions': all_matches_list
        },
        'process2_new_matches': {
            'count': len(matches),
            'transactions': matches
        },
        'unmatched_stripe': {
            'count': len(unmatched_stripe_p2),
            'transactions': unmatched_stripe_p2
        },
        'unmatched_cashbook': {
            'count': len(unmatched_cashbook_p2),
            'transactions': unmatched_cashbook_p2
        },
        'summary': {
            'total_stripe': len(stripe_transactions),
            'total_cashbook': len(cashbook_transactions),
            'perfect_matches': len(all_matches_list),
            'process2_new_matches': len(matches),
            'unmatched_stripe': len(unmatched_stripe_p2),
            'unmatched_cashbook': len(unmatched_cashbook_p2),
            'out_of_cutoff_cashbook': 0
        }
    }

def perform_process3_analysis(stripe_transactions, job_id, subsidiary_id):
    """Perform Process 3 analysis: Fee, Refund, Cross-Subsidiary Detection, and Near-Matches with date tolerance"""
    fees = []
    refunds = []
    cross_subsidiary = []
    near_matches = []
    unmatched_stripe = []
    unmatched_cashbook = []
    
    # Get already matched transaction IDs to exclude them
    matched_stripe_ids = set()
    matched_cashbook_ids = set()
    existing_matches = MatchedTransaction.query.filter_by(
        job_id=job_id,
        subsidiary_id=subsidiary_id
    ).all()
    
    for match in existing_matches:
        matched_stripe_ids.add(match.stripe_id)
        matched_cashbook_ids.add(match.cashbook_id)
    
    # Filter out already matched transactions
    unmatched_stripe_tx = [tx for tx in stripe_transactions if tx.id not in matched_stripe_ids]
    
    # Get Cashbook transactions to check for cross-subsidiary billing entities and unmatched
    cashbook_transactions = CashbookTransaction.query.filter_by(
        job_id=job_id,
        subsidiary_id=subsidiary_id
    ).all()
    
    unmatched_cashbook_tx = [tx for tx in cashbook_transactions if tx.id not in matched_cashbook_ids]
    
    # Define subsidiary mapping for cross-subsidiary detection
    subsidiary_mapping = {
        1: "Ndevor Systems Ltd : Phorest Australia",  # Australia
        2: "Ndevor Systems Ltd : Phorest Canada",     # Canada  
        3: "Ndevor Systems Ltd : Phorest US",        # USA
        4: "Ndevor Systems Ltd : Phorest Ireland",    # EU/Ireland
        5: "Ndevor Systems Ltd : Phorest Ireland : Phorest UK"  # UK
    }
    
    current_subsidiary_name = subsidiary_mapping.get(subsidiary_id, "Unknown")
    
    # Analyze unmatched Stripe transactions
    for stripe_tx in unmatched_stripe_tx:
        # Check if it's a refund (negative amount OR type is 'Refund' case-insensitive)
        tx_type = (stripe_tx.type or '').lower()
        is_refund = (stripe_tx.amount and stripe_tx.amount < 0) or tx_type == 'refund'
        
        if is_refund:
            refunds.append({
                'id': stripe_tx.id,
                'client_number': stripe_tx.client_number,
                'date': stripe_tx.created,
                'amount': stripe_tx.amount,
                'type': stripe_tx.type,
                'reason': 'Refund transaction (negative amount or type=Refund)',
                'source': 'Stripe'
            })
        # Check if client number is 0 (likely fees)
        elif stripe_tx.client_number == "0":
            fees.append({
                'id': stripe_tx.id,
                'client_number': stripe_tx.client_number,
                'date': stripe_tx.created,
                'amount': stripe_tx.amount,
                'type': stripe_tx.type,
                'reason': 'Client number is 0 (likely fees)',
                'source': 'Stripe'
            })
        else:
            # Check for cross-subsidiary transactions
            # Look for Cashbook transactions with different billing entities
            cross_subsidiary_found = False
            for cb_tx in cashbook_transactions:
                if (cb_tx.billing_entity and 
                    cb_tx.billing_entity != current_subsidiary_name and
                    cb_tx.payment_date == stripe_tx.created and
                    abs(float(cb_tx.amount or 0) - float(stripe_tx.amount or 0)) < 0.01):
                    
                    cross_subsidiary.append({
                        'id': stripe_tx.id,
                        'client_number': stripe_tx.client_number,
                        'date': stripe_tx.created,
                        'amount': stripe_tx.amount,
                        'type': stripe_tx.type,
                        'reason': f'Cross-subsidiary: {cb_tx.billing_entity} (payout to different bank)',
                        'cashbook_billing_entity': cb_tx.billing_entity,
                        'cashbook_id': cb_tx.id,
                        'source': 'Stripe'
                    })
                    cross_subsidiary_found = True
                    break
            
            if not cross_subsidiary_found:
                # Check for near-matches with date tolerance
                # Use ALL cashbook transactions, not just unmatched ones
                near_match_found = False
                for cb_tx in cashbook_transactions:
                    if is_near_match(stripe_tx, cb_tx, date_tolerance_days=2):
                        from datetime import datetime
                        try:
                            stripe_date = datetime.strptime(stripe_tx.created, '%d/%m/%Y')
                            cashbook_date = datetime.strptime(cb_tx.payment_date, '%d/%m/%Y')
                            date_diff = abs((stripe_date - cashbook_date).days)
                        except:
                            date_diff = 'Unknown'
                        
                        near_matches.append({
                            'id': stripe_tx.id,
                            'client_number': stripe_tx.client_number,
                            'date': stripe_tx.created,
                            'amount': stripe_tx.amount,
                            'type': stripe_tx.type,
                            'reason': f'Near-match: Client & Amount match, Date diff: {date_diff} days',
                            'cashbook_id': cb_tx.id,
                            'cashbook_date': cb_tx.payment_date,
                            'cashbook_amount': cb_tx.amount,
                            'date_difference': date_diff,
                            'source': 'Stripe'
                        })
                        near_match_found = True
                        break
                
                if not near_match_found:
                    unmatched_stripe.append({
                        'id': stripe_tx.id,
                        'client_number': stripe_tx.client_number,
                        'date': stripe_tx.created,
                        'amount': stripe_tx.amount,
                        'type': stripe_tx.type,
                        'reason': 'Other unmatched Stripe transaction',
                        'source': 'Stripe'
                    })
    
    # Analyze unmatched Cashbook transactions
    for cashbook_tx in unmatched_cashbook_tx:
        unmatched_cashbook.append({
            'id': cashbook_tx.id,
            'client_id': cashbook_tx.client_id,
            'date': cashbook_tx.payment_date,
            'amount': cashbook_tx.amount,
            'billing_entity': cashbook_tx.billing_entity,
            'reason': 'Unmatched Cashbook transaction',
            'source': 'Cashbook'
        })
    
    # Save reconciliation results metadata for Process 3
    reconciliation_result = ReconciliationResults(
        job_id=job_id,
        subsidiary_id=subsidiary_id,
        process_number=3,
        cutoff_date=None,  # Process 3 doesn't use cutoff date
        unmatched_stripe_count=len(unmatched_stripe),  # Process 3 specific fields
        unmatched_cashbook_count=len(unmatched_cashbook),
        out_of_cutoff_count=len(near_matches),  # Using this field for near-matches count
        multiple_matches_count=len(fees),  # Using this field for fees count
        unmatched_stripe_p2_count=len(refunds),  # Using this field for refunds count
        unmatched_cashbook_p2_count=len(cross_subsidiary)  # Using this field for cross-subsidiary count
    )
    db.session.add(reconciliation_result)
    db.session.commit()
    
    return {
        'fees': {
            'count': len(fees),
            'transactions': fees
        },
        'refunds': {
            'count': len(refunds),
            'transactions': refunds
        },
        'cross_subsidiary': {
            'count': len(cross_subsidiary),
            'transactions': cross_subsidiary
        },
        'near_matches': {
            'count': len(near_matches),
            'transactions': near_matches
        },
        'unmatched_stripe': {
            'count': len(unmatched_stripe),
            'transactions': unmatched_stripe
        },
        'unmatched_cashbook': {
            'count': len(unmatched_cashbook),
            'transactions': unmatched_cashbook
        },
        'summary': {
            'total_unmatched_stripe': len(unmatched_stripe_tx),
            'total_unmatched_cashbook': len(unmatched_cashbook_tx),
            'fees': len(fees),
            'refunds': len(refunds),
            'cross_subsidiary': len(cross_subsidiary),
            'near_matches': len(near_matches),
            'unmatched_stripe': len(unmatched_stripe),
            'unmatched_cashbook': len(unmatched_cashbook)
        }
    }

def is_client_amount_match(stripe_tx, cashbook_tx):
    """Check if Stripe and Cashbook transactions match by client and amount (ignoring date)"""
    # Match client number
    stripe_client = str(stripe_tx.client_number or '')
    cashbook_client = str(cashbook_tx.client_id or '')
    if stripe_client != cashbook_client:
        return False
    
    # Match amount (with small tolerance for floating point)
    if abs((stripe_tx.amount or 0) - (cashbook_tx.amount or 0)) > 0.01:
        return False
    
    return True

def is_date_amount_match(stripe_tx, cashbook_tx, date_tolerance_days=2):
    """Check if Stripe and Cashbook transactions match by date and amount with date tolerance"""
    from datetime import datetime
    
    try:
        # Parse dates
        stripe_date = datetime.strptime(stripe_tx.created, '%d/%m/%Y') if stripe_tx.created else None
        cashbook_date = datetime.strptime(cashbook_tx.payment_date, '%d/%m/%Y') if cashbook_tx.payment_date else None
        
        if not stripe_date or not cashbook_date:
            return False
        
        # Check date tolerance (allow 1-2 days difference)
        date_diff = abs((stripe_date - cashbook_date).days)
        if date_diff > date_tolerance_days:
            return False
        
        # Match amount (with small tolerance for floating point)
        if abs((stripe_tx.amount or 0) - (cashbook_tx.amount or 0)) > 0.01:
            return False
        
        return True
    except Exception as e:
        print(f"Date matching error: {e}")
        return False

def is_near_match(stripe_tx, cashbook_tx, date_tolerance_days=2):
    """Check if Stripe and Cashbook transactions are near-matches with date tolerance"""
    from datetime import datetime, timedelta
    
    # Match client number (convert both to string for comparison)
    stripe_client = str(stripe_tx.client_number or '')
    cashbook_client = str(cashbook_tx.client_id or '')
    if stripe_client != cashbook_client:
        return False
    
    # Match amount (with small tolerance for floating point)
    stripe_amount = float(stripe_tx.amount or 0)
    cashbook_amount = float(cashbook_tx.amount or 0)
    if abs(stripe_amount - cashbook_amount) >= 0.01:
        return False
    
    # Check date tolerance
    try:
        stripe_date = datetime.strptime(stripe_tx.created, '%d/%m/%Y')
        cashbook_date = datetime.strptime(cashbook_tx.payment_date, '%d/%m/%Y')
        
        date_diff = abs((stripe_date - cashbook_date).days)
        return date_diff <= date_tolerance_days
    except Exception as e:
        print(f"Date parsing error: {e}")
        return False

def create_matched_transaction(stripe_tx, cashbook_tx, job_id, subsidiary_id, match_type, process_number):
    """Helper function to create a MatchedTransaction with ALL columns from BOTH files"""
    return MatchedTransaction(
        job_id=job_id,
        subsidiary_id=subsidiary_id,
        # ALL Cashbook columns
        cashbook_id=cashbook_tx.id,
        cb_payment_date=cashbook_tx.payment_date,
        cb_client_id=cashbook_tx.client_id,
        cb_invoice_number=cashbook_tx.invoice_number,
        cb_billing_entity=cashbook_tx.billing_entity,
        cb_ar_account=cashbook_tx.ar_account,
        cb_currency=cashbook_tx.currency,
        cb_exchange_rate=cashbook_tx.exchange_rate,
        cb_amount=cashbook_tx.amount,
        cb_account=cashbook_tx.account,
        cb_location=cashbook_tx.location,
        cb_transtype=cashbook_tx.transtype,
        cb_comment=cashbook_tx.comment,
        cb_card_reference=cashbook_tx.card_reference,
        cb_reasoncode=cashbook_tx.reasoncode,
        cb_sepaprovider=cashbook_tx.sepaprovider,
        cb_invoice_hash=cashbook_tx.invoice_hash,
        cb_payment_hash=cashbook_tx.payment_hash,
        cb_memo=cashbook_tx.memo,
        # ALL Stripe columns
        stripe_id=stripe_tx.id,
        stripe_client_number=stripe_tx.client_number,
        stripe_type=stripe_tx.type,
        stripe_stripe_id=stripe_tx.stripe_id,
        stripe_created=stripe_tx.created,
        stripe_description=stripe_tx.description,
        stripe_amount=stripe_tx.amount,
        stripe_currency=stripe_tx.currency,
        stripe_converted_amount=stripe_tx.converted_amount,
        stripe_fees=stripe_tx.fees,
        stripe_net=stripe_tx.net,
        stripe_converted_currency=stripe_tx.converted_currency,
        stripe_details=stripe_tx.details,
        stripe_customer_id=stripe_tx.customer_id,
        stripe_customer_email=stripe_tx.customer_email,
        stripe_customer_name=stripe_tx.customer_name,
        stripe_purpose_metadata=stripe_tx.purpose_metadata,
        stripe_phorest_client_id_metadata=stripe_tx.phorest_client_id_metadata,
        # Metadata
        match_type=match_type,
        process_number=process_number
    )

@app.route('/api/delete-all-matches/<int:job_id>/<int:subsidiary_id>', methods=['DELETE'])
def delete_all_matches(job_id, subsidiary_id):
    """Delete all matched transactions and reconciliation results for a specific job and subsidiary"""
    try:
        # Delete all matched transactions
        matched_deleted = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).delete()
        
        # Delete all reconciliation results
        results_deleted = ReconciliationResults.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).delete()
        
        db.session.commit()
        
        return jsonify({
            'message': 'All matches deleted successfully',
            'matched_transactions_deleted': matched_deleted,
            'reconciliation_results_deleted': results_deleted
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error deleting matches: {str(e)}'}), 500

@app.route('/api/delete-process-matches/<int:job_id>/<int:subsidiary_id>/<int:process_number>', methods=['DELETE'])
def delete_process_matches(job_id, subsidiary_id, process_number):
    """Delete matched transactions and results for a specific process and all subsequent processes"""
    try:
        # Delete matched transactions for the specified process and higher
        matched_deleted = MatchedTransaction.query.filter(
            MatchedTransaction.job_id == job_id,
            MatchedTransaction.subsidiary_id == subsidiary_id,
            MatchedTransaction.process_number >= process_number
        ).delete()
        
        # Delete reconciliation results for the specified process and higher
        results_deleted = ReconciliationResults.query.filter(
            ReconciliationResults.job_id == job_id,
            ReconciliationResults.subsidiary_id == subsidiary_id,
            ReconciliationResults.process_number >= process_number
        ).delete()
        
        db.session.commit()
        
        return jsonify({
            'message': f'Process {process_number}+ matches deleted successfully',
            'matched_transactions_deleted': matched_deleted,
            'reconciliation_results_deleted': results_deleted
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error deleting process matches: {str(e)}'}), 500

@app.route('/api/process1-match/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def process1_match(job_id, subsidiary_id):
    """Process 1: Match Stripe transactions with Cashbook transactions"""
    try:
        # Get all Stripe transactions for this job and subsidiary
        stripe_transactions = StripeTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        # Get all Cashbook transactions for this job and subsidiary
        cashbook_transactions = CashbookTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        if not stripe_transactions:
            return jsonify({'error': 'No Stripe transactions found'}), 400
        
        if not cashbook_transactions:
            return jsonify({'error': 'No Cashbook transactions found'}), 400
        
        # Find cutoff date (last ACTUAL transaction date in Stripe, excluding fees)
        # Exclude Stripe fees and Network Cost transactions
        actual_transactions = [
            t for t in stripe_transactions 
            if t.created and t.type not in ['Stripe Fee', 'Network Cost']
        ]
        
        if not actual_transactions:
            return jsonify({'error': 'No actual transactions found in Stripe data (only fees)'}), 400
        
        # Sort dates properly by parsing them as dates, not strings
        from datetime import datetime
        parsed_dates = []
        for tx in actual_transactions:
            try:
                date_obj = datetime.strptime(tx.created, '%d/%m/%Y')
                parsed_dates.append((date_obj, tx.created))
            except:
                continue  # Skip invalid dates
        
        if not parsed_dates:
            return jsonify({'error': 'No valid dates found in actual Stripe transactions'}), 400
        
        # Sort by date object and get the latest
        parsed_dates.sort(key=lambda x: x[0], reverse=True)
        cutoff_date = parsed_dates[0][1]  # Get the string format of the latest date
        
        # Route to EU-specific or standard matching logic
        if subsidiary_id == 4:  # EU
            print("[DEBUG] Using EU-specific Process 1 matching")
            matching_results = perform_matching_eu(stripe_transactions, cashbook_transactions, cutoff_date, job_id, subsidiary_id)
        else:
            # Standard matching for other subsidiaries
            matching_results = perform_matching(stripe_transactions, cashbook_transactions, cutoff_date, job_id, subsidiary_id)
        
        return jsonify({
            'message': 'Process 1 matching completed',
            'cutoff_date': cutoff_date,
            'matching_results': matching_results
        })
        
    except Exception as e:
        return jsonify({'error': f'Error in Process 1 matching: {str(e)}'}), 500

def perform_matching_eu(stripe_transactions, cashbook_transactions, cutoff_date, job_id, subsidiary_id):
    """
    EU-SPECIFIC Process 1: Perfect matching with AED currency handling
    EU has special requirements due to multi-currency (AED) and branch splitting
    """
    from datetime import datetime
    
    # Check for existing matches to prevent duplicates
    existing_matches = MatchedTransaction.query.filter_by(
        job_id=job_id,
        subsidiary_id=subsidiary_id,
        process_number=1
    ).all()
    
    if existing_matches:
        print(f"[EU DEBUG] Found {len(existing_matches)} existing Process 1 matches. Returning cached results.")
        
        # Get already-matched IDs
        matched_stripe_ids = {match.stripe_id for match in existing_matches}
        matched_cashbook_ids = {match.cashbook_id for match in existing_matches}
        
        # Convert cutoff_date
        if isinstance(cutoff_date, str):
            try:
                cutoff_date_obj = datetime.strptime(cutoff_date, '%d/%m/%Y').date()
            except:
                cutoff_date_obj = None
        else:
            cutoff_date_obj = cutoff_date
        
        # Find unmatched transactions
        unmatched_stripe = []
        unmatched_cashbook = []
        out_of_cutoff_cashbook = []
        
        for stripe_tx in stripe_transactions:
            if stripe_tx.id not in matched_stripe_ids:
                # Parse date
                if isinstance(stripe_tx.created, str):
                    try:
                        stripe_date = datetime.strptime(stripe_tx.created, '%d/%m/%Y %H:%M').date()
                    except:
                        try:
                            stripe_date = datetime.strptime(stripe_tx.created, '%d/%m/%Y').date()
                        except:
                            stripe_date = None
                else:
                    stripe_date = stripe_tx.created.date() if stripe_tx.created else None
                
                unmatched_stripe.append({
                    'id': stripe_tx.id,
                    'client_number': str(stripe_tx.client_number) if stripe_tx.client_number else "0",
                    'date': stripe_date,
                    'amount': stripe_tx.amount,
                    'currency': (stripe_tx.currency or '').upper()
                })
        
        for cashbook_tx in cashbook_transactions:
            if cashbook_tx.id not in matched_cashbook_ids:
                # Parse date
                if isinstance(cashbook_tx.payment_date, str):
                    try:
                        cashbook_date = datetime.strptime(cashbook_tx.payment_date, '%d/%m/%Y').date()
                    except:
                        cashbook_date = None
                else:
                    cashbook_date = cashbook_tx.payment_date.date() if cashbook_tx.payment_date else None
                
                # Check if out of cutoff
                if cashbook_date and cutoff_date_obj and cashbook_date > cutoff_date_obj:
                    out_of_cutoff_cashbook.append({
                        'id': cashbook_tx.id,
                        'client_id': cashbook_tx.client_id,
                        'date': cashbook_date,
                        'amount': cashbook_tx.amount,
                        'transtype': cashbook_tx.transtype
                    })
                else:
                    unmatched_cashbook.append({
                        'id': cashbook_tx.id,
                        'client_id': cashbook_tx.client_id,
                        'date': cashbook_date,
                        'amount': cashbook_tx.amount,
                        'transtype': cashbook_tx.transtype
                    })
        
        # Return existing matches
        matches = []
        for match in existing_matches:
            matches.append({
                'stripe_id': match.stripe_id,
                'cashbook_id': match.cashbook_id,
                'client_number': match.stripe_client_number,
                'date': match.stripe_created,
                'amount': float(match.stripe_amount) if match.stripe_amount else None,
                'currency': match.stripe_currency
            })
        
        return {
            'perfect_matches': {
                'count': len(matches),
                'transactions': matches
            },
            'unmatched_stripe': {
                'count': len(unmatched_stripe),
                'transactions': unmatched_stripe
            },
            'unmatched_cashbook': {
                'count': len(unmatched_cashbook),
                'transactions': unmatched_cashbook
            },
            'out_of_cutoff_cashbook': {
                'count': len(out_of_cutoff_cashbook),
                'transactions': out_of_cutoff_cashbook
            },
            'summary': {
                'total_stripe': len(stripe_transactions),
                'total_cashbook': len(cashbook_transactions),
                'perfect_matches': len(matches),
                'unmatched_stripe': len(unmatched_stripe),
                'unmatched_cashbook': len(unmatched_cashbook),
                'out_of_cutoff_cashbook': len(out_of_cutoff_cashbook)
            }
        }
    
    matches = []
    unmatched_stripe = []
    unmatched_cashbook = []
    out_of_cutoff_cashbook = []
    
    # Track matched IDs
    matched_stripe_ids = set()
    matched_cashbook_ids = set()
    
    # Convert cutoff_date string to date object if needed
    if isinstance(cutoff_date, str):
        try:
            cutoff_date_obj = datetime.strptime(cutoff_date, '%d/%m/%Y').date()
        except:
            cutoff_date_obj = None
    else:
        cutoff_date_obj = cutoff_date
    
    print(f"[EU DEBUG] Process 1: {len(stripe_transactions)} Stripe, {len(cashbook_transactions)} Cashbook")
    print(f"[EU DEBUG] Cutoff date: {cutoff_date_obj}")
    
    # OPTIMIZATION: Build a lookup dictionary for Cashbook transactions
    # Key: (client_id, date, amount, currency) -> list of cashbook_tx
    cashbook_lookup = {}
    for cashbook_tx in cashbook_transactions:
        cashbook_client = str(cashbook_tx.client_id) if cashbook_tx.client_id else "0"
        
        # Handle date - Cashbook stores as 'dd/mm/yyyy' string
        if isinstance(cashbook_tx.payment_date, str):
            try:
                # Correct format: dd/mm/yyyy (NOT mm/dd/yyyy!)
                cashbook_date = datetime.strptime(cashbook_tx.payment_date, '%d/%m/%Y').date()
            except Exception as e:
                print(f"[EU WARNING] Failed to parse Cashbook date '{cashbook_tx.payment_date}': {e}")
                continue
        else:
            cashbook_date = cashbook_tx.payment_date.date() if cashbook_tx.payment_date else None
        
        if not cashbook_date or cashbook_tx.amount is None:
            continue
        
        cashbook_currency = (cashbook_tx.currency or '').upper()
        # Round amount to 2 decimal places for consistent matching
        cashbook_amount = round(cashbook_tx.amount, 2)
        
        key = (cashbook_client, cashbook_date, cashbook_amount, cashbook_currency)
        if key not in cashbook_lookup:
            cashbook_lookup[key] = []
        cashbook_lookup[key].append(cashbook_tx)
    
    print(f"[EU DEBUG] Built lookup dictionary with {len(cashbook_lookup)} unique keys")
    
    # Process 1: Perfect matching (Client + Date + Amount) - OPTIMIZED
    match_count = 0
    for stripe_tx in stripe_transactions:
        # Skip Payment Failure Refund transactions - they should not be matched
        if stripe_tx.type == 'Payment Failure Refund':
            unmatched_stripe.append({
                'id': stripe_tx.id,
                'client_number': str(stripe_tx.client_number) if stripe_tx.client_number else "0",
                'date': stripe_tx.created,
                'amount': stripe_tx.amount,
                'currency': (stripe_tx.currency or '').upper()
            })
            continue
        
        # Get Stripe transaction details
        stripe_client = str(stripe_tx.client_number) if stripe_tx.client_number else "0"
        
        # Handle date - Stripe stores as 'dd/mm/yyyy' or 'dd/mm/yyyy HH:MM' string
        if isinstance(stripe_tx.created, str):
            try:
                # Try with time first: dd/mm/yyyy HH:MM
                stripe_date = datetime.strptime(stripe_tx.created, '%d/%m/%Y %H:%M').date()
            except:
                try:
                    # Try without time: dd/mm/yyyy
                    stripe_date = datetime.strptime(stripe_tx.created, '%d/%m/%Y').date()
                except Exception as e:
                    print(f"[EU WARNING] Failed to parse Stripe date '{stripe_tx.created}': {e}")
                    stripe_date = None
        else:
            stripe_date = stripe_tx.created.date() if stripe_tx.created else None
        
        stripe_currency = (stripe_tx.currency or '').upper()
        
        # For AED transactions, use ORIGINAL amount (not converted)
        if stripe_currency == 'AED':
            stripe_amount = stripe_tx.amount
        else:
            stripe_amount = stripe_tx.amount
        
        if not stripe_date or stripe_amount is None:
            unmatched_stripe.append({
                'id': stripe_tx.id,
                'client_number': stripe_client,
                'date': stripe_date,
                'amount': stripe_amount,
                'currency': stripe_currency
            })
            continue
        
        # Round amount for matching
        stripe_amount_rounded = round(stripe_amount, 2)
        
        # Look up in dictionary (O(1) instead of O(n))
        key = (stripe_client, stripe_date, stripe_amount_rounded, stripe_currency)
        candidate_cashbook = cashbook_lookup.get(key, [])
        
        matched = False
        for cashbook_tx in candidate_cashbook:
            if cashbook_tx.id in matched_cashbook_ids:
                continue
            
            # Found a match!
            match_count += 1
            if match_count % 100 == 0:
                print(f"[EU DEBUG] Matched {match_count} transactions...")
            
            # Create matched transaction
            matched_transaction = create_matched_transaction(
                stripe_tx, cashbook_tx, job_id, subsidiary_id, 'perfect_match', 1
            )
            db.session.add(matched_transaction)
            
            matches.append({
                'stripe_id': stripe_tx.id,
                'cashbook_id': cashbook_tx.id,
                'client_number': stripe_client,
                'date': stripe_date,
                'amount': stripe_amount,
                'currency': stripe_currency
            })
            
            matched_stripe_ids.add(stripe_tx.id)
            matched_cashbook_ids.add(cashbook_tx.id)
            matched = True
            break
        
        if not matched:
            unmatched_stripe.append({
                'id': stripe_tx.id,
                'client_number': stripe_client,
                'date': stripe_date,
                'amount': stripe_amount,
                'currency': stripe_currency
            })
    
    # Process remaining Cashbook transactions
    for cashbook_tx in cashbook_transactions:
        if cashbook_tx.id in matched_cashbook_ids:
            continue
        
        # Handle date - it might be string or datetime object
        if isinstance(cashbook_tx.payment_date, str):
            try:
                cashbook_date = datetime.strptime(cashbook_tx.payment_date, '%d/%m/%Y %H:%M:%S').date()
            except:
                try:
                    cashbook_date = datetime.strptime(cashbook_tx.payment_date, '%d/%m/%Y').date()
                except:
                    cashbook_date = None
        else:
            cashbook_date = cashbook_tx.payment_date.date() if cashbook_tx.payment_date else None
        
        # Check if out of cutoff
        if cashbook_date and cutoff_date_obj and cashbook_date > cutoff_date_obj:
            out_of_cutoff_cashbook.append({
                'id': cashbook_tx.id,
                'client_id': cashbook_tx.client_id,
                'date': cashbook_date,
                'amount': cashbook_tx.amount,
                'transtype': cashbook_tx.transtype
            })
        else:
            unmatched_cashbook.append({
                'id': cashbook_tx.id,
                'client_id': cashbook_tx.client_id,
                'date': cashbook_date,
                'amount': cashbook_tx.amount,
                'transtype': cashbook_tx.transtype
            })
    
    # Commit matches to database
    db.session.commit()
    
    print(f"[EU DEBUG] Process 1 Results: {len(matches)} perfect matches")
    
    # Save reconciliation results metadata (convert date back to string for storage)
    cutoff_date_str = cutoff_date if isinstance(cutoff_date, str) else cutoff_date_obj.strftime('%d/%m/%Y') if cutoff_date_obj else None
    reconciliation_result = ReconciliationResults(
        job_id=job_id,
        subsidiary_id=subsidiary_id,
        process_number=1,
        cutoff_date=cutoff_date_str,
        unmatched_stripe_count=len(unmatched_stripe),
        unmatched_cashbook_count=len(unmatched_cashbook),
        out_of_cutoff_count=len(out_of_cutoff_cashbook)
    )
    db.session.add(reconciliation_result)
    db.session.commit()
    
    # Return in the same format as standard perform_matching
    return {
        'perfect_matches': {
            'count': len(matches),
            'transactions': matches
        },
        'unmatched_stripe': {
            'count': len(unmatched_stripe),
            'transactions': unmatched_stripe
        },
        'unmatched_cashbook': {
            'count': len(unmatched_cashbook),
            'transactions': unmatched_cashbook
        },
        'out_of_cutoff_cashbook': {
            'count': len(out_of_cutoff_cashbook),
            'transactions': out_of_cutoff_cashbook
        },
        'summary': {
            'total_stripe': len(stripe_transactions),
            'total_cashbook': len(cashbook_transactions),
            'perfect_matches': len(matches),
            'unmatched_stripe': len(unmatched_stripe),
            'unmatched_cashbook': len(unmatched_cashbook),
            'out_of_cutoff_cashbook': len(out_of_cutoff_cashbook)
        }
    }

def perform_matching(stripe_transactions, cashbook_transactions, cutoff_date, job_id, subsidiary_id):
    """Perform the actual matching logic and save matches to database"""
    perfect_matches = []
    unmatched_stripe = []
    unmatched_cashbook = []
    out_of_cutoff_cashbook = []
    
    # Check for existing matches to prevent duplicates
    existing_matches = MatchedTransaction.query.filter_by(
        job_id=job_id,
        subsidiary_id=subsidiary_id,
        process_number=1
    ).all()
    
    if existing_matches:
        # Return existing results instead of creating duplicates
        existing_stripe_ids = {match.stripe_id for match in existing_matches}
        existing_cashbook_ids = {match.cashbook_id for match in existing_matches}
        
        # Filter out already matched transactions
        unmatched_stripe_tx = [tx for tx in stripe_transactions if tx.id not in existing_stripe_ids]
        unmatched_cashbook_tx = [tx for tx in cashbook_transactions if tx.id not in existing_cashbook_ids]
        
        # Convert cutoff date to comparable format
        cutoff_date_obj = None
        if cutoff_date:
            try:
                from datetime import datetime
                cutoff_date_obj = datetime.strptime(cutoff_date, '%d/%m/%Y')
            except:
                pass
        
        # Process unmatched transactions
        for stripe_tx in unmatched_stripe_tx:
            unmatched_stripe.append({
                'id': stripe_tx.id,
                'client_number': stripe_tx.client_number,
                'date': stripe_tx.created,
                'amount': stripe_tx.amount
            })
        
        for cashbook_tx in unmatched_cashbook_tx:
            is_out_of_cutoff = False
            if cutoff_date_obj and cashbook_tx.payment_date:
                try:
                    cashbook_date_obj = datetime.strptime(cashbook_tx.payment_date, '%d/%m/%Y')
                    if cashbook_date_obj > cutoff_date_obj:
                        is_out_of_cutoff = True
                except:
                    pass
            
            cashbook_info = {
                'id': cashbook_tx.id,
                'client_id': cashbook_tx.client_id,
                'date': cashbook_tx.payment_date,
                'amount': cashbook_tx.amount,
                'transtype': cashbook_tx.transtype
            }
            
            if is_out_of_cutoff:
                out_of_cutoff_cashbook.append(cashbook_info)
            else:
                unmatched_cashbook.append(cashbook_info)
        
        # Return existing matches plus new unmatched transactions
        return {
            'perfect_matches': {
                'count': len(existing_matches),
                'transactions': [{
                    'stripe_id': match.stripe_id,
                    'cashbook_id': match.cashbook_id,
                    'client_number': match.stripe_client_number,
                    'date': match.stripe_created,
                    'amount': float(match.stripe_amount) if match.stripe_amount else None,
                    'match_type': match.match_type
                } for match in existing_matches]
            },
            'unmatched_stripe': {
                'count': len(unmatched_stripe),
                'transactions': unmatched_stripe
            },
            'unmatched_cashbook': {
                'count': len(unmatched_cashbook),
                'transactions': unmatched_cashbook
            },
            'out_of_cutoff_cashbook': {
                'count': len(out_of_cutoff_cashbook),
                'transactions': out_of_cutoff_cashbook
            },
            'summary': {
                'total_stripe': len(stripe_transactions),
                'total_cashbook': len(cashbook_transactions),
                'perfect_matches': len(existing_matches),
                'unmatched_stripe': len(unmatched_stripe),
                'unmatched_cashbook': len(unmatched_cashbook),
                'out_of_cutoff_cashbook': len(out_of_cutoff_cashbook)
            }
        }
    
    # Convert cutoff date to comparable format
    cutoff_date_obj = None
    if cutoff_date:
        try:
            from datetime import datetime
            cutoff_date_obj = datetime.strptime(cutoff_date, '%d/%m/%Y')
        except:
            pass
    
    # Create a copy of cashbook transactions for matching
    available_cashbook = cashbook_transactions.copy()
    
    # Process each Stripe transaction
    for stripe_tx in stripe_transactions:
        # Skip Payment Failure Refund transactions - they should not be matched
        if stripe_tx.type == 'Payment Failure Refund':
            unmatched_stripe.append({
                'id': stripe_tx.id,
                'client_number': stripe_tx.client_number,
                'date': stripe_tx.created,
                'amount': stripe_tx.amount
            })
            continue
        
        matched = False
        
        # Look for matching Cashbook transaction
        for i, cashbook_tx in enumerate(available_cashbook):
            if is_perfect_match(stripe_tx, cashbook_tx):
                # Save match to database with ALL columns from BOTH files
                matched_transaction = create_matched_transaction(
                    stripe_tx, cashbook_tx, job_id, subsidiary_id, 'perfect', 1
                )
                db.session.add(matched_transaction)
                
                perfect_matches.append({
                    'stripe_id': stripe_tx.id,
                    'cashbook_id': cashbook_tx.id,
                    'client_number': stripe_tx.client_number,
                    'date': stripe_tx.created,
                    'amount': stripe_tx.amount,
                    'match_type': 'perfect'
                })
                
                # Remove matched cashbook transaction
                available_cashbook.pop(i)
                matched = True
                break
        
        if not matched:
            unmatched_stripe.append({
                'id': stripe_tx.id,
                'client_number': stripe_tx.client_number,
                'date': stripe_tx.created,
                'amount': stripe_tx.amount
            })
    
    # Categorize remaining cashbook transactions
    for cashbook_tx in available_cashbook:
        # Check if out of cutoff
        is_out_of_cutoff = False
        if cutoff_date_obj and cashbook_tx.payment_date:
            try:
                cashbook_date_obj = datetime.strptime(cashbook_tx.payment_date, '%d/%m/%Y')
                if cashbook_date_obj > cutoff_date_obj:
                    is_out_of_cutoff = True
            except:
                pass
        
        cashbook_info = {
            'id': cashbook_tx.id,
            'client_id': cashbook_tx.client_id,
            'date': cashbook_tx.payment_date,
            'amount': cashbook_tx.amount,
            'transtype': cashbook_tx.transtype
        }
        
        if is_out_of_cutoff:
            out_of_cutoff_cashbook.append(cashbook_info)
        else:
            unmatched_cashbook.append(cashbook_info)
    
    # Commit all matches to database
    db.session.commit()
    
    # Save reconciliation results metadata
    reconciliation_result = ReconciliationResults(
        job_id=job_id,
        subsidiary_id=subsidiary_id,
        process_number=1,
        cutoff_date=cutoff_date,
        unmatched_stripe_count=len(unmatched_stripe),
        unmatched_cashbook_count=len(unmatched_cashbook),
        out_of_cutoff_count=len(out_of_cutoff_cashbook)
    )
    db.session.add(reconciliation_result)
    db.session.commit()
    
    return {
        'perfect_matches': {
            'count': len(perfect_matches),
            'transactions': perfect_matches
        },
        'unmatched_stripe': {
            'count': len(unmatched_stripe),
            'transactions': unmatched_stripe
        },
        'unmatched_cashbook': {
            'count': len(unmatched_cashbook),
            'transactions': unmatched_cashbook
        },
        'out_of_cutoff_cashbook': {
            'count': len(out_of_cutoff_cashbook),
            'transactions': out_of_cutoff_cashbook
        },
        'summary': {
            'total_stripe': len(stripe_transactions),
            'total_cashbook': len(cashbook_transactions),
            'perfect_matches': len(perfect_matches),
            'unmatched_stripe': len(unmatched_stripe),
            'unmatched_cashbook': len(unmatched_cashbook),
            'out_of_cutoff_cashbook': len(out_of_cutoff_cashbook)
        }
    }

def is_perfect_match(stripe_tx, cashbook_tx):
    """Check if Stripe and Cashbook transactions are a perfect match"""
    # Match client number
    if stripe_tx.client_number != str(cashbook_tx.client_id):
        return False
    
    # Match date
    if stripe_tx.created != cashbook_tx.payment_date:
        return False
    
    # Match amount (with small tolerance for floating point)
    if abs((stripe_tx.amount or 0) - (cashbook_tx.amount or 0)) > 0.01:
        return False
    
    return True
@app.route('/api/start-reconciliation/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def start_reconciliation(job_id, subsidiary_id):
    try:
        # Get all Stripe transactions for this job and subsidiary
        stripe_transactions = StripeTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        if not stripe_transactions:
            return jsonify({'error': 'No Stripe transactions found for this job and subsidiary'}), 400
        
        # Calculate fees
        fees_calculation = calculate_stripe_fees(stripe_transactions)
        
        return jsonify({
            'message': 'Reconciliation started successfully',
            'fees_calculation': fees_calculation,
            'total_transactions': len(stripe_transactions)
        })
        
    except Exception as e:
        return jsonify({'error': f'Error starting reconciliation: {str(e)}'}), 500

def calculate_stripe_fees(stripe_transactions):
    """Calculate fees from Stripe transactions"""
    # 1. Column I Fees: All values in the "Fees" column
    column_i_fees = sum(
        transaction.fees for transaction in stripe_transactions 
        if transaction.fees is not None
    )
    
    # 2. Network Cost & Stripe Fee: Transactions where Type = "Network Cost" or "Stripe Fee"
    # These are negative in Stripe but should be displayed as positive fees
    network_cost_fees = sum(
        transaction.amount for transaction in stripe_transactions 
        if transaction.type == 'Network Cost' and transaction.amount is not None
    )
    
    stripe_fee_fees = sum(
        transaction.amount for transaction in stripe_transactions 
        if transaction.type == 'Stripe Fee' and transaction.amount is not None
    )
    
    # Convert negative totals to positive for display
    total_network_stripe_fees = abs(network_cost_fees + stripe_fee_fees)
    
    # Count transactions for each fee type
    column_i_count = sum(1 for t in stripe_transactions if t.fees is not None)
    network_cost_count = sum(1 for t in stripe_transactions if t.type == 'Network Cost')
    stripe_fee_count = sum(1 for t in stripe_transactions if t.type == 'Stripe Fee')
    
    return {
        'column_i_fees': {
            'total': round(column_i_fees, 2),
            'count': column_i_count,
            'description': 'All fees from Fees column'
        },
        'network_cost_fees': {
            'total': round(abs(network_cost_fees), 2),
            'count': network_cost_count,
            'description': 'Network Cost transactions (converted to positive)'
        },
        'stripe_fee_fees': {
            'total': round(abs(stripe_fee_fees), 2),
            'count': stripe_fee_count,
            'description': 'Stripe Fee transactions (converted to positive)'
        },
        'total_network_stripe_fees': round(total_network_stripe_fees, 2),
        'total_all_fees': round(column_i_fees + total_network_stripe_fees, 2)
    }

@app.route('/api/matched-transactions-results/<int:job_id>/<int:subsidiary_id>')
def get_matched_transactions_results(job_id, subsidiary_id):
    """Get persistent matched transaction results"""
    try:
        # Get all matched transactions for this job and subsidiary
        matched_transactions = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        if not matched_transactions:
            return jsonify({
                'perfect_matches': {'count': 0, 'transactions': []},
                'date_amount_matches': {'count': 0, 'transactions': []},
                'summary': {
                    'total_matched': 0,
                    'process1_matches': 0,
                    'process2_matches': 0
                }
            })
        
        # Separate by process
        process1_matches = [mt for mt in matched_transactions if mt.process_number == 1]
        process2_matches = [mt for mt in matched_transactions if mt.process_number == 2]
        
        # Format results
        perfect_matches = []
        for mt in process1_matches:
            perfect_matches.append({
                'stripe_id': mt.stripe_id,
                'cashbook_id': mt.cashbook_id,
                'client_number': mt.stripe_client_number,
                'date': mt.stripe_created,  # Fixed: was stripe_date
                'amount': float(mt.stripe_amount) if mt.stripe_amount else None,
                'match_type': mt.match_type
            })
        
        date_amount_matches = []
        for mt in process2_matches:
            date_amount_matches.append({
                'stripe_id': mt.stripe_id,
                'cashbook_id': mt.cashbook_id,
                'client_number': mt.stripe_client_number,
                'client_id': mt.cb_client_id,  # Fixed: was client_id
                'date': mt.stripe_created,  # Fixed: was stripe_date
                'amount': float(mt.stripe_amount) if mt.stripe_amount else None,
                'match_type': mt.match_type
            })
        
        # Get reconciliation metadata
        reconciliation_results = ReconciliationResults.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        # Get Process metadata
        process1_metadata = next((r for r in reconciliation_results if r.process_number == 1), None)
        process2_metadata = next((r for r in reconciliation_results if r.process_number == 2), None)
        process3_metadata = next((r for r in reconciliation_results if r.process_number == 3), None)
        
        return jsonify({
            'perfect_matches': {
                'count': len(perfect_matches),
                'transactions': perfect_matches
            },
            'date_amount_matches': {
                'count': len(date_amount_matches),
                'transactions': date_amount_matches
            },
            'summary': {
                'total_matched': len(matched_transactions),
                'process1_matches': len(process1_matches),
                'process2_matches': len(process2_matches)
            },
            'metadata': {
                'process1': {
                    'cutoff_date': process1_metadata.cutoff_date if process1_metadata else None,
                    'unmatched_stripe_count': process1_metadata.unmatched_stripe_count if process1_metadata else 0,
                    'unmatched_cashbook_count': process1_metadata.unmatched_cashbook_count if process1_metadata else 0,
                    'out_of_cutoff_count': process1_metadata.out_of_cutoff_count if process1_metadata else 0
                },
                'process2': {
                    'multiple_matches_count': process2_metadata.multiple_matches_count if process2_metadata else 0,
                    'unmatched_stripe_p2_count': process2_metadata.unmatched_stripe_p2_count if process2_metadata else 0,
                    'unmatched_cashbook_p2_count': process2_metadata.unmatched_cashbook_p2_count if process2_metadata else 0
                },
                'process3': {
                    'fees_count': process3_metadata.multiple_matches_count if process3_metadata else 0,
                    'refunds_count': process3_metadata.unmatched_stripe_p2_count if process3_metadata else 0,
                    'cross_subsidiary_count': process3_metadata.unmatched_cashbook_p2_count if process3_metadata else 0,
                    'near_matches_count': process3_metadata.out_of_cutoff_count if process3_metadata else 0,
                    'unmatched_stripe_count': process3_metadata.unmatched_stripe_count if process3_metadata else 0,
                    'unmatched_cashbook_count': process3_metadata.unmatched_cashbook_count if process3_metadata else 0
                }
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'Error retrieving matched transactions: {str(e)}'}), 500

# Journal Preparation API Endpoints
# HARD RULE: Journal creation uses SEPARATE tables with ONE-WAY SYNC
# Original data changes → Journal data updates
# Journal data changes → Original data NEVER affected

@app.route('/api/journals/sync/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def sync_journal_data(job_id, subsidiary_id):
    """Sync data from MatchedTransaction to JournalTransaction (ONE-WAY SYNC)"""
    try:
        from journal_generation.journal_sync import JournalSync
        
        # Get memo from request
        memo = request.json.get('memo', '') if request.is_json else ''
        
        # Create sync instance
        sync = JournalSync(db, {
            'MatchedTransaction': MatchedTransaction,
            'JournalTransaction': JournalTransaction
        })
        
        # Perform sync
        result = sync.sync_journal_data(job_id, subsidiary_id, memo)
        
        return jsonify({
            'success': True,
            'message': 'Journal data synced successfully',
            'result': result
        })
        
    except Exception as e:
        return jsonify({'error': f'Error syncing journal data: {str(e)}'}), 500

@app.route('/api/journals/clear/<int:job_id>/<int:subsidiary_id>', methods=['DELETE'])
def clear_journal_data(job_id, subsidiary_id):
    """Clear all journal data for a job/subsidiary"""
    try:
        from journal_generation.journal_sync import JournalSync
        
        # Create sync instance
        sync = JournalSync(db, {
            'MatchedTransaction': MatchedTransaction,
            'JournalTransaction': JournalTransaction
        })
        
        # Clear journal data
        success = sync.clear_journal_data(job_id, subsidiary_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Journal data cleared successfully'
            })
        else:
            return jsonify({'error': 'Failed to clear journal data'}), 500
        
    except Exception as e:
        return jsonify({'error': f'Error clearing journal data: {str(e)}'}), 500

@app.route('/api/journals/process-summit-installments/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def process_summit_installments(job_id, subsidiary_id):
    """Process Salon Summit Installments - TEMPORARILY DISABLED"""
    return jsonify({'success': False, 'error': 'Salon Summit functionality temporarily disabled'}), 503

@app.route('/api/prepare-perfect-matches-journal/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def prepare_perfect_matches_journal(job_id, subsidiary_id):
    """Prepare journal entries for perfect matches"""
    try:
        # Get perfect matches (Process 1)
        perfect_matches = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id,
            process_number=1,
            match_type='perfect'
        ).all()
        
        if not perfect_matches:
            return jsonify({'error': 'No perfect matches found'}), 404
        
        # For now, just return count - journal logic will be implemented later
        return jsonify({
            'message': 'Perfect matches journal preparation completed',
            'count': len(perfect_matches)
        })
        
    except Exception as e:
        return jsonify({'error': f'Error preparing perfect matches journal: {str(e)}'}), 500

@app.route('/api/prepare-date-amount-journal/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def prepare_date_amount_journal(job_id, subsidiary_id):
    """Prepare journal entries for date+amount matches"""
    try:
        # Get date+amount matches (Process 2)
        date_amount_matches = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id,
            process_number=2,
            match_type='date_amount_single'
        ).all()
        
        if not date_amount_matches:
            return jsonify({'error': 'No date+amount matches found'}), 404
        
        # For now, just return count - journal logic will be implemented later
        return jsonify({
            'message': 'Date+amount matches journal preparation completed',
            'count': len(date_amount_matches)
        })
        
    except Exception as e:
        return jsonify({'error': f'Error preparing date+amount journal: {str(e)}'}), 500

@app.route('/api/download-matched-transactions/<int:job_id>/<int:subsidiary_id>')
def download_matched_transactions(job_id, subsidiary_id):
    """Download all matched transactions as Excel file"""
    try:
        import pandas as pd
        import io
        from flask import send_file
        
        # Get all matched transactions
        matches = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        if not matches:
            return jsonify({'error': 'No matched transactions found'}), 404
        
        # Convert to list of dictionaries with ALL columns
        data = []
        for match in matches:
            row = {
                # Cashbook columns
                'CB Payment Date': match.cb_payment_date,
                'CB Client ID': match.cb_client_id,
                'CB Invoice Number': match.cb_invoice_number,
                'CB Billing Entity': match.cb_billing_entity,
                'CB AR Account': match.cb_ar_account,
                'CB Currency': match.cb_currency,
                'CB Exchange Rate': match.cb_exchange_rate,
                'CB Amount': match.cb_amount,
                'CB Account': match.cb_account,
                'CB Location': match.cb_location,
                'CB Transtype': match.cb_transtype,
                'CB Comment': match.cb_comment,
                'CB Card Reference': match.cb_card_reference,
                'CB Reasoncode': match.cb_reasoncode,
                'CB SEPA Provider': match.cb_sepaprovider,
                'CB Invoice #': match.cb_invoice_hash,
                'CB Payment #': match.cb_payment_hash,
                'CB Memo': match.cb_memo,
                # Stripe columns
                'Stripe Client Number': match.stripe_client_number,
                'Stripe Type': match.stripe_type,
                'Stripe ID': match.stripe_stripe_id,
                'Stripe Created': match.stripe_created,
                'Stripe Description': match.stripe_description,
                'Stripe Amount': match.stripe_amount,
                'Stripe Currency': match.stripe_currency,
                'Stripe Converted Amount': match.stripe_converted_amount,
                'Stripe Fees': match.stripe_fees,
                'Stripe Net': match.stripe_net,
                'Stripe Converted Currency': match.stripe_converted_currency,
                'Stripe Details': match.stripe_details,
                'Stripe Customer ID': match.stripe_customer_id,
                'Stripe Customer Email': match.stripe_customer_email,
                'Stripe Customer Name': match.stripe_customer_name,
                'Stripe Purpose Metadata': match.stripe_purpose_metadata,
                'Stripe Phorest Client ID Metadata': match.stripe_phorest_client_id_metadata,
                # Match info
                'Match Type': match.match_type,
                'Process Number': match.process_number
            }
            data.append(row)
        
        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Matched Transactions', index=False)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'matched_transactions_job_{job_id}_sub_{subsidiary_id}.xlsx'
        )
        
    except Exception as e:
        return jsonify({'error': f'Error downloading matched transactions: {str(e)}'}), 500

@app.route('/api/download-unmatched-stripe/<int:job_id>/<int:subsidiary_id>')
def download_unmatched_stripe(job_id, subsidiary_id):
    """Download unmatched Stripe transactions (charges and refunds only) as Excel file"""
    try:
        import pandas as pd
        import io
        from flask import send_file
        
        # Get all matched IDs
        matched_stripe_ids = set()
        matches = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        for match in matches:
            matched_stripe_ids.add(match.stripe_id)
        
        # Get all Stripe transactions for this subsidiary
        all_stripe = StripeTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        # Filter for unmatched charges and refunds
        unmatched = []
        for tx in all_stripe:
            if tx.id not in matched_stripe_ids:
                tx_type = (tx.type or '').lower()
                if tx_type == 'charge' or tx_type == 'refund':
                    unmatched.append({
                        'Client Number': tx.client_number,
                        'Type': tx.type,
                        'Stripe ID': tx.stripe_id,
                        'Created': tx.created,
                        'Description': tx.description,
                        'Amount': tx.amount,
                        'Currency': tx.currency,
                        'Converted Amount': tx.converted_amount,
                        'Fees': tx.fees,
                        'Net': tx.net,
                        'Converted Currency': tx.converted_currency,
                        'Details': tx.details,
                        'Customer ID': tx.customer_id,
                        'Customer Email': tx.customer_email,
                        'Customer Name': tx.customer_name,
                        'Purpose Metadata': tx.purpose_metadata,
                        'Phorest Client ID Metadata': tx.phorest_client_id_metadata
                    })
        
        if not unmatched:
            return jsonify({'error': 'No unmatched charge/refund transactions found'}), 404
        
        df = pd.DataFrame(unmatched)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Unmatched Stripe', index=False)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'unmatched_stripe_job_{job_id}_sub_{subsidiary_id}.xlsx'
        )
        
    except Exception as e:
        return jsonify({'error': f'Error downloading unmatched Stripe: {str(e)}'}), 500

@app.route('/api/download-unmatched-cashbook/<int:job_id>/<int:subsidiary_id>')
def download_unmatched_cashbook(job_id, subsidiary_id):
    """Download unmatched Cashbook transactions as Excel file"""
    try:
        import pandas as pd
        import io
        from flask import send_file
        
        # Get all matched IDs
        matched_cashbook_ids = set()
        matches = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        for match in matches:
            matched_cashbook_ids.add(match.cashbook_id)
        
        # Get all Cashbook transactions for this subsidiary
        all_cashbook = CashbookTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        # Get cutoff date from reconciliation results
        cutoff_date_str = None
        recon_result = ReconciliationResults.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id,
            process_number=1
        ).first()
        
        if recon_result and recon_result.cutoff_date:
            cutoff_date_str = recon_result.cutoff_date
        
        from datetime import datetime
        cutoff_date = None
        if cutoff_date_str:
            try:
                cutoff_date = datetime.strptime(cutoff_date_str, '%d/%m/%Y')
            except:
                pass
        
        # Filter for unmatched (excluding out of cutoff)
        unmatched = []
        for tx in all_cashbook:
            if tx.id not in matched_cashbook_ids:
                # Check if it's out of cutoff
                is_out_of_cutoff = False
                if cutoff_date and tx.payment_date:
                    try:
                        tx_date = datetime.strptime(tx.payment_date, '%d/%m/%Y')
                        if tx_date > cutoff_date:
                            is_out_of_cutoff = True
                    except:
                        pass
                
                if not is_out_of_cutoff:
                    unmatched.append({
                        'Payment Date': tx.payment_date,
                        'Client ID': tx.client_id,
                        'Invoice Number': tx.invoice_number,
                        'Billing Entity': tx.billing_entity,
                        'AR Account': tx.ar_account,
                        'Currency': tx.currency,
                        'Exchange Rate': tx.exchange_rate,
                        'Amount': tx.amount,
                        'Account': tx.account,
                        'Location': tx.location,
                        'Transtype': tx.transtype,
                        'Comment': tx.comment,
                        'Card Reference': tx.card_reference,
                        'Reasoncode': tx.reasoncode,
                        'SEPA Provider': tx.sepaprovider,
                        'Invoice #': tx.invoice_hash,
                        'Payment #': tx.payment_hash,
                        'Memo': tx.memo
                    })
        
        if not unmatched:
            return jsonify({'error': 'No unmatched cashbook transactions found'}), 404
        
        df = pd.DataFrame(unmatched)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Unmatched Cashbook', index=False)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'unmatched_cashbook_job_{job_id}_sub_{subsidiary_id}.xlsx'
        )
        
    except Exception as e:
        return jsonify({'error': f'Error downloading unmatched cashbook: {str(e)}'}), 500

@app.route('/api/download-master-upload-file/<int:job_id>/<int:subsidiary_id>')
def download_master_upload_file(job_id, subsidiary_id):
    """Download Master Upload File - All matched transactions in Cashbook format with correct client_id"""
    try:
        import pandas as pd
        import io
        from flask import send_file, request
        
        # Get memo from query parameter
        memo = request.args.get('memo', '')
        
        # Get all matched transactions
        matches = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        if not matches:
            return jsonify({'error': 'No matched transactions found'}), 404
        
        # Create DataFrame with Cashbook format (exact same as US.csv structure)
        # Using Cashbook data because it has the correct client_id
        data = []
        for match in matches:
            row = {
                'payment_date': match.cb_payment_date,
                'client_id': match.cb_client_id,  # Correct client number from Cashbook
                'invoice_number': match.cb_invoice_number,
                'billing_entity': match.cb_billing_entity,
                'ar_account': match.cb_ar_account,
                'currency': match.cb_currency,
                'exchange_rate': match.cb_exchange_rate,
                'amount': match.cb_amount,
                'account': match.cb_account,
                'Location': match.cb_location,
                'transtype': match.cb_transtype,
                'comment': match.cb_comment,
                'Card Reference': match.cb_card_reference,
                'reasoncode': match.cb_reasoncode,
                'sepaprovider': match.cb_sepaprovider,
                'invoice #': match.cb_invoice_hash,
                'payment #': match.cb_payment_hash,
                'Memo': memo if memo else match.cb_memo  # Use provided memo or original
            }
            data.append(row)
        
        df = pd.DataFrame(data)
        
        # Create CSV file in memory
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        # Convert to bytes
        output_bytes = io.BytesIO(output.getvalue().encode('utf-8'))
        
        # Get subsidiary name for filename
        subsidiary_names = {
            1: 'Australia',
            2: 'Canada',
            3: 'USA',
            4: 'EU',
            5: 'UK'
        }
        subsidiary_name = subsidiary_names.get(subsidiary_id, 'Unknown')
        
        return send_file(
            output_bytes,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'Master_Upload_File_{subsidiary_name}_Job{job_id}.csv'
        )
        
    except Exception as e:
        return jsonify({'error': f'Error downloading master upload file: {str(e)}'}), 500

@app.route('/api/download-split-journals/<int:job_id>/<int:subsidiary_id>')
def download_split_journals(job_id, subsidiary_id):
    """Download split journal files as a ZIP archive"""
    try:
        import pandas as pd
        import io
        import zipfile
        from flask import send_file, request
        
        # Get memo from query parameter
        memo = request.args.get('memo', '')
        
        # Get all matched transactions
        matches = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        if not matches:
            return jsonify({'error': 'No matched transactions found'}), 404
        
        # Get subsidiary info
        subsidiary_names = {
            1: 'Australia',
            2: 'Canada',
            3: 'USA',
            4: 'EU',
            5: 'UK'
        }
        subsidiary_name = subsidiary_names.get(subsidiary_id, 'Unknown')
        
        # Subsidiary billing entity mapping
        subsidiary_billing_entities = {
            1: "Ndevor Systems Ltd : Phorest Australia",
            2: "Ndevor Systems Ltd : Phorest Canada",
            3: "Ndevor Systems Ltd : Phorest US",
            4: "Ndevor Systems Ltd : Phorest Ireland",  # EU
            5: "Ndevor Systems Ltd : Phorest Ireland : Phorest UK"
        }
        current_billing_entity = subsidiary_billing_entities.get(subsidiary_id, '')
        
        # Prepare data
        refunds = []
        poa = []
        regular = []
        cross_subsidiary = {}
        
        for match in matches:
            row = {
                'payment_date': match.cb_payment_date,
                'client_id': match.cb_client_id,
                'invoice_number': match.cb_invoice_number,
                'billing_entity': match.cb_billing_entity,
                'ar_account': match.cb_ar_account,
                'currency': match.cb_currency,
                'exchange_rate': match.cb_exchange_rate,
                'amount': match.cb_amount,
                'account': match.cb_account,
                'Location': match.cb_location,
                'transtype': match.cb_transtype,
                'comment': match.cb_comment,
                'Card Reference': match.cb_card_reference,
                'reasoncode': match.cb_reasoncode,
                'sepaprovider': match.cb_sepaprovider,
                'invoice #': match.cb_invoice_hash,
                'payment #': match.cb_payment_hash,
                'Memo': memo if memo else match.cb_memo  # Use provided memo or original
            }
            
            # Check for cross-subsidiary transactions
            if match.cb_billing_entity and match.cb_billing_entity != current_billing_entity:
                if match.cb_billing_entity not in cross_subsidiary:
                    cross_subsidiary[match.cb_billing_entity] = []
                cross_subsidiary[match.cb_billing_entity].append(row)
            # Split by category (only for current subsidiary)
            elif match.cb_amount and match.cb_amount < 0:
                refunds.append(row)
            elif match.cb_invoice_number and 'POA' in str(match.cb_invoice_number).upper():
                poa.append(row)
            else:
                regular.append(row)
        
        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 1. Refunds Journal
            if refunds:
                df_refunds = pd.DataFrame(refunds)
                csv_buffer = io.StringIO()
                df_refunds.to_csv(csv_buffer, index=False)
                zip_file.writestr(f'Journals_For_Refunds_{subsidiary_name}.csv', csv_buffer.getvalue())
            
            # 2. POA Journal
            if poa:
                df_poa = pd.DataFrame(poa)
                csv_buffer = io.StringIO()
                df_poa.to_csv(csv_buffer, index=False)
                zip_file.writestr(f'POA_{subsidiary_name}.csv', csv_buffer.getvalue())
            
            # 3. Regular Journal
            if regular:
                df_regular = pd.DataFrame(regular)
                csv_buffer = io.StringIO()
                df_regular.to_csv(csv_buffer, index=False)
                zip_file.writestr(f'Journal_{subsidiary_name}.csv', csv_buffer.getvalue())
            
            # 4. Cross-subsidiary journals (if any)
            for billing_entity, transactions in cross_subsidiary.items():
                df_cross = pd.DataFrame(transactions)
                csv_buffer = io.StringIO()
                df_cross.to_csv(csv_buffer, index=False)
                # Clean up billing entity name for filename
                safe_name = billing_entity.replace(':', '').replace(' ', '_')
                zip_file.writestr(f'Journal_{safe_name}.csv', csv_buffer.getvalue())
            
            # 5. Summary file
            summary_data = {
                'Category': [],
                'Count': [],
                'Total Amount': []
            }
            
            if refunds:
                summary_data['Category'].append(f'Refunds - {subsidiary_name}')
                summary_data['Count'].append(len(refunds))
                summary_data['Total Amount'].append(sum(r['amount'] for r in refunds if r['amount']))
            
            if poa:
                summary_data['Category'].append(f'POA - {subsidiary_name}')
                summary_data['Count'].append(len(poa))
                summary_data['Total Amount'].append(sum(p['amount'] for p in poa if p['amount']))
            
            if regular:
                summary_data['Category'].append(f'Journal - {subsidiary_name}')
                summary_data['Count'].append(len(regular))
                summary_data['Total Amount'].append(sum(r['amount'] for r in regular if r['amount']))
            
            for billing_entity, transactions in cross_subsidiary.items():
                safe_name = billing_entity.replace(':', '').replace(' ', '_')
                summary_data['Category'].append(f'Cross-Sub - {safe_name}')
                summary_data['Count'].append(len(transactions))
                summary_data['Total Amount'].append(sum(t['amount'] for t in transactions if t['amount']))
            
            # Grand total
            summary_data['Category'].append('GRAND TOTAL')
            summary_data['Count'].append(len(matches))
            total_amount = sum(m.cb_amount for m in matches if m.cb_amount)
            summary_data['Total Amount'].append(total_amount)
            
            df_summary = pd.DataFrame(summary_data)
            csv_buffer = io.StringIO()
            df_summary.to_csv(csv_buffer, index=False)
            zip_file.writestr('_Summary.csv', csv_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'Split_Journals_{subsidiary_name}_Job{job_id}.zip'
        )
        
    except Exception as e:
        return jsonify({'error': f'Error downloading split journals: {str(e)}'}), 500

@app.route('/api/get-financial-summary/<int:job_id>/<int:subsidiary_id>')
def get_financial_summary(job_id, subsidiary_id):
    """Get complete financial summary for reconciliation (splits, refunds, fees, final total)"""
    try:
        # Get reconciliation results from all processes
        all_results = ReconciliationResults.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).order_by(ReconciliationResults.process_number).all()
        
        if not all_results:
            return jsonify({'error': 'No reconciliation results found. Please run Process 1, 2, and 3 first.'}), 404
        
        # Build metadata from all processes
        metadata = {}
        for result in all_results:
            if result.metadata:
                process_key = f'process{result.process_number}'
                metadata[process_key] = result.metadata
        
        # Get all matched transactions for split breakdown (excluding Salon Summit Installments)
        matches = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).filter(MatchedTransaction.match_type != 'Salon Summit Installment').all()
        
        if not matches:
            return jsonify({'error': 'No matched transactions found'}), 404
        
        # Subsidiary billing entity mapping
        subsidiary_billing_entities = {
            1: "Ndevor Systems Ltd : Phorest Australia",
            2: "Ndevor Systems Ltd : Phorest Canada",
            3: "Ndevor Systems Ltd : Phorest US",
            4: "Ndevor Systems Ltd : Phorest Ireland",  # EU
            5: "Ndevor Systems Ltd : Phorest Ireland : Phorest UK"
        }
        current_billing_entity = subsidiary_billing_entities.get(subsidiary_id, '')
        
        # Calculate split journals breakdown (from matched transactions)
        refunds_count = 0
        refunds_total = 0
        poa_count = 0
        poa_total = 0
        regular_count = 0
        regular_total = 0
        cross_sub_count = 0
        cross_sub_total = 0
        
        # Track AED transactions separately for EU
        aed_count = 0
        aed_total_eur = 0  # EUR equivalent used in calculations
        aed_total_aed = 0  # Original AED amount for display
        
        for match in matches:
            # Use Stripe amount for reconciliation (consistent with matching logic)
            # All transaction types use amount column for matching, so use amount for reconciliation
            amount = match.stripe_amount or 0  # Use amount column for all transactions
            original_amount = amount  # Keep original for AED tracking
            
            # For EU (subsidiary_id=4), track and convert AED transactions
            is_aed = False
            if subsidiary_id == 4:
                # Check if this is an AED transaction by looking at Stripe currency
                if match.stripe_currency and match.stripe_currency.upper() == 'AED':
                    is_aed = True
                    aed_count += 1
                    aed_total_aed += match.stripe_amount or 0  # Original AED amount from Stripe
                    # Use Stripe's converted amount (in EUR) for calculations
                    amount = match.stripe_converted_amount or amount
                    aed_total_eur += amount
            
            # Check for cross-subsidiary
            if match.cb_billing_entity and match.cb_billing_entity != current_billing_entity:
                cross_sub_count += 1
                cross_sub_total += amount
            # Check for refunds
            elif amount < 0:
                refunds_count += 1
                refunds_total += amount
            # Check for POA
            elif match.cb_invoice_number and 'POA' in str(match.cb_invoice_number).upper():
                poa_count += 1
                poa_total += amount
            # Regular
            else:
                regular_count += 1
                regular_total += amount
        
        splits_subtotal_count = refunds_count + poa_count + regular_count + cross_sub_count
        splits_subtotal = refunds_total + poa_total + regular_total + cross_sub_total
        
        # Get unmatched Stripe transactions (charges & refunds only) from Process 2
        # These are Stripe transactions that weren't matched in Process 1 or 2
        matched_stripe_ids = set()
        for match in matches:
            matched_stripe_ids.add(match.stripe_id)
        
        all_stripe = StripeTransaction.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).all()
        
        # Count unmatched stripe charges and refunds only (not fees)
        unmatched_refunds_count = 0
        unmatched_refunds_total = 0
        
        for tx in all_stripe:
            if tx.id not in matched_stripe_ids:
                tx_type = (tx.type or '').lower()
                # Only count 'charge' and 'refund' types
                if tx_type in ['charge', 'refund']:
                    unmatched_refunds_count += 1
                    # For EU, use converted EUR amount for AED transactions
                    if subsidiary_id == 4 and tx.currency and tx.currency.upper() == 'AED':
                        unmatched_refunds_total += tx.converted_amount or tx.amount or 0
                    else:
                        unmatched_refunds_total += tx.amount or 0
        
        # Calculate fees - same logic as calculate_stripe_fees function
        # 1. Column I Fees: All values in the "Fees" column (keep original sign)
        col_i_fees_total = sum(tx.fees for tx in all_stripe if tx.fees is not None)
        col_i_fees_count = sum(1 for tx in all_stripe if tx.fees is not None)
        
        # 2. Network Cost & Stripe Fee: Use AMOUNT column, convert negative to positive
        network_cost_fees = sum(tx.amount for tx in all_stripe if tx.type == 'Network Cost' and tx.amount is not None)
        stripe_fee_fees = sum(tx.amount for tx in all_stripe if tx.type == 'Stripe Fee' and tx.amount is not None)
        type_fees_total = abs(network_cost_fees + stripe_fee_fees)  # Convert negative to positive
        type_fees_count = sum(1 for tx in all_stripe if tx.type in ['Network Cost', 'Stripe Fee'])
        
        total_fees_count = col_i_fees_count + type_fees_count
        total_fees_total = col_i_fees_total + type_fees_total
        
        # Calculate Regular Transactions Net (Charges & Refunds only)
        # This is what the reconciliation should equal
        regular_transactions_net = 0
        for tx in all_stripe:
            tx_type = (tx.type or '').lower()
            if tx_type in ['charge', 'refund'] and tx.net is not None:
                regular_transactions_net += tx.net
        
        # Calculate Type-based Fees Net (Network Cost + Stripe Fee)
        type_fees_net = 0
        for tx in all_stripe:
            if tx.type in ['Network Cost', 'Stripe Fee'] and tx.net is not None:
                type_fees_net += tx.net
        
        # Calculate UNMATCHED Payment Failure Refunds
        # PFR are excluded from matching, so all PFR are unmatched
        # Use AMOUNT value but apply NET's sign (if Net is negative, make Amount negative)
        pfr_amount_signed = 0
        pfr_count = 0
        for tx in all_stripe:
            if tx.type == 'Payment Failure Refund':
                amount = tx.amount if tx.amount is not None else 0
                net = tx.net if tx.net is not None else 0
                # Apply Net's sign to Amount
                if net < 0:
                    pfr_amount_signed += -abs(amount)
                else:
                    pfr_amount_signed += abs(amount)
                pfr_count += 1
        
        # Calculate UNMATCHED Other Transactions (Adjustments, etc.)
        # Use AMOUNT value but apply NET's sign
        # Only include if they're NOT matched
        other_amount_signed = 0
        other_count = 0
        for tx in all_stripe:
            if tx.id not in matched_stripe_ids:  # Check if unmatched
                tx_type = (tx.type or '').lower()
                if tx_type not in ['charge', 'refund'] and tx.type not in ['Network Cost', 'Stripe Fee', 'Payment Failure Refund']:
                    amount = tx.amount if tx.amount is not None else 0
                    net = tx.net if tx.net is not None else 0
                    # Apply Net's sign to Amount
                    if net < 0:
                        other_amount_signed += -abs(amount)
                    else:
                        other_amount_signed += abs(amount)
                    other_count += 1
        
        # Total Stripe Net (all transactions) - this is what we're reconciling TO
        # Use NET column for all transactions (this is the actual Stripe net amount)
        total_stripe_net = sum(tx.net for tx in all_stripe if tx.net is not None)
        
        # CORRECT FORMULA:
        # Matched Stripe Amount + Unmatched C/R Amount - (Col I Fees + Type Fees) + PFR Amount (signed) + Other Amount (signed) = Total Stripe Net
        # Note: PFR and Other use AMOUNT value but with NET's sign (negative if Net < 0)
        # Calculate matched Stripe amount total (with AED conversions for EU)
        matched_stripe_total = 0
        for match in matches:
            amount = match.stripe_amount or 0
            # For EU (subsidiary_id=4), apply AED conversion
            if subsidiary_id == 4:
                if match.stripe_currency and match.stripe_currency.upper() == 'AED':
                    amount = match.stripe_converted_amount or amount
            matched_stripe_total += amount
        final_total = matched_stripe_total + unmatched_refunds_total - total_fees_total + pfr_amount_signed + other_amount_signed
        final_count = splits_subtotal_count + unmatched_refunds_count + pfr_count + other_count
        
        # Calculate variance against Total Stripe Net
        variance = final_total - total_stripe_net
        
        response_data = {
            'splits': {
                'refunds': {'count': refunds_count, 'total': refunds_total},
                'poa': {'count': poa_count, 'total': poa_total},
                'regular': {'count': regular_count, 'total': regular_total},
                'cross_subsidiary': {'count': cross_sub_count, 'total': cross_sub_total},
                'subtotal_count': splits_subtotal_count,
                'subtotal': splits_subtotal
            },
            'unmatched_refunds': {
                'count': unmatched_refunds_count,
                'total': unmatched_refunds_total
            },
            'fees': {
                'col_i_fees': {'count': col_i_fees_count, 'total': col_i_fees_total},
                'type_fees': {'count': type_fees_count, 'total': type_fees_total},
                'total_count': total_fees_count,
                'total': total_fees_total
            },
            'pfr': {
                'count': pfr_count,
                'total': pfr_amount_signed
            },
            'other': {
                'count': other_count,
                'total': other_amount_signed
            },
            'final': {
                'count': final_count,
                'total': final_total
            },
            'validation': {
                'total_stripe_net': total_stripe_net,
                'calculated_total': final_total,
                'variance': variance,
                'matches': abs(variance) < 0.01,  # Consider match if difference < 1 cent
                'breakdown': {
                    'regular_net': regular_transactions_net,
                    'type_fees_net': type_fees_net,
                    'pfr_amount': pfr_amount_signed,
                    'pfr_count': pfr_count,
                    'other_amount': other_amount_signed
                }
            }
        }
        
        # Add AED currency info for EU only
        if subsidiary_id == 4 and aed_count > 0:
            response_data['aed_currency'] = {
                'count': aed_count,
                'total_eur': aed_total_eur,  # EUR amount used in calculations
                'total_aed': aed_total_aed   # Original AED amount for display
            }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': f'Error getting financial summary: {str(e)}'}), 500

@app.route('/api/get-split-summary/<int:job_id>/<int:subsidiary_id>')
def get_split_summary(job_id, subsidiary_id):
    """Get summary of split journals (counts and totals) without generating files"""
    try:
        # Get all matched transactions
        matches = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        if not matches:
            return jsonify({'error': 'No matched transactions found'}), 404
        
        # Subsidiary billing entity mapping
        subsidiary_billing_entities = {
            1: "Ndevor Systems Ltd : Phorest Australia",
            2: "Ndevor Systems Ltd : Phorest Canada",
            3: "Ndevor Systems Ltd : Phorest US",
            4: "Ndevor Systems Ltd : Phorest Ireland",  # EU
            5: "Ndevor Systems Ltd : Phorest Ireland : Phorest UK"
        }
        current_billing_entity = subsidiary_billing_entities.get(subsidiary_id, '')
        
        # Count and calculate totals
        refunds_count = 0
        refunds_total = 0
        poa_count = 0
        poa_total = 0
        regular_count = 0
        regular_total = 0
        cross_sub_count = 0
        cross_sub_total = 0
        
        master_total = 0
        
        for match in matches:
            # Use Stripe amount (same as reconciliation summary)
            amount = match.stripe_amount or 0
            
            # For EU (subsidiary_id=4), use converted EUR amount for AED transactions
            if subsidiary_id == 4:
                # Check if this is an AED transaction by looking at Stripe currency
                if match.stripe_currency and match.stripe_currency.upper() == 'AED':
                    # Use Stripe's converted amount (in EUR) for calculations
                    amount = match.stripe_converted_amount or amount
            
            master_total += amount
            
            # Check for cross-subsidiary
            if match.cb_billing_entity and match.cb_billing_entity != current_billing_entity:
                cross_sub_count += 1
                cross_sub_total += amount
            # Check for refunds
            elif amount < 0:
                refunds_count += 1
                refunds_total += amount
            # Check for POA
            elif match.cb_invoice_number and 'POA' in str(match.cb_invoice_number).upper():
                poa_count += 1
                poa_total += amount
            # Regular
            else:
                regular_count += 1
                regular_total += amount
        
        splits_total = refunds_total + poa_total + regular_total + cross_sub_total
        
        return jsonify({
            'refunds': {'count': refunds_count, 'total': refunds_total},
            'poa': {'count': poa_count, 'total': poa_total},
            'regular': {'count': regular_count, 'total': regular_total},
            'cross_subsidiary': {'count': cross_sub_count, 'total': cross_sub_total},
            'master_total': master_total,
            'splits_total': splits_total,
            'match': abs(master_total - splits_total) < 0.01  # Floating point tolerance
        })
        
    except Exception as e:
        return jsonify({'error': f'Error getting split summary: {str(e)}'}), 500

@app.route('/api/download-individual-split/<int:job_id>/<int:subsidiary_id>/<split_type>')
def download_individual_split(job_id, subsidiary_id, split_type):
    """Download individual split journal file"""
    try:
        import pandas as pd
        import io
        from flask import send_file, request
        
        # Get memo from query parameter
        memo = request.args.get('memo', '')
        
        # Get all matched transactions
        matches = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        if not matches:
            return jsonify({'error': 'No matched transactions found'}), 404
        
        # Get subsidiary info
        subsidiary_names = {
            1: 'Australia',
            2: 'Canada',
            3: 'USA',
            4: 'EU',
            5: 'UK'
        }
        subsidiary_name = subsidiary_names.get(subsidiary_id, 'Unknown')
        
        # Subsidiary billing entity mapping
        subsidiary_billing_entities = {
            1: "Ndevor Systems Ltd : Phorest Australia",
            2: "Ndevor Systems Ltd : Phorest Canada",
            3: "Ndevor Systems Ltd : Phorest US",
            4: "Ndevor Systems Ltd : Phorest Ireland",  # EU
            5: "Ndevor Systems Ltd : Phorest Ireland : Phorest UK"
        }
        current_billing_entity = subsidiary_billing_entities.get(subsidiary_id, '')
        
        # Filter transactions based on split type
        filtered_transactions = []
        
        for match in matches:
            row = {
                'payment_date': match.cb_payment_date,
                'client_id': match.cb_client_id,
                'invoice_number': match.cb_invoice_number,
                'billing_entity': match.cb_billing_entity,
                'ar_account': match.cb_ar_account,
                'currency': match.cb_currency,
                'exchange_rate': match.cb_exchange_rate,
                'amount': match.cb_amount,
                'account': match.cb_account,
                'Location': match.cb_location,
                'transtype': match.cb_transtype,
                'comment': match.cb_comment,
                'Card Reference': match.cb_card_reference,
                'reasoncode': match.cb_reasoncode,
                'sepaprovider': match.cb_sepaprovider,
                'invoice #': match.cb_invoice_hash,
                'payment #': match.cb_payment_hash,
                'Memo': memo if memo else match.cb_memo
            }
            
            # Skip cross-subsidiary transactions (not from current subsidiary)
            if match.cb_billing_entity and match.cb_billing_entity != current_billing_entity:
                continue
            
            # Filter by type
            if split_type == 'refunds' and match.cb_amount and match.cb_amount < 0:
                filtered_transactions.append(row)
            elif split_type == 'poa' and match.cb_invoice_number and 'POA' in str(match.cb_invoice_number).upper():
                filtered_transactions.append(row)
            elif split_type == 'regular':
                # Regular = not refund, not POA, current subsidiary
                is_refund = match.cb_amount and match.cb_amount < 0
                is_poa = match.cb_invoice_number and 'POA' in str(match.cb_invoice_number).upper()
                if not is_refund and not is_poa:
                    filtered_transactions.append(row)
        
        if not filtered_transactions:
            return jsonify({'error': f'No {split_type} transactions found'}), 404
        
        df = pd.DataFrame(filtered_transactions)
        
        # Create CSV file in memory
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        # Convert to bytes
        output_bytes = io.BytesIO(output.getvalue().encode('utf-8'))
        
        # Determine filename
        if split_type == 'refunds':
            filename = f'Journals_For_Refunds_{subsidiary_name}.csv'
        elif split_type == 'poa':
            filename = f'POA_{subsidiary_name}.csv'
        else:  # regular
            filename = f'Journal_{subsidiary_name}.csv'
        
        return send_file(
            output_bytes,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({'error': f'Error downloading {split_type}: {str(e)}'}), 500

@app.route('/api/download-refunds-journal/<int:job_id>/<int:subsidiary_id>')
def download_refunds_journal(job_id, subsidiary_id):
    """Download unmatched Stripe refund transactions for journal entry"""
    try:
        import pandas as pd
        import io
        from flask import send_file
        
        # Get all matched Stripe IDs to exclude them
        matched_stripe_ids = set()
        matches = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        for match in matches:
            matched_stripe_ids.add(match.stripe_id)
        
        # Get all Stripe transactions
        all_stripe = StripeTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        # Filter for unmatched refunds (negative amount OR type='Refund')
        refunds = []
        for tx in all_stripe:
            if tx.id not in matched_stripe_ids:
                tx_type = (tx.type or '').lower()
                is_refund = (tx.amount and tx.amount < 0) or tx_type == 'refund'
                
                if is_refund:
                    refunds.append({
                        'Client Number': tx.client_number,
                        'Type': tx.type,
                        'Stripe ID': tx.stripe_id,
                        'Created': tx.created,
                        'Description': tx.description,
                        'Amount': tx.amount,
                        'Currency': tx.currency,
                        'Converted Amount': tx.converted_amount,
                        'Fees': tx.fees,
                        'Net': tx.net,
                        'Converted Currency': tx.converted_currency,
                        'Details': tx.details,
                        'Customer ID': tx.customer_id,
                        'Customer Email': tx.customer_email,
                        'Customer Name': tx.customer_name,
                        'Purpose Metadata': tx.purpose_metadata,
                        'Phorest Client ID Metadata': tx.phorest_client_id_metadata
                    })
        
        if not refunds:
            return jsonify({'error': 'No unmatched refund transactions found'}), 404
        
        df = pd.DataFrame(refunds)
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Refunds', index=False)
        
        output.seek(0)
        
        # Get subsidiary name for filename
        subsidiary_names = {
            1: 'Australia',
            2: 'Canada',
            3: 'USA',
            4: 'EU',
            5: 'UK'
        }
        subsidiary_name = subsidiary_names.get(subsidiary_id, 'Unknown')
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'Refunds_Journal_{subsidiary_name}_Job{job_id}.xlsx'
        )
        
    except Exception as e:
        return jsonify({'error': f'Error downloading refunds: {str(e)}'}), 500

@app.route('/api/download-out-of-cutoff/<int:job_id>/<int:subsidiary_id>')
def download_out_of_cutoff(job_id, subsidiary_id):
    """Download out of cutoff Cashbook transactions as Excel file"""
    try:
        import pandas as pd
        import io
        from flask import send_file
        
        # Get cutoff date from reconciliation results
        recon_result = ReconciliationResults.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id,
            process_number=1
        ).first()
        
        if not recon_result or not recon_result.cutoff_date:
            return jsonify({'error': 'Cutoff date not found'}), 404
        
        cutoff_date_str = recon_result.cutoff_date
        
        from datetime import datetime
        try:
            cutoff_date = datetime.strptime(cutoff_date_str, '%d/%m/%Y')
        except:
            return jsonify({'error': 'Invalid cutoff date format'}), 400
        
        # Get all Cashbook transactions for this subsidiary
        all_cashbook = CashbookTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        # Filter for out of cutoff
        out_of_cutoff = []
        for tx in all_cashbook:
            if tx.payment_date:
                try:
                    tx_date = datetime.strptime(tx.payment_date, '%d/%m/%Y')
                    if tx_date > cutoff_date:
                        out_of_cutoff.append({
                            'Payment Date': tx.payment_date,
                            'Client ID': tx.client_id,
                            'Invoice Number': tx.invoice_number,
                            'Billing Entity': tx.billing_entity,
                            'AR Account': tx.ar_account,
                            'Currency': tx.currency,
                            'Exchange Rate': tx.exchange_rate,
                            'Amount': tx.amount,
                            'Account': tx.account,
                            'Location': tx.location,
                            'Transtype': tx.transtype,
                            'Comment': tx.comment,
                            'Card Reference': tx.card_reference,
                            'Reasoncode': tx.reasoncode,
                            'SEPA Provider': tx.sepaprovider,
                            'Invoice #': tx.invoice_hash,
                            'Payment #': tx.payment_hash,
                            'Memo': tx.memo
                        })
                except:
                    pass
        
        if not out_of_cutoff:
            return jsonify({'error': 'No out of cutoff transactions found'}), 404
        
        df = pd.DataFrame(out_of_cutoff)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Out of Cutoff', index=False)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'out_of_cutoff_job_{job_id}_sub_{subsidiary_id}.xlsx'
        )
        
    except Exception as e:
        return jsonify({'error': f'Error downloading out of cutoff: {str(e)}'}), 500

@app.route('/api/prepare-fees-refunds-journal/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def prepare_fees_refunds_journal(job_id, subsidiary_id):
    """Prepare journal entries for fees and refunds"""
    try:
        # Get fees and refunds from Process 3 analysis
        reconciliation_results = ReconciliationResults.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id,
            process_number=3
        ).first()
        
        if not reconciliation_results:
            return jsonify({'error': 'Process 3 results not found'}), 404
        
        fees_count = reconciliation_results.multiple_matches_count
        refunds_count = reconciliation_results.unmatched_stripe_p2_count
        
        # For now, just return count - journal logic will be implemented later
        return jsonify({
            'message': 'Fees and refunds journal preparation completed',
            'count': fees_count + refunds_count,
            'fees': fees_count,
            'refunds': refunds_count
        })
        
    except Exception as e:
        return jsonify({'error': f'Error preparing fees/refunds journal: {str(e)}'}), 500

@app.route('/api/journal-preview/<int:job_id>/<int:subsidiary_id>')
def journal_preview(job_id, subsidiary_id):
    """Get journal entries preview"""
    try:
        # For now, return empty preview - will be implemented with actual journal logic
        return jsonify({
            'entries': []
        })
        
    except Exception as e:
        return jsonify({'error': f'Error loading journal preview: {str(e)}'}), 500

# ============================================================================
# JOURNAL GENERATION ENDPOINTS
# ============================================================================

@app.route('/api/journals/preview/<int:job_id>/<int:subsidiary_id>')
def preview_journals(job_id, subsidiary_id):
    """Get preview/summary of journals (existing or generate new)"""
    try:
        # Use EU-specific builder for EU subsidiary
        if subsidiary_id == 4:
            from journal_generation.journal_builder_eu import JournalBuilderEU
            builder_class = JournalBuilderEU
        else:
            from journal_generation.journal_builder import JournalBuilder
            builder_class = JournalBuilder
        
        # Check if journals have already been generated
        existing_journals = JournalTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).first()
        
        # Pass all models to JournalBuilder
        models = {
            'MatchedTransaction': MatchedTransaction,
            'StripeTransaction': StripeTransaction,
            'CashbookTransaction': CashbookTransaction,
            'JournalTransaction': JournalTransaction
        }
        builder = builder_class(db, job_id, subsidiary_id, models)
        
        if existing_journals:
            # Journals exist - return existing data
            result = builder.generate_all()
            result['journals_exist'] = True
            result['message'] = 'Showing existing journals. Use Clear Journals to regenerate.'
            return jsonify(result)
        else:
            # No journals exist - generate new ones
            result = builder.generate_all()
            if not result.get('success') and 'No matched transactions' in result.get('error', ''):
                result['needs_sync'] = True
            result['journals_exist'] = False
            result['message'] = 'Journals generated successfully.'
            return jsonify(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Error generating journal preview: {str(e)}'}), 500

# ============================================================================
# FURTHER PROCESSING (FP) ENDPOINTS
# ============================================================================

@app.route('/api/fp/status/<int:job_id>/<int:subsidiary_id>')
def fp_status(job_id, subsidiary_id):
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': True, 'status': 'empty', 'counts': {}, 'totals': {}, 'working_loaded': False})
        rows = FPJournalRow.query.filter_by(dataset_id=dataset.id).all()
        working_count = FPWorkingRow.query.filter_by(dataset_id=dataset.id).count()
        counts = {'total': len(rows)}
        totals = {'amount': float(sum((r.amount or 0) for r in rows))}
        return jsonify({'success': True, 'status': dataset.status, 'counts': counts, 'totals': totals, 'working_loaded': working_count > 0})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fp/clear/<int:job_id>/<int:subsidiary_id>', methods=['DELETE'])
def fp_clear(job_id, subsidiary_id):
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if dataset:
            FPJournalRow.query.filter_by(dataset_id=dataset.id).delete()
            FPWorkingRow.query.filter_by(dataset_id=dataset.id).delete()
            db.session.delete(dataset)
            db.session.commit()
        return jsonify({'success': True, 'message': 'Further processing data cleared'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fp/upload/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def fp_upload(job_id, subsidiary_id):
    try:
        # Prevent uploads if committed
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if dataset and dataset.status == 'committed':
            return jsonify({'success': False, 'error': 'Data already committed. Clear to upload again.'}), 409
        if not dataset:
            dataset = FPDataset(job_id=job_id, subsidiary_id=subsidiary_id, status='loaded')
            db.session.add(dataset)
            db.session.flush()

        payload = request.get_json(force=True)
        journal_type = payload.get('journal_type')  # 'Main' | 'POA' | 'Cross_Subsidiary'
        filename = payload.get('filename', 'uploaded.csv')
        rows = payload.get('rows', [])  # array of objects from CSV
        if journal_type not in ['Main', 'POA', 'Cross_Subsidiary']:
            return jsonify({'success': False, 'error': 'Invalid journal_type'}), 400
        created = 0
        for row in rows:
            amount = float(row.get('amount', 0) or 0)
            client_id = str(row.get('client_id') or row.get('Client') or '')
            invoice_number = str(row.get('invoice_number') or row.get('Invoice') or '')
            r = FPJournalRow(
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
            db.session.add(r)
            created += 1
        db.session.commit()
        return jsonify({'success': True, 'created': created, 'status': dataset.status})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fp/preview/<int:job_id>/<int:subsidiary_id>')
def fp_preview(job_id, subsidiary_id):
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': True, 'status': 'empty', 'journals': {}})
        by_type = {'Main': {'count': 0, 'total': 0.0}, 'POA': {'count': 0, 'total': 0.0}, 'Cross_Subsidiary': {'count': 0, 'total': 0.0}}
        rows = FPJournalRow.query.filter_by(dataset_id=dataset.id).all()
        for r in rows:
            info = by_type.get(r.journal_type)
            if info is not None:
                info['count'] += 1
                info['total'] += (r.amount or 0)
        for k in by_type:
            by_type[k]['total'] = float(by_type[k]['total'])
        return jsonify({'success': True, 'status': dataset.status, 'journals': by_type})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fp/commit/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def fp_commit(job_id, subsidiary_id):
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': False, 'error': 'No data to commit'}), 400
        if dataset.status == 'committed':
            return jsonify({'success': True, 'status': 'committed'})
        dataset.status = 'committed'
        db.session.commit()
        return jsonify({'success': True, 'status': 'committed'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fp/init', methods=['POST'])
def fp_init():
    """Create Further Processing tables if they don't exist."""
    try:
        # Create only FP tables if missing
        FPDataset.__table__.create(db.engine, checkfirst=True)
        FPJournalRow.__table__.create(db.engine, checkfirst=True)
        FPWorkingRow.__table__.create(db.engine, checkfirst=True)
        FPSummitInstallment.__table__.create(db.engine, checkfirst=True)
        FPProcessedJournal.__table__.create(db.engine, checkfirst=True)
        return jsonify({'success': True, 'message': 'FP tables are ready'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fp/load-combined/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def fp_load_combined(job_id, subsidiary_id):
    """Materialize all uploaded rows into one working table for further processing."""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': False, 'error': 'No dataset found. Upload and commit first.'}), 400
        if dataset.status != 'committed':
            return jsonify({'success': False, 'error': 'Dataset not committed. Click "Use this data" first.'}), 409
        # ensure table exists
        FPWorkingRow.__table__.create(db.engine, checkfirst=True)
        # if already loaded, block to enforce idempotency
        exists = FPWorkingRow.query.filter_by(dataset_id=dataset.id).first()
        if exists:
            return jsonify({'success': False, 'error': 'Combined dataset already loaded. Clear data to reload.'}), 409
        # copy rows
        rows = FPJournalRow.query.filter_by(dataset_id=dataset.id).all()
        created = 0
        for r in rows:
            wr = FPWorkingRow(
                dataset_id=dataset.id,
                job_id=job_id,
                subsidiary_id=subsidiary_id,
                source_journal_type=r.journal_type,
                client_id=r.client_id,
                invoice_number=r.invoice_number,
                amount=r.amount,
                row_json=r.row_json
            )
            db.session.add(wr)
            created += 1
        db.session.commit()
        return jsonify({'success': True, 'created': created})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fp/data/<int:job_id>/<int:subsidiary_id>')
def fp_data(job_id, subsidiary_id):
    """Return sample rows and totals from FP data (working if present else uploaded)."""
    try:
        source = request.args.get('source', 'auto')  # auto|working|uploaded
        limit = int(request.args.get('limit', '0'))  # 0 = no limit
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': True, 'rows': [], 'totals': {'count': 0, 'amount': 0.0}, 'source': 'none'})
        use_working = False
        if source == 'working' or source == 'auto':
            use_working = FPWorkingRow.query.filter_by(dataset_id=dataset.id).count() > 0
        rows_json = []
        total_amount = 0.0
        total_count = 0
        if use_working and source != 'uploaded':
            q = FPWorkingRow.query.filter_by(dataset_id=dataset.id)
            total_count = q.count()
            total_amount = float(sum((r.amount or 0) for r in q))
            for r in (q.limit(limit).all() if limit > 0 else q.all()):
                # Parse the stored JSON data
                row_data = {}
                if r.row_json:
                    try:
                        import json
                        row_data = json.loads(r.row_json)
                    except:
                        pass
                
                rows_json.append({
                    'source_journal_type': r.source_journal_type,
                    'client_id': r.client_id,
                    'invoice_number': r.invoice_number,
                    'billing_entity': row_data.get('billing_entity', ''),
                    'ar_account': row_data.get('ar_account', ''),
                    'currency': row_data.get('currency', ''),
                    'exchange_rate': row_data.get('exchange_rate', ''),
                    'amount': r.amount,
                    'account': row_data.get('account', ''),
                    'location': row_data.get('location', ''),
                    'transtype': row_data.get('transtype', ''),
                    'comment': row_data.get('comment', ''),
                    'card_reference': row_data.get('card_reference', ''),
                    'reasoncode': row_data.get('reasoncode', ''),
                    'sepaprovider': row_data.get('sepaprovider', ''),
                    'invoice_hash': row_data.get('invoice_hash', ''),
                    'payment_hash': row_data.get('payment_hash', ''),
                    'memo': row_data.get('memo', ''),
                    'payment_date': row_data.get('payment_date', '')
                })
            return jsonify({'success': True, 'rows': rows_json, 'totals': {'count': total_count, 'amount': total_amount}, 'source': 'working'})
        # fallback to uploaded
        q = FPJournalRow.query.filter_by(dataset_id=dataset.id)
        total_count = q.count()
        total_amount = float(sum((r.amount or 0) for r in q))
        for r in (q.limit(limit).all() if limit > 0 else q.all()):
            rows_json.append({
                'journal_type': r.journal_type,
                'client_id': r.client_id,
                'invoice_number': r.invoice_number,
                'billing_entity': r.billing_entity,
                'ar_account': r.ar_account,
                'currency': r.currency,
                'exchange_rate': r.exchange_rate,
                'amount': r.amount,
                'account': r.account,
                'location': r.location,
                'transtype': r.transtype,
                'comment': r.comment,
                'card_reference': r.card_reference,
                'reasoncode': r.reasoncode,
                'sepaprovider': r.sepaprovider,
                'invoice_hash': r.invoice_hash,
                'payment_hash': r.payment_hash,
                'memo': r.memo,
                'payment_date': r.payment_date,
                'filename': r.filename
            })
        return jsonify({'success': True, 'rows': rows_json, 'totals': {'count': total_count, 'amount': total_amount}, 'source': 'uploaded'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/fp-data/<int:job_id>/<int:subsidiary_id>')
def fp_data_viewer(job_id, subsidiary_id):
    """Serve the FP data viewer page."""
    return render_template('fp_data_viewer.html', job_id=job_id, subsidiary_id=subsidiary_id)

@app.route('/summit-details/<int:job_id>/<int:subsidiary_id>')
def summit_details(job_id, subsidiary_id):
    """Serve the summit details page."""
    return render_template('summit_details.html', job_id=job_id, subsidiary_id=subsidiary_id)

@app.route('/api/fp/summit-upload/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def fp_summit_upload(job_id, subsidiary_id):
    """Upload Salon Summit CSV data for processing - stores in persistent table."""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset or dataset.status != 'committed':
            return jsonify({'success': False, 'error': 'No committed dataset found'}), 400
        
        payload = request.get_json(force=True)
        summit_data = payload.get('summit_data', [])
        
        if not summit_data:
            return jsonify({'success': False, 'error': 'No summit data provided'}), 400
        
        # Check if summit data already uploaded
        existing = FPSummitInstallment.query.filter_by(dataset_id=dataset.id).first()
        if existing:
            return jsonify({'success': False, 'error': 'Summit data already uploaded. Clear to re-upload.'}), 409
        
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

@app.route('/api/fp/summit-process/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def fp_summit_process(job_id, subsidiary_id):
    """
    NEW SIMPLIFIED LOGIC:
    1. Check if summit data exists in FPSummitInstallment table
    2. Check if processed journal already exists (prevent duplicate processing)
    3. Copy FPJournalRow → FPProcessedJournal (fresh, unmodified copy of original data)
    4. Match summit clients against processed journal, reduce amounts
    5. Create new Salon_Summit_Installments rows in processed journal
    """
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset or dataset.status != 'committed':
            return jsonify({'success': False, 'error': 'No committed dataset found'}), 400
        
        # Check if summit data uploaded
        summit_installments = FPSummitInstallment.query.filter_by(dataset_id=dataset.id).all()
        if not summit_installments:
            return jsonify({'success': False, 'error': 'No summit data uploaded'}), 400
        
        # Check if already processed
        existing_processed = FPProcessedJournal.query.filter_by(dataset_id=dataset.id).first()
        if existing_processed:
            return jsonify({
                'success': False, 
                'error': 'Summit processing already complete. Clear to reprocess.'
            }), 409
        
        # Store original amounts before any processing (if not already stored)
        if not dataset.original_amounts:
            journal_rows = FPJournalRow.query.filter_by(dataset_id=dataset.id).all()
            original_amounts = {}
            for row in journal_rows:
                client_id = str(row.client_id).strip()
                if client_id:
                    if client_id not in original_amounts:
                        original_amounts[client_id] = 0
                    original_amounts[client_id] += float(row.amount or 0)
            
            dataset.original_amounts = json.dumps(original_amounts)
            db.session.commit()
        
        summit_data = json.loads(dataset.summit_data)
        
        # Combine duplicate client IDs by summing their amounts
        combined_summit_data = {}
        duplicates_combined = 0
        for item in summit_data:
            oak_id = str(item.get('oak_id', ''))
            installment_amount = float(item.get('installment_amount', 0))
            
            if oak_id:
                if oak_id in combined_summit_data:
                    combined_summit_data[oak_id] += installment_amount
                    duplicates_combined += 1
                else:
                    combined_summit_data[oak_id] = installment_amount
        
        # Convert back to list format
        processed_summit_data = []
        for oak_id, total_amount in combined_summit_data.items():
            if total_amount != 0:  # Only include non-zero amounts
                processed_summit_data.append({
                    'oak_id': oak_id,
                    'installment_amount': total_amount
                })
        
        # Get all working rows
        working_rows = FPWorkingRow.query.filter_by(dataset_id=dataset.id).all()
        if not working_rows:
            return jsonify({'success': False, 'error': 'No working data found'}), 400
        
        # Create lookup for working rows by client_id
        working_lookup = {}
        for row in working_rows:
            client_id = str(row.client_id).strip() if row.client_id else ''
            if client_id not in working_lookup:
                working_lookup[client_id] = []
            working_lookup[client_id].append(row)
        
        # Get original amounts for matching
        original_amounts = {}
        if dataset.original_amounts:
            original_amounts = json.loads(dataset.original_amounts)
        else:
            # Fallback to current amounts if original not stored
            for row in working_rows:
                client_id = str(row.client_id).strip()
                if client_id:
                    if client_id not in original_amounts:
                        original_amounts[client_id] = 0
                    original_amounts[client_id] += float(row.amount or 0)
        
        # Process summit installments
        matched_count = 0
        total_summit_amount = 0.0
        original_total = sum(original_amounts.values())
        
        # Debug logging to file
        with open('/tmp/summit_debug.log', 'w') as f:
            f.write(f"Processing {len(processed_summit_data)} summit items\n")
            f.write(f"Original amounts available for {len(original_amounts)} clients\n")
            f.write(f"Working lookup has {len(working_lookup)} clients\n\n")
        
        # Get all journal rows for updating
        journal_rows = FPJournalRow.query.filter_by(dataset_id=dataset.id).all()
        journal_lookup = {}
        for row in journal_rows:
            client_id = str(row.client_id).strip() if row.client_id else ''
            if client_id not in journal_lookup:
                journal_lookup[client_id] = []
            journal_lookup[client_id].append(row)
        
        summit_journal_rows = []
        unmatched_summit_lines = []
        
        for summit_item in processed_summit_data:
            oak_id = str(summit_item.get('oak_id', ''))
            installment_amount = float(summit_item.get('installment_amount', 0))
            
            if not oak_id or installment_amount <= 0:
                continue
            
            # Debug logging for all clients
            with open('/tmp/summit_debug.log', 'a') as f:
                f.write(f"\nProcessing client {oak_id} with installment ${installment_amount:.2f}\n")
                f.write(f"  In working_lookup: {oak_id in working_lookup}\n")
                f.write(f"  In original_amounts: {oak_id in original_amounts}\n")
                if oak_id in original_amounts:
                    f.write(f"  Original amount: ${original_amounts[oak_id]:.2f}\n")
            
            matched = False
            if oak_id in working_lookup and oak_id in original_amounts:
                # Use original amount for matching
                original_amount = original_amounts[oak_id]
                if original_amount >= installment_amount:
                    # Calculate total current amount across all rows for this client
                    total_current_amount = sum((row.amount or 0) for row in working_lookup[oak_id])
                    
                    # Debug logging
                    with open('/tmp/summit_debug.log', 'a') as f:
                        f.write(f"  Original: ${original_amount:.2f}, Current Total: ${total_current_amount:.2f}\n")
                        f.write(f"  Original >= Installment: {original_amount >= installment_amount}\n")
                        f.write(f"  Current Total > 0: {total_current_amount > 0}\n")
                    
                    if total_current_amount > 0:
                        with open('/tmp/summit_debug.log', 'a') as f:
                            f.write(f"  ✅ MATCHED - Proceeding with reduction\n")
                        # Reduce proportionally from each working row
                        for working_row in working_lookup[oak_id]:
                            current_amount = working_row.amount or 0
                            reduction = (current_amount / total_current_amount) * installment_amount
                            working_row.amount = current_amount - reduction
                        
                        # ALSO reduce the corresponding journal row amounts proportionally
                        if oak_id in journal_lookup:
                            for journal_row in journal_lookup[oak_id]:
                                if journal_row.journal_type != 'Salon_Summit_Installments':  # Don't modify summit rows
                                    current_amount = journal_row.amount or 0
                                    reduction = (current_amount / total_current_amount) * installment_amount
                                    journal_row.amount = current_amount - reduction
                                    # Update the row_json to reflect the new amount
                                    if journal_row.row_json:
                                        try:
                                            row_data = json.loads(journal_row.row_json)
                                            row_data['amount'] = current_amount - reduction
                                            journal_row.row_json = json.dumps(row_data)
                                        except:
                                            pass
                        
                        # Create summit journal row (use first working row as template)
                        if working_lookup[oak_id]:
                            first_working_row = working_lookup[oak_id][0]
                            summit_row_data = {
                                'source_journal_type': 'Salon_Summit_Installments',
                                'client_id': first_working_row.client_id,
                                'invoice_number': first_working_row.invoice_number,
                                'amount': installment_amount,
                                'row_json': first_working_row.row_json  # Copy all original data
                            }
                            summit_journal_rows.append(summit_row_data)
                        
                        # Mark as matched
                        matched = True
                        matched_count += 1
                        total_summit_amount += installment_amount
            
            # If not matched, add to unmatched lines
            if not matched:
                unmatched_summit_lines.append(summit_item)
        
        # Create new FPJournalRow entries for summit journal
        for summit_row in summit_journal_rows:
            # Parse original row data
            original_data = {}
            if summit_row['row_json']:
                try:
                    original_data = json.loads(summit_row['row_json'])
                except:
                    pass
            
            # Create new journal row with summit data
            summit_journal_row = FPJournalRow(
                dataset_id=dataset.id,
                job_id=job_id,
                subsidiary_id=subsidiary_id,
                journal_type='Salon_Summit_Installments',
                client_id=summit_row['client_id'],
                invoice_number=summit_row['invoice_number'],
                amount=summit_row['amount'],
                row_json=json.dumps({
                    **original_data,
                    'journal_type': 'Salon_Summit_Installments',
                    'amount': summit_row['amount'],
                    'memo': f'Salon Summit Installment - Client {summit_row["client_id"]}'
                }),
                filename='salon_summit_generated.csv'
            )
            db.session.add(summit_journal_row)
        
        db.session.commit()
        
        # Calculate total remaining amount after processing
        total_remaining_amount = 0.0
        for row in working_rows:
            total_remaining_amount += (row.amount or 0)
        
        # Calculate final total after processing
        # This should be: summit_amount + all_remaining_amounts_in_working_rows
        final_total = total_summit_amount + total_remaining_amount
        
        # Verification: final total should equal original total
        verification_passed = abs(final_total - original_total) < 0.01
        
        # Generate downloadable files after processing
        try:
            generated_files = generate_summit_journal_files(dataset.id, job_id, subsidiary_id, unmatched_summit_lines)
        except Exception as e:
            print(f"Warning: Could not generate journal files: {e}")
            generated_files = []

        # Debug: Calculate journal totals after processing
        journal_totals = {}
        journal_types = db.session.query(FPJournalRow.journal_type).filter_by(dataset_id=dataset.id).distinct().all()
        for journal_type_tuple in journal_types:
            journal_type = journal_type_tuple[0]
            journal_rows = FPJournalRow.query.filter_by(dataset_id=dataset.id, journal_type=journal_type).all()
            journal_totals[journal_type] = {
                'count': len(journal_rows),
                'total_amount': sum(row.amount or 0 for row in journal_rows)
            }
        
        # Calculate unmatched summit total
        unmatched_summit_total = sum(line.get('installment_amount', 0) for line in unmatched_summit_lines)
        
        return jsonify({
            'success': True,
            'matched_count': matched_count,
            'unmatched_count': len(unmatched_summit_lines),
            'total_summit_amount': total_summit_amount,
            'unmatched_summit_total': unmatched_summit_total,
            'total_remaining_amount': total_remaining_amount,
            'original_total': original_total,
            'final_total': final_total,
            'duplicates_combined': duplicates_combined,
            'verification_passed': verification_passed,
            'generated_files': generated_files,
            'journal_totals': journal_totals
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

def generate_summit_journal_files(dataset_id, job_id, subsidiary_id, unmatched_summit_lines=None):
    """Generate downloadable CSV files for all journals after summit processing."""
    import os
    import csv
    from datetime import datetime
    
    # Create output directory
    output_dir = f"generated_journals/job_{job_id}_sub_{subsidiary_id}"
    os.makedirs(output_dir, exist_ok=True)
    
    generated_files = []
    
    # Get all journal types from the dataset
    journal_types = db.session.query(FPJournalRow.journal_type).filter_by(dataset_id=dataset_id).distinct().all()
    
    for journal_type_tuple in journal_types:
        journal_type = journal_type_tuple[0]
        
        # Get all rows for this journal type
        rows = FPJournalRow.query.filter_by(dataset_id=dataset_id, journal_type=journal_type).all()
        
        if not rows:
            continue
            
        # Parse the first row to get column headers
        if rows[0].row_json:
            try:
                sample_data = json.loads(rows[0].row_json)
                headers = list(sample_data.keys())
            except:
                # Fallback to basic headers
                headers = ['payment_date', 'client_id', 'invoice_number', 'billing_entity', 
                          'ar_account', 'currency', 'exchange_rate', 'amount', 'account', 
                          'location', 'transtype', 'comment', 'card_reference', 'reasoncode', 
                          'sepaprovider', 'invoice_hash', 'payment_hash', 'memo']
        else:
            headers = ['payment_date', 'client_id', 'invoice_number', 'billing_entity', 
                      'ar_account', 'currency', 'exchange_rate', 'amount', 'account', 
                      'location', 'transtype', 'comment', 'card_reference', 'reasoncode', 
                      'sepaprovider', 'invoice_hash', 'payment_hash', 'memo']
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{journal_type}_{subsidiary_id}_{timestamp}.csv"
        filepath = os.path.join(output_dir, filename)
        
        # Write CSV file
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            
            for row in rows:
                if row.row_json:
                    try:
                        row_data = json.loads(row.row_json)
                        # Ensure amount is updated
                        row_data['amount'] = row.amount
                        writer.writerow(row_data)
                    except:
                        # Fallback to basic data
                        basic_data = {
                            'client_id': row.client_id,
                            'invoice_number': row.invoice_number,
                            'amount': row.amount,
                            'journal_type': row.journal_type
                        }
                        writer.writerow(basic_data)
        
        generated_files.append({
            'journal_type': journal_type,
            'filename': filename,
            'filepath': filepath,
            'row_count': len(rows),
            'total_amount': sum(row.amount or 0 for row in rows)
        })
    
    # Generate unmatched summit lines CSV
    if unmatched_summit_lines and len(unmatched_summit_lines) > 0:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unmatched_filename = f"Unmatched_Summit_Lines_{subsidiary_id}_{timestamp}.csv"
        unmatched_filepath = os.path.join(output_dir, unmatched_filename)
        
        # Write unmatched summit lines CSV
        with open(unmatched_filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['OAK ID', 'Region', 'Amount (Instalment)']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for line in unmatched_summit_lines:
                writer.writerow({
                    'OAK ID': line.get('oak_id', ''),
                    'Region': line.get('region', ''),
                    'Amount (Instalment)': line.get('installment_amount', 0)
                })
        
        generated_files.append({
            'journal_type': 'Unmatched_Summit_Lines',
            'filename': unmatched_filename,
            'filepath': unmatched_filepath,
            'row_count': len(unmatched_summit_lines),
            'total_amount': sum(line.get('installment_amount', 0) for line in unmatched_summit_lines)
        })
    
    return generated_files

@app.route('/api/fp/summit-status/<int:job_id>/<int:subsidiary_id>')
def fp_summit_status(job_id, subsidiary_id):
    """Check if Salon Summit processing has already been completed."""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': True, 'already_processed': False})
        
        # Check if summit journal exists
        existing_summit_journal = FPJournalRow.query.filter_by(
            dataset_id=dataset.id,
            journal_type='Salon_Summit_Installments'
        ).first()
        
        return jsonify({
            'success': True, 
            'already_processed': existing_summit_journal is not None
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fp/summit-details/<int:job_id>/<int:subsidiary_id>', methods=['GET'])
def fp_summit_details(job_id, subsidiary_id):
    """Get detailed matching information for Salon Summit processing."""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': False, 'error': 'No dataset found'}), 404
        
        if not dataset.summit_data:
            return jsonify({'success': False, 'error': 'No summit data found'}), 404
        
        # Get summit data
        summit_data = json.loads(dataset.summit_data)
        
        # Get original amounts (stored before any summit processing)
        if dataset.original_amounts:
            db_client_amounts = json.loads(dataset.original_amounts)
        else:
            # Fallback to current journal amounts if original not stored
            journal_rows = FPJournalRow.query.filter_by(dataset_id=dataset.id).all()
            db_client_amounts = {}
            for row in journal_rows:
                client_id = str(row.client_id).strip()
                if client_id:
                    if client_id not in db_client_amounts:
                        db_client_amounts[client_id] = 0
                    db_client_amounts[client_id] += float(row.amount or 0)
        
        # Process summit data and find matches
        summit_combined = {}
        for item in summit_data:
            oak_id = str(item.get('oak_id', '')).strip()
            amount = float(item.get('installment_amount', 0))
            if oak_id:
                if oak_id not in summit_combined:
                    summit_combined[oak_id] = 0
                summit_combined[oak_id] += amount
        
        # Get actual summit journal rows that were created
        summit_journal_rows = FPJournalRow.query.filter_by(
            dataset_id=dataset.id,
            journal_type='Salon_Summit_Installments'
        ).all()
        
        # Create lookup of actual summit amounts by client_id
        actual_summit_amounts = {}
        for row in summit_journal_rows:
            client_id = str(row.client_id).strip()
            if client_id:
                if client_id not in actual_summit_amounts:
                    actual_summit_amounts[client_id] = 0
                actual_summit_amounts[client_id] += float(row.amount or 0)
        
        # Find matches based on actual summit journal rows created
        matched_details = []
        unmatched_details = []
        
        for oak_id, summit_amount in summit_combined.items():
            if oak_id in actual_summit_amounts:
                # This client was actually processed and has summit journal rows
                actual_summit_amount = actual_summit_amounts[oak_id]
                if oak_id in db_client_amounts:
                    db_amount = db_client_amounts[oak_id]
                    invoice_amount = db_amount - actual_summit_amount
                    matched_details.append({
                        'oak_id': oak_id,
                        'summit_amount': actual_summit_amount,  # Use actual amount from summit journal
                        'invoice_amount': invoice_amount,
                        'total_amount': db_amount
                    })
                else:
                    matched_details.append({
                        'oak_id': oak_id,
                        'summit_amount': actual_summit_amount,
                        'invoice_amount': 0,
                        'total_amount': actual_summit_amount
                    })
            elif oak_id in db_client_amounts:
                # Client exists in database but wasn't processed (insufficient amount or other issue)
                db_amount = db_client_amounts[oak_id]
                if db_amount >= summit_amount:
                    unmatched_details.append({
                        'oak_id': oak_id,
                        'summit_amount': summit_amount,
                        'db_amount': db_amount,
                        'reason': 'Processing failed'
                    })
                else:
                    unmatched_details.append({
                        'oak_id': oak_id,
                        'summit_amount': summit_amount,
                        'db_amount': db_amount,
                        'reason': 'Insufficient amount'
                    })
            else:
                unmatched_details.append({
                    'oak_id': oak_id,
                    'summit_amount': summit_amount,
                    'reason': 'Not found in database'
                })
        
        # Calculate totals
        matched_total = sum(item['summit_amount'] for item in matched_details)
        unmatched_total = sum(item['summit_amount'] for item in unmatched_details)
        invoice_total = sum(item['invoice_amount'] for item in matched_details)
        
        return jsonify({
            'success': True,
            'matched': {
                'count': len(matched_details),
                'details': matched_details,
                'summit_total': matched_total,
                'invoice_total': invoice_total,
                'original_total': matched_total + invoice_total
            },
            'unmatched': {
                'count': len(unmatched_details),
                'details': unmatched_details,
                'total': unmatched_total
            },
            'grand_total': matched_total + unmatched_total
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fp/summit-clear/<int:job_id>/<int:subsidiary_id>', methods=['DELETE'])
def fp_summit_clear(job_id, subsidiary_id):
    """Clear Salon Summit data and restore original amounts."""
    try:
        dataset = FPDataset.query.filter_by(job_id=job_id, subsidiary_id=subsidiary_id).first()
        if not dataset:
            return jsonify({'success': False, 'error': 'No dataset found'}), 400
        
        # Store original amounts before clearing
        original_amounts = None
        if dataset.original_amounts:
            original_amounts = json.loads(dataset.original_amounts)
        
        # Clear summit data (but KEEP original_amounts for future reprocessing)
        dataset.summit_data = None
        
        # Remove summit journal rows
        FPJournalRow.query.filter_by(
            dataset_id=dataset.id,
            journal_type='Salon_Summit_Installments'
        ).delete()
        
        # Restore original amounts in journal rows and working rows
        if original_amounts:
            
            # Restore journal rows
            journal_rows = FPJournalRow.query.filter_by(dataset_id=dataset.id).all()
            for row in journal_rows:
                client_id = str(row.client_id).strip()
                if client_id in original_amounts:
                    row.amount = original_amounts[client_id]
                    # Update row_json to reflect original amount
                    if row.row_json:
                        try:
                            row_data = json.loads(row.row_json)
                            row_data['amount'] = original_amounts[client_id]
                            row.row_json = json.dumps(row_data)
                        except:
                            pass
            
            # Restore working rows
            working_rows = FPWorkingRow.query.filter_by(dataset_id=dataset.id).all()
            for row in working_rows:
                client_id = str(row.client_id).strip()
                if client_id in original_amounts:
                    row.amount = original_amounts[client_id]
                    # Update row_json to reflect original amount
                    if row.row_json:
                        try:
                            row_data = json.loads(row.row_json)
                            row_data['amount'] = original_amounts[client_id]
                            row.row_json = json.dumps(row_data)
                        except:
                            pass
        
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fp/download/<int:job_id>/<int:subsidiary_id>/<path:filename>')
def fp_download_file(job_id, subsidiary_id, filename):
    """Download a generated journal file."""
    try:
        filepath = f"generated_journals/job_{job_id}_sub_{subsidiary_id}/{filename}"
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, download_name=filename)
        else:
            return jsonify({'success': False, 'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fp/list-files/<int:job_id>/<int:subsidiary_id>')
def fp_list_files(job_id, subsidiary_id):
    """List all generated journal files for download."""
    try:
        output_dir = f"generated_journals/job_{job_id}_sub_{subsidiary_id}"
        files = []
        
        if os.path.exists(output_dir):
            for filename in os.listdir(output_dir):
                if filename.endswith('.csv'):
                    filepath = os.path.join(output_dir, filename)
                    file_size = os.path.getsize(filepath)
                    files.append({
                        'filename': filename,
                        'size': file_size,
                        'download_url': f'/api/fp/download/{job_id}/{subsidiary_id}/{filename}'
                    })
        
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/journals/status/<int:job_id>/<int:subsidiary_id>')
def journal_status(job_id, subsidiary_id):
    """Check if journals have been generated for this job/subsidiary"""
    try:
        # Check if journals exist
        existing_journals = JournalTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).first()
        
        if existing_journals:
            # Count total journals
            total_count = JournalTransaction.query.filter_by(
                job_id=job_id,
                subsidiary_id=subsidiary_id
            ).count()
            
            return jsonify({
                'success': True,
                'journals_exist': True,
                'total_journals': total_count,
                'message': 'Journals have been generated. Use Clear Journals to delete before regenerating.'
            })
        else:
            return jsonify({
                'success': True,
                'journals_exist': False,
                'total_journals': 0,
                'message': 'No journals generated yet. You can generate journals now.'
            })
            
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error checking journal status: {str(e)}'}), 500

@app.route('/api/journals/salon-summit-status/<int:job_id>/<int:subsidiary_id>')
def salon_summit_status(job_id, subsidiary_id):
    """Salon Summit functionality disabled"""
    return jsonify({'success': False, 'error': 'Salon Summit functionality temporarily disabled'}), 503

@app.route('/api/journals/process-salon-summit/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def process_salon_summit(job_id, subsidiary_id):
    """Salon Summit functionality disabled"""
    return jsonify({'success': False, 'error': 'Salon Summit functionality temporarily disabled'}), 503

@app.route('/api/journals/clear-salon-summit/<int:job_id>/<int:subsidiary_id>', methods=['DELETE'])
def clear_salon_summit(job_id, subsidiary_id):
    """Salon Summit functionality disabled"""
    return jsonify({'success': False, 'error': 'Salon Summit functionality temporarily disabled'}), 503

@app.route('/api/journals/download-master/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def download_master_journal(job_id, subsidiary_id):
    """Download the master journal file"""
    try:
        from journal_generation.journal_builder import JournalBuilder
        from flask import send_file
        
        data = request.get_json() or {}
        memo = data.get('memo', '')
        
        # Pass all models to JournalBuilder
        models = {
            'MatchedTransaction': MatchedTransaction,
            'StripeTransaction': StripeTransaction,
            'CashbookTransaction': CashbookTransaction,
            'JournalTransaction': JournalTransaction
        }
        builder = JournalBuilder(db, job_id, subsidiary_id, models)
        master_df = builder.generate_master_journal(memo)
        
        if master_df.empty:
            return jsonify({'error': 'No matched transactions found'}), 404
        
        # Export to Excel
        excel_file = builder.export_journal_to_excel(master_df, 'Master_Journal')
        
        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'Master_Journal_{builder.subsidiary_name}_Job{job_id}.xlsx'
        )
        
    except Exception as e:
        return jsonify({'error': f'Error downloading master journal: {str(e)}'}), 500

@app.route('/api/journals/download-split/<int:job_id>/<int:subsidiary_id>/<journal_type>', methods=['POST'])
def download_split_journal(job_id, subsidiary_id, journal_type):
    """Download a specific split journal"""
    try:
        from flask import send_file
        
        # Use EU-specific builder for subsidiary 4
        if subsidiary_id == 4:
            from journal_generation.journal_builder_eu import JournalBuilderEU
            builder_class = JournalBuilderEU
        else:
            from journal_generation.journal_builder import JournalBuilder
            builder_class = JournalBuilder
        
        data = request.get_json() or {}
        memo = data.get('memo', '')
        
        # Pass all models to JournalBuilder
        models = {
            'MatchedTransaction': MatchedTransaction,
            'StripeTransaction': StripeTransaction,
            'CashbookTransaction': CashbookTransaction,
            'JournalTransaction': JournalTransaction
        }
        builder = builder_class(db, job_id, subsidiary_id, models)
        master_df = builder.generate_master_journal(memo)
        
        if master_df.empty:
            return jsonify({'error': 'No matched transactions found'}), 404
        
        # Get split journals (pass memo for refunds journal)
        journals = builder.split_journals(master_df, memo)
        
        # Add Salon Summit Installments from database (only for non-EU builder)
        if hasattr(builder, '_get_salon_summit_installments'):
            salon_summit_df = builder._get_salon_summit_installments()
            if not salon_summit_df.empty:
                journals[f'Salon_Summit_Installments_{builder.subsidiary_name}'] = salon_summit_df
        
        # Find the requested journal
        journal_df = None
        for journal_name, df in journals.items():
            if journal_type.lower() in journal_name.lower():
                journal_df = df
                break
        
        if journal_df is None or journal_df.empty:
            return jsonify({'error': f'Journal type "{journal_type}" not found or empty'}), 404
        
        # Export to CSV
        csv_file = builder.export_journal_to_csv(journal_df, journal_type)
        
        return send_file(
            csv_file,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{journal_type}_{builder.subsidiary_name}_Job{job_id}.csv'
        )
        
    except Exception as e:
        return jsonify({'error': f'Error downloading split journal: {str(e)}'}), 500

@app.route('/api/process-installments/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def process_installments(job_id, subsidiary_id):
    """Process installment file and split matched transactions"""
    try:
        from flask import request
        import pandas as pd
        import io
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Read CSV file
        df = pd.read_csv(io.StringIO(file.read().decode('utf-8')))
        
        # Validate columns - support both formats
        if 'OAK ID' in df.columns and 'Total Amount Received' in df.columns and 'Amount (Instalment)' in df.columns:
            # Summit upload format - filter by region based on subsidiary
            region_mapping = {
                1: 'CANADA',    # Australia -> Canada (closest match)
                2: 'CANADA',    # Canada
                3: 'USA',       # USA
                4: 'IRELAND',   # EU
                5: 'UK'         # UK
            }
            
            target_region = region_mapping.get(subsidiary_id)
            if not target_region:
                return jsonify({'success': False, 'error': f'No region mapping found for subsidiary {subsidiary_id}'}), 400
            
            # Filter by region
            if 'Region' in df.columns:
                df = df[df['Region'] == target_region]
                if df.empty:
                    return jsonify({'success': False, 'error': f'No entries found for region {target_region} in summit file'}), 400
            else:
                return jsonify({'success': False, 'error': 'Summit file must have Region column'}), 400
            
            df = df.rename(columns={
                'OAK ID': 'client_id',
                'Total Amount Received': 'total_amount',
                'Amount (Instalment)': 'installment_amount'
            })
        elif 'client_id' not in df.columns or 'installment_amount' not in df.columns:
            return jsonify({'success': False, 'error': 'CSV must have columns: client_id, installment_amount OR OAK ID, Total Amount Received, Amount (Instalment)'}), 400
        
        # Get all matched transactions for this subsidiary
        matches = MatchedTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        ).all()
        
        if not matches:
            return jsonify({'success': False, 'error': 'No matched transactions found'}), 404
        
        # Process installments
        processed_count = 0
        split_count = 0
        installment_records = []
        
        for _, installment_row in df.iterrows():
            client_id = installment_row['client_id']
            
            # Clean and convert amounts (handle commas, spaces, and parentheses for negative numbers)
            def clean_amount(amount_str):
                if pd.isna(amount_str):
                    return 0.0
                
                # Convert to string and clean
                cleaned = str(amount_str).replace(',', '').strip()
                
                # Handle parentheses for negative numbers (e.g., "(93.28)" -> -93.28)
                if cleaned.startswith('(') and cleaned.endswith(')'):
                    cleaned = '-' + cleaned[1:-1]
                
                return float(cleaned) if cleaned else 0.0
            
            installment_amount = clean_amount(installment_row['installment_amount'])
            total_amount = clean_amount(installment_row.get('total_amount', installment_amount))  # Use total_amount if available
            
            # Find matching transactions
            for match in matches:
                if (match.cb_client_id == client_id and 
                    abs(float(match.cb_amount) - total_amount) < 0.01):  # Match on total amount with precise tolerance
                    
                    # Create installment record
                    installment_record = {
                        'client_id': client_id,
                        'installment_amount': installment_amount,
                        'original_amount': float(match.cb_amount),
                        'remaining_amount': float(match.cb_amount) - installment_amount,
                        'match_id': match.id
                    }
                    installment_records.append(installment_record)
                    processed_count += 1
                    
                    # Split the transaction
                    if installment_amount != 0:  # Process both positive and negative installments
                        # Create new installment transaction (Summit Journal gets the installment amount)
                        installment_match = MatchedTransaction(
                            job_id=match.job_id,
                            subsidiary_id=match.subsidiary_id,
                            stripe_id=match.stripe_id,
                            cashbook_id=match.cashbook_id,
                            match_type='Salon Summit Installment',
                            process_number=match.process_number,
                            
                            # Stripe data (same as original)
                            stripe_client_number=match.stripe_client_number,
                            stripe_type=match.stripe_type,
                            stripe_stripe_id=match.stripe_stripe_id,
                            stripe_created=match.stripe_created,
                            stripe_description=match.stripe_description,
                            stripe_amount=installment_amount,  # Summit Journal gets installment amount
                            stripe_currency=match.stripe_currency,
                            stripe_converted_amount=match.stripe_converted_amount,
                            stripe_fees=match.stripe_fees,
                            stripe_net=match.stripe_net,
                            stripe_converted_currency=match.stripe_converted_currency,
                            stripe_details=match.stripe_details,
                            stripe_customer_id=match.stripe_customer_id,
                            stripe_customer_email=match.stripe_customer_email,
                            stripe_customer_name=match.stripe_customer_name,
                            stripe_purpose_metadata=match.stripe_purpose_metadata,
                            stripe_phorest_client_id_metadata=match.stripe_phorest_client_id_metadata,
                            
                            # Cashbook data (modified for installment)
                            cb_payment_date=match.cb_payment_date,
                            cb_client_id=match.cb_client_id,
                            cb_invoice_number=match.cb_invoice_number + '-INSTALLMENT',
                            cb_billing_entity=match.cb_billing_entity,
                            cb_ar_account=match.cb_ar_account,
                            cb_currency=match.cb_currency,
                            cb_exchange_rate=match.cb_exchange_rate,
                            cb_amount=installment_amount,  # Summit Journal gets installment amount
                            cb_account=match.cb_account,
                            cb_location=match.cb_location,
                            cb_transtype=match.cb_transtype,
                            cb_comment=match.cb_comment + ' - Salon Summit Installment',
                            cb_card_reference=match.cb_card_reference,
                            cb_reasoncode=match.cb_reasoncode,
                            cb_sepaprovider=match.cb_sepaprovider,
                            cb_invoice_hash=(match.cb_invoice_hash if match.cb_invoice_hash and str(match.cb_invoice_hash) != 'nan' else '') + '-summit',
                            cb_payment_hash=(match.cb_payment_hash if match.cb_payment_hash and str(match.cb_payment_hash) != 'nan' else '') + '-summit',
                            cb_memo=match.cb_memo
                        )
                        
                        db.session.add(installment_match)
                        
                        # DO NOT modify the original matched transaction
                        # The journal generation will handle the splitting logic
                        
                        split_count += 1
                        break
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'processed_count': processed_count,
            'split_count': split_count,
            'installments': installment_records
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Error processing installments: {str(e)}'}), 500

@app.route('/api/journals/download-all/<int:job_id>/<int:subsidiary_id>', methods=['POST'])
def download_all_journals_new(job_id, subsidiary_id):
    """Download all journals as a ZIP file"""
    try:
        from flask import send_file
        import zipfile
        import io
        
        # Use EU-specific builder for subsidiary 4
        if subsidiary_id == 4:
            from journal_generation.journal_builder_eu import JournalBuilderEU
            builder_class = JournalBuilderEU
        else:
            from journal_generation.journal_builder import JournalBuilder
            builder_class = JournalBuilder
        
        data = request.get_json() or {}
        memo = data.get('memo', '')
        
        # Pass all models to JournalBuilder
        models = {
            'MatchedTransaction': MatchedTransaction,
            'StripeTransaction': StripeTransaction,
            'CashbookTransaction': CashbookTransaction,
            'JournalTransaction': JournalTransaction
        }
        builder = builder_class(db, job_id, subsidiary_id, models)
        all_journals = builder.export_all_journals(memo)
        
        if not all_journals:
            return jsonify({'error': 'No journals to export'}), 404
        
        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for journal_name, csv_file in all_journals.items():
                zip_file.writestr(
                    f'{journal_name}_{builder.subsidiary_name}_Job{job_id}.csv',
                    csv_file.getvalue()
                )
        
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'All_Journals_{builder.subsidiary_name}_Job{job_id}.zip'
        )
        
    except Exception as e:
        return jsonify({'error': f'Error downloading all journals: {str(e)}'}), 500

@app.route('/api/download-all-journals/<int:job_id>/<int:subsidiary_id>')
def download_all_journals(job_id, subsidiary_id):
    """Legacy endpoint - kept for compatibility"""
    try:
        import pandas as pd
        import io
        from flask import send_file
        
        # Redirect to new journal generation system
        from journal_generation.journal_builder import JournalBuilder
        
        # Pass all models to JournalBuilder
        models = {
            'MatchedTransaction': MatchedTransaction,
            'StripeTransaction': StripeTransaction,
            'CashbookTransaction': CashbookTransaction,
            'JournalTransaction': JournalTransaction
        }
        builder = JournalBuilder(db, job_id, subsidiary_id, models)
        result = builder.generate_all()
        
        if not result.get('success'):
            # Return empty file with message
            df = pd.DataFrame({'Message': [result.get('error', 'No journals available')]})
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Info', index=False)
            
            output.seek(0)
        else:
            # Generate master journal
            master_df = builder.generate_master_journal()
            excel_file = builder.export_journal_to_excel(master_df, 'Master_Journal')
            output = excel_file
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'journal_entries_job_{job_id}_sub_{subsidiary_id}.xlsx'
        )
        
    except Exception as e:
        return jsonify({'error': f'Error downloading journal entries: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)