from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Float, Numeric

# This will be imported by app.py after db is initialized
def create_models(db):
    """Create model classes with the provided db instance"""
    
    class Receipt(db.Model):
        """Receipt model for storing receipt file information"""
        __tablename__ = 'receipts'
        
        id = Column(Integer, primary_key=True)
        filename = Column(String(255), nullable=False)
        file_path = Column(String(500), nullable=False)
        status = Column(String(50), default='pending')  # pending, processing, completed, error
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        
        # Additional fields for receipt processing
        total_amount = Column(Float, nullable=True)
        vendor_name = Column(String(255), nullable=True)
        receipt_date = Column(DateTime, nullable=True)
        processed_data = Column(Text, nullable=True)  # JSON string of processed data
        
        def to_dict(self):
            """Convert model to dictionary for JSON serialization"""
            return {
                'id': self.id,
                'filename': self.filename,
                'file_path': self.file_path,
                'status': self.status,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
                'total_amount': self.total_amount,
                'vendor_name': self.vendor_name,
                'receipt_date': self.receipt_date.isoformat() if self.receipt_date else None,
                'processed_data': self.processed_data
            }

    class ProcessingJob(db.Model):
        """Model for tracking processing jobs"""
        __tablename__ = 'processing_jobs'
        
        id = Column(Integer, primary_key=True)
        job_name = Column(String(255), nullable=False)
        status = Column(String(50), default='pending')  # pending, running, completed, failed
        started_at = Column(DateTime, nullable=True)
        completed_at = Column(DateTime, nullable=True)
        error_message = Column(Text, nullable=True)
        created_at = Column(DateTime, default=datetime.utcnow)
        
        # Job configuration
        input_files = Column(Text, nullable=True)  # JSON string of input file paths
        output_files = Column(Text, nullable=True)  # JSON string of output file paths
        job_config = Column(Text, nullable=True)  # JSON string of job configuration
        
        def to_dict(self):
            """Convert model to dictionary for JSON serialization"""
            return {
                'id': self.id,
                'job_name': self.job_name,
                'status': self.status,
                'started_at': self.started_at.isoformat() if self.started_at else None,
                'completed_at': self.completed_at.isoformat() if self.completed_at else None,
                'error_message': self.error_message,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'input_files': self.input_files,
                'output_files': self.output_files,
                'job_config': self.job_config
            }
    
    class Subsidiary(db.Model):
        """Model for storing subsidiary information"""
        __tablename__ = 'subsidiaries'
        
        id = Column(Integer, primary_key=True)
        name = Column(String(255), nullable=False)
        code = Column(String(10), nullable=False, unique=True)
        region = Column(String(100), nullable=True)
        is_active = Column(Boolean, default=True)
        created_at = Column(DateTime, default=datetime.utcnow)
        
        def to_dict(self):
            """Convert model to dictionary for JSON serialization"""
            return {
                'id': self.id,
                'name': self.name,
                'code': self.code,
                'region': self.region,
                'is_active': self.is_active,
                'created_at': self.created_at.isoformat() if self.created_at else None
            }
    
    class StripeTransaction(db.Model):
        """Model for storing Stripe transaction data from CSV uploads"""
        __tablename__ = 'stripe_transactions'
        
        id = Column(Integer, primary_key=True)
        subsidiary_id = Column(Integer, nullable=False)  # Link to subsidiary
        job_id = Column(Integer, nullable=False)  # Link to reconciliation job
        
        # CSV columns (renamed first column from "0" to "client_number")
        client_number = Column(String(50), nullable=True)  # Renamed from "0"
        description_client_id = Column(String(50), nullable=True)  # Extracted from Description column (e.g., "41823:Company Name")
        type = Column(String(100), nullable=True)
        stripe_id = Column(String(255), nullable=True)  # ID column
        created = Column(String(100), nullable=True)  # Created date
        description = Column(Text, nullable=True)
        amount = Column(Float, nullable=True)
        currency = Column(String(10), nullable=True)
        converted_amount = Column(Float, nullable=True)
        fees = Column(Float, nullable=True)
        net = Column(Float, nullable=True)
        converted_currency = Column(String(10), nullable=True)
        details = Column(Text, nullable=True)
        customer_id = Column(String(255), nullable=True)
        customer_email = Column(String(255), nullable=True)
        customer_name = Column(String(255), nullable=True)
        purpose_metadata = Column(String(255), nullable=True)
        phorest_client_id_metadata = Column(String(255), nullable=True)
        
        # Metadata
        uploaded_at = Column(DateTime, default=datetime.utcnow)
        filename = Column(String(255), nullable=True)
        
        def to_dict(self):
            """Convert model to dictionary for JSON serialization"""
            return {
                'id': self.id,
                'subsidiary_id': self.subsidiary_id,
                'job_id': self.job_id,
                'client_number': self.client_number,
                'description_client_id': self.description_client_id,
                'type': self.type,
                'stripe_id': self.stripe_id,
                'created': self.created,
                'description': self.description,
                'amount': self.amount,
                'currency': self.currency,
                'converted_amount': self.converted_amount,
                'fees': self.fees,
                'net': self.net,
                'converted_currency': self.converted_currency,
                'details': self.details,
                'customer_id': self.customer_id,
                'customer_email': self.customer_email,
                'customer_name': self.customer_name,
                'purpose_metadata': self.purpose_metadata,
                'phorest_client_id_metadata': self.phorest_client_id_metadata,
                'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
                'filename': self.filename
            }
    
    class CashbookTransaction(db.Model):
        """Model for storing Cashbook transaction data from Excel uploads"""
        __tablename__ = 'cashbook_transactions'
        
        id = Column(Integer, primary_key=True)
        subsidiary_id = Column(Integer, nullable=False)  # Link to subsidiary
        job_id = Column(Integer, nullable=False)  # Link to reconciliation job
        
        # All 18 columns from Cashbookaus.xlsx
        payment_date = Column(String(20), nullable=True)  # Payment Date in dd/mm/yyyy format
        client_id = Column(Integer, nullable=True)  # This will match with Stripe client_number
        invoice_number = Column(String(255), nullable=True)
        billing_entity = Column(String(500), nullable=True)
        ar_account = Column(String(500), nullable=True)
        currency = Column(String(10), nullable=True)
        exchange_rate = Column(Float, nullable=True)
        amount = Column(Float, nullable=True)
        account = Column(String(500), nullable=True)
        location = Column(String(100), nullable=True)  # Location column
        transtype = Column(String(100), nullable=True)
        comment = Column(Text, nullable=True)
        card_reference = Column(Float, nullable=True)  # Card Reference column
        reasoncode = Column(Float, nullable=True)
        sepaprovider = Column(String(255), nullable=True)
        invoice_hash = Column(String(255), nullable=True)  # invoice # column
        payment_hash = Column(String(255), nullable=True)  # payment # column
        memo = Column(Float, nullable=True)  # Memo column
        
        # Metadata
        uploaded_at = Column(DateTime, default=datetime.utcnow)
        filename = Column(String(255), nullable=True)
        
        def to_dict(self):
            """Convert model to dictionary for JSON serialization"""
            return {
                'id': self.id,
                'subsidiary_id': self.subsidiary_id,
                'job_id': self.job_id,
                'payment_date': self.payment_date,  # Already a string in dd/mm/yyyy format
                'client_id': self.client_id,
                'invoice_number': self.invoice_number,
                'billing_entity': self.billing_entity,
                'ar_account': self.ar_account,
                'currency': self.currency,
                'exchange_rate': self.exchange_rate,
                'amount': self.amount,
                'account': self.account,
                'location': self.location,
                'transtype': self.transtype,
                'comment': self.comment,
                'card_reference': self.card_reference,
                'reasoncode': self.reasoncode,
                'sepaprovider': self.sepaprovider,
                'invoice_hash': self.invoice_hash,
                'payment_hash': self.payment_hash,
                'memo': self.memo,
                'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
                'filename': self.filename
            }
    
    class LookerCashbookTransaction(db.Model):
        """Model for storing Looker Cashbook transaction data from Excel uploads"""
        __tablename__ = 'looker_cashbook_transactions'
        
        id = Column(Integer, primary_key=True)
        job_id = Column(Integer, nullable=False)  # Link to reconciliation job
        
        # All 16 columns from cashbookraw.xlsx
        unnamed_index = Column(Integer, nullable=True)  # Unnamed: 0 column
        payment_date = Column(String(20), nullable=True)  # Payment Date in dd/mm/yyyy format
        client_id = Column(Integer, nullable=True)  # Client ID
        invoice_number = Column(String(255), nullable=True)  # Invoice Number
        billing_entity = Column(String(500), nullable=True)  # Billing Entity
        ar_account = Column(String(500), nullable=True)  # AR Account
        currency = Column(String(10), nullable=True)  # Currency
        exchange_rate = Column(Integer, nullable=True)  # Exchange Rate
        amount = Column(Float, nullable=True)  # Amount
        account = Column(String(500), nullable=True)  # Account
        location = Column(String(100), nullable=True)  # Location
        transtype = Column(String(100), nullable=True)  # Transtype
        comment = Column(Text, nullable=True)  # Comment
        reasoncode = Column(Integer, nullable=True)  # Reasoncode
        sepa_provider = Column(String(255), nullable=True)  # SEPA Provider
        stripe_charge_id = Column(String(255), nullable=True)  # Stripechargeid
        
        # Metadata
        uploaded_at = Column(DateTime, default=datetime.utcnow)
        filename = Column(String(255), nullable=True)
        
        def to_dict(self):
            """Convert model to dictionary for JSON serialization"""
            return {
                'id': self.id,
                'job_id': self.job_id,
                'unnamed_index': self.unnamed_index,
                'payment_date': self.payment_date,  # Already a string in dd/mm/yyyy format
                'client_id': self.client_id,
                'invoice_number': self.invoice_number,
                'billing_entity': self.billing_entity,
                'ar_account': self.ar_account,
                'currency': self.currency,
                'exchange_rate': self.exchange_rate,
                'amount': self.amount,
                'account': self.account,
                'location': self.location,
                'transtype': self.transtype,
                'comment': self.comment,
                'reasoncode': self.reasoncode,
                'sepa_provider': self.sepa_provider,
                'stripe_charge_id': self.stripe_charge_id,
                'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
                'filename': self.filename
            }

    class MatchedTransaction(db.Model):
        """Model for storing matched transactions with ALL columns from BOTH Cashbook AND Stripe files"""
        __tablename__ = 'matched_transactions'
        
        id = Column(Integer, primary_key=True)
        job_id = Column(Integer, nullable=False)
        subsidiary_id = Column(Integer, nullable=False)
        
        # ============ ALL CASHBOOK COLUMNS ============
        cashbook_id = Column(Integer, nullable=False)  # Reference to original cashbook transaction
        cb_payment_date = Column(String(20), nullable=True)  # Payment Date
        cb_client_id = Column(Integer, nullable=True)  # Client ID
        cb_invoice_number = Column(String(255), nullable=True)  # Invoice Number
        cb_billing_entity = Column(String(500), nullable=True)  # Billing Entity
        cb_ar_account = Column(String(500), nullable=True)  # AR Account
        cb_currency = Column(String(10), nullable=True)  # Currency
        cb_exchange_rate = Column(Float, nullable=True)  # Exchange Rate
        cb_amount = Column(Float, nullable=True)  # Amount
        cb_account = Column(String(500), nullable=True)  # Account
        cb_location = Column(String(100), nullable=True)  # Location
        cb_transtype = Column(String(100), nullable=True)  # Transtype
        cb_comment = Column(Text, nullable=True)  # Comment
        cb_card_reference = Column(Float, nullable=True)  # Card Reference
        cb_reasoncode = Column(Float, nullable=True)  # Reasoncode
        cb_sepaprovider = Column(String(255), nullable=True)  # SEPA Provider
        cb_invoice_hash = Column(String(255), nullable=True)  # Invoice #
        cb_payment_hash = Column(String(255), nullable=True)  # Payment #
        cb_memo = Column(Float, nullable=True)  # Memo
        
        # ============ ALL STRIPE COLUMNS ============
        stripe_id = Column(Integer, nullable=False)  # Reference to original stripe transaction
        stripe_client_number = Column(String(50), nullable=True)  # Client Number
        stripe_type = Column(String(100), nullable=True)  # Type
        stripe_stripe_id = Column(String(255), nullable=True)  # Stripe ID
        stripe_created = Column(String(100), nullable=True)  # Created date
        stripe_description = Column(Text, nullable=True)  # Description
        stripe_amount = Column(Float, nullable=True)  # Amount
        stripe_currency = Column(String(10), nullable=True)  # Currency
        stripe_converted_amount = Column(Float, nullable=True)  # Converted Amount
        stripe_fees = Column(Float, nullable=True)  # Fees
        stripe_net = Column(Float, nullable=True)  # Net
        stripe_converted_currency = Column(String(10), nullable=True)  # Converted Currency
        stripe_details = Column(Text, nullable=True)  # Details
        stripe_customer_id = Column(String(255), nullable=True)  # Customer ID
        stripe_customer_email = Column(String(255), nullable=True)  # Customer Email
        stripe_customer_name = Column(String(255), nullable=True)  # Customer Name
        stripe_purpose_metadata = Column(String(255), nullable=True)  # Purpose Metadata
        stripe_phorest_client_id_metadata = Column(String(255), nullable=True)  # Phorest Client ID Metadata
        
        # Matching metadata
        match_type = Column(String(50), nullable=False)  # 'perfect', 'date_amount', etc.
        process_number = Column(Integer, nullable=False)  # 1, 2, or 3
        created_at = Column(DateTime, default=datetime.utcnow)
        
        def to_dict(self):
            """Convert model to dictionary for JSON serialization"""
            return {
                'id': self.id,
                'job_id': self.job_id,
                'subsidiary_id': self.subsidiary_id,
                # Cashbook columns
                'cashbook_id': self.cashbook_id,
                'cb_payment_date': self.cb_payment_date,
                'cb_client_id': self.cb_client_id,
                'cb_invoice_number': self.cb_invoice_number,
                'cb_billing_entity': self.cb_billing_entity,
                'cb_ar_account': self.cb_ar_account,
                'cb_currency': self.cb_currency,
                'cb_exchange_rate': self.cb_exchange_rate,
                'cb_amount': self.cb_amount,
                'cb_account': self.cb_account,
                'cb_location': self.cb_location,
                'cb_transtype': self.cb_transtype,
                'cb_comment': self.cb_comment,
                'cb_card_reference': self.cb_card_reference,
                'cb_reasoncode': self.cb_reasoncode,
                'cb_sepaprovider': self.cb_sepaprovider,
                'cb_invoice_hash': self.cb_invoice_hash,
                'cb_payment_hash': self.cb_payment_hash,
                'cb_memo': self.cb_memo,
                # Stripe columns
                'stripe_id': self.stripe_id,
                'stripe_client_number': self.stripe_client_number,
                'stripe_type': self.stripe_type,
                'stripe_stripe_id': self.stripe_stripe_id,
                'stripe_created': self.stripe_created,
                'stripe_description': self.stripe_description,
                'stripe_amount': self.stripe_amount,
                'stripe_currency': self.stripe_currency,
                'stripe_converted_amount': self.stripe_converted_amount,
                'stripe_fees': self.stripe_fees,
                'stripe_net': self.stripe_net,
                'stripe_converted_currency': self.stripe_converted_currency,
                'stripe_details': self.stripe_details,
                'stripe_customer_id': self.stripe_customer_id,
                'stripe_customer_email': self.stripe_customer_email,
                'stripe_customer_name': self.stripe_customer_name,
                'stripe_purpose_metadata': self.stripe_purpose_metadata,
                'stripe_phorest_client_id_metadata': self.stripe_phorest_client_id_metadata,
                # Metadata
                'match_type': self.match_type,
                'process_number': self.process_number,
                'created_at': self.created_at.isoformat() if self.created_at else None
            }
    
    class ReconciliationResults(db.Model):
        """Model for storing reconciliation process results and metadata"""
        __tablename__ = 'reconciliation_results'
        
        id = Column(Integer, primary_key=True)
        job_id = Column(Integer, nullable=False)
        subsidiary_id = Column(Integer, nullable=False)
        process_number = Column(Integer, nullable=False)  # 1 or 2
        cutoff_date = Column(String(20), nullable=True)  # dd/mm/yyyy format
        
        # Process 1 specific fields
        unmatched_stripe_count = Column(Integer, default=0)
        unmatched_cashbook_count = Column(Integer, default=0)
        out_of_cutoff_count = Column(Integer, default=0)
        
        # Process 2 specific fields
        multiple_matches_count = Column(Integer, default=0)
        unmatched_stripe_p2_count = Column(Integer, default=0)
        unmatched_cashbook_p2_count = Column(Integer, default=0)
        
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        
        def to_dict(self):
            """Convert model to dictionary for JSON serialization"""
            return {
                'id': self.id,
                'job_id': self.job_id,
                'subsidiary_id': self.subsidiary_id,
                'process_number': self.process_number,
                'cutoff_date': self.cutoff_date,
                'unmatched_stripe_count': self.unmatched_stripe_count,
                'unmatched_cashbook_count': self.unmatched_cashbook_count,
                'out_of_cutoff_count': self.out_of_cutoff_count,
                'multiple_matches_count': self.multiple_matches_count,
                'unmatched_stripe_p2_count': self.unmatched_stripe_p2_count,
                'unmatched_cashbook_p2_count': self.unmatched_cashbook_p2_count,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None
            }
    
    class JournalTransaction(db.Model):
        """
        Journal-specific table that COPIES data from MatchedTransaction
        ONE-WAY SYNC: Original data changes → Journal data updates
        Journal data changes → Original data NEVER affected
        """
        __tablename__ = 'journal_transactions'
        
        id = Column(Integer, primary_key=True)
        job_id = Column(Integer, nullable=False)
        subsidiary_id = Column(Integer, nullable=False)
        
        # Reference to original matched transaction (READ-ONLY)
        matched_transaction_id = Column(Integer, nullable=False)
        
        # Journal-specific fields (can be modified for journal purposes)
        journal_type = Column(String(50), nullable=True)  # Main, POA, Refunds, Salon Summit Installments
        journal_memo = Column(String(500), nullable=True)  # User-entered memo
        journal_invoice_number = Column(String(255), nullable=True)  # CPMT: {invoice_number}
        journal_payment_number = Column(String(255), nullable=True)  # CPMT: {invoice_number}-{date}
        
        # Copied data from MatchedTransaction (READ-ONLY, synced from original)
        cb_payment_date = Column(String(20), nullable=True)
        cb_client_id = Column(Integer, nullable=True)
        cb_invoice_number = Column(String(255), nullable=True)
        cb_billing_entity = Column(String(500), nullable=True)
        cb_ar_account = Column(String(500), nullable=True)
        cb_currency = Column(String(10), nullable=True)
        cb_exchange_rate = Column(Float, nullable=True)
        cb_amount = Column(Float, nullable=True)
        cb_account = Column(String(500), nullable=True)
        cb_location = Column(String(100), nullable=True)
        cb_transtype = Column(String(100), nullable=True)
        cb_comment = Column(Text, nullable=True)
        cb_card_reference = Column(Float, nullable=True)
        cb_reasoncode = Column(Float, nullable=True)
        cb_sepaprovider = Column(String(255), nullable=True)
        cb_invoice_hash = Column(String(255), nullable=True)
        cb_payment_hash = Column(String(255), nullable=True)
        cb_memo = Column(Float, nullable=True)
        
        stripe_client_number = Column(String(50), nullable=True)
        stripe_type = Column(String(100), nullable=True)
        stripe_stripe_id = Column(String(255), nullable=True)
        stripe_created = Column(String(100), nullable=True)
        stripe_description = Column(Text, nullable=True)
        stripe_amount = Column(Float, nullable=True)
        stripe_currency = Column(String(10), nullable=True)
        stripe_converted_amount = Column(Float, nullable=True)
        stripe_fees = Column(Float, nullable=True)
        stripe_net = Column(Float, nullable=True)
        stripe_converted_currency = Column(String(10), nullable=True)
        stripe_details = Column(Text, nullable=True)
        stripe_customer_id = Column(String(255), nullable=True)
        stripe_customer_email = Column(String(255), nullable=True)
        stripe_customer_name = Column(String(255), nullable=True)
        stripe_purpose_metadata = Column(String(255), nullable=True)
        stripe_phorest_client_id_metadata = Column(String(255), nullable=True)
        
        # Journal-specific metadata
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        last_synced_at = Column(DateTime, nullable=True)  # When last synced from original
        
        def to_dict(self):
            """Convert model to dictionary for JSON serialization"""
            return {
                'id': self.id,
                'job_id': self.job_id,
                'subsidiary_id': self.subsidiary_id,
                'matched_transaction_id': self.matched_transaction_id,
                'journal_type': self.journal_type,
                'journal_memo': self.journal_memo,
                'journal_invoice_number': self.journal_invoice_number,
                'journal_payment_number': self.journal_payment_number,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
                'last_synced_at': self.last_synced_at.isoformat() if self.last_synced_at else None
            }
    
    class FPDataset(db.Model):
        """Further Processing dataset state per job/subsidiary"""
        __tablename__ = 'fp_datasets'
        id = Column(Integer, primary_key=True)
        job_id = Column(Integer, nullable=False)
        subsidiary_id = Column(Integer, nullable=False)
        status = Column(String(20), default='empty')  # empty, loaded, committed
        summit_data = Column(Text, nullable=True)  # JSON string of summit installments
        original_amounts = Column(Text, nullable=True)  # JSON string of original client amounts before summit processing
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class FPJournalRow(db.Model):
        """Rows uploaded for further processing (from Main/POA/Cross journals)"""
        __tablename__ = 'fp_journal_rows'
        id = Column(Integer, primary_key=True)
        dataset_id = Column(Integer, nullable=False)
        job_id = Column(Integer, nullable=False)
        subsidiary_id = Column(Integer, nullable=False)
        journal_type = Column(String(50), nullable=False)  # Main, POA, Cross_Subsidiary
        client_id = Column(String(100), nullable=True)
        invoice_number = Column(String(255), nullable=True)
        amount = Column(Float, nullable=True)
        row_json = Column(Text, nullable=True)  # raw row as JSON string
        filename = Column(String(255), nullable=True)
        uploaded_at = Column(DateTime, default=datetime.utcnow)

    class FPWorkingRow(db.Model):
        """Combined working table for Further Processing (materialized from uploads)"""
        __tablename__ = 'fp_working_rows'
        id = Column(Integer, primary_key=True)
        dataset_id = Column(Integer, nullable=False)
        job_id = Column(Integer, nullable=False)
        subsidiary_id = Column(Integer, nullable=False)
        source_journal_type = Column(String(50), nullable=False)
        client_id = Column(String(100), nullable=True)
        invoice_number = Column(String(255), nullable=True)
        amount = Column(Float, nullable=True)
        row_json = Column(Text, nullable=True)
        created_at = Column(DateTime, default=datetime.utcnow)

    class FPSummitInstallment(db.Model):
        """Summit installment data - persistent storage"""
        __tablename__ = 'fp_summit_installments'
        id = Column(Integer, primary_key=True)
        dataset_id = Column(Integer, nullable=False)
        job_id = Column(Integer, nullable=False)
        subsidiary_id = Column(Integer, nullable=False)
        client_id = Column(String(100), nullable=False)
        region = Column(String(50), nullable=True)
        installment_amount = Column(Float, nullable=False)
        created_at = Column(DateTime, default=datetime.utcnow)

    class FPProcessedJournal(db.Model):
        """Processed journals after summit split - persistent storage"""
        __tablename__ = 'fp_processed_journals'
        id = Column(Integer, primary_key=True)
        dataset_id = Column(Integer, nullable=False)
        job_id = Column(Integer, nullable=False)
        subsidiary_id = Column(Integer, nullable=False)
        journal_type = Column(String(50), nullable=False)  # Main, POA, Cross_Subsidiary, Salon_Summit_Installments
        client_id = Column(String(100), nullable=True)
        invoice_number = Column(String(255), nullable=True)
        amount = Column(Float, nullable=True)
        row_json = Column(Text, nullable=True)
        created_at = Column(DateTime, default=datetime.utcnow)

    class FPMatchResult(db.Model):
        """Summit matching results - stores all match outcomes"""
        __tablename__ = 'fp_match_results'
        id = Column(Integer, primary_key=True)
        dataset_id = Column(Integer, nullable=False)
        job_id = Column(Integer, nullable=False)
        subsidiary_id = Column(Integer, nullable=False)
        client_id = Column(String(100), nullable=False)
        match_status = Column(String(50), nullable=False)  # 'matched', 'insufficient', 'unmatched'
        total_received = Column(Float, nullable=True)  # Amount from combined journals
        installment_amount = Column(Float, nullable=False)  # From summit file
        remaining_amount = Column(Float, nullable=True)  # total_received - installment_amount
        created_at = Column(DateTime, default=datetime.utcnow)

    return (Receipt, ProcessingJob, Subsidiary, StripeTransaction, CashbookTransaction,
            LookerCashbookTransaction, MatchedTransaction, ReconciliationResults, JournalTransaction,
            FPDataset, FPJournalRow, FPWorkingRow, FPSummitInstallment, FPProcessedJournal, FPMatchResult)