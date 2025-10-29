"""
Journal Sync Module
Handles one-way synchronization from original tables to journal tables

HARD RULE: ONE-WAY SYNC ONLY
- Original data changes → Journal data updates
- Journal data changes → Original data NEVER affected
"""

from datetime import datetime
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class JournalSync:
    """
    Handles one-way synchronization from MatchedTransaction to JournalTransaction
    """
    
    def __init__(self, db, models):
        self.db = db
        self.models = models
        self.MatchedTransaction = models.get('MatchedTransaction')
        self.JournalTransaction = models.get('JournalTransaction')
    
    def sync_journal_data(self, job_id: int, subsidiary_id: int, memo: str = None) -> dict:
        """
        Sync data from MatchedTransaction to JournalTransaction
        This is the ONLY way journal data gets updated
        
        Args:
            job_id: ID of the reconciliation job
            subsidiary_id: ID of the subsidiary
            memo: User-entered memo for journals
            
        Returns:
            dict: Sync results
        """
        if not self.MatchedTransaction or not self.JournalTransaction:
            raise ValueError("Required models not available")
        
        try:
            # Get all matched transactions for this job/subsidiary
            matched_transactions = self.MatchedTransaction.query.filter_by(
                job_id=job_id,
                subsidiary_id=subsidiary_id
            ).all()
            
            # Get existing journal transactions
            existing_journal_transactions = self.JournalTransaction.query.filter_by(
                job_id=job_id,
                subsidiary_id=subsidiary_id
            ).all()
            
            existing_ids = {jt.matched_transaction_id for jt in existing_journal_transactions}
            
            created_count = 0
            updated_count = 0
            
            for match in matched_transactions:
                # Skip Salon Summit Installments (they're handled separately)
                if match.match_type == 'Salon Summit Installment':
                    continue
                
                # Check if journal transaction already exists
                existing_jt = next(
                    (jt for jt in existing_journal_transactions 
                     if jt.matched_transaction_id == match.id), 
                    None
                )
                
                if existing_jt:
                    # Update existing journal transaction with latest data
                    self._update_journal_transaction(existing_jt, match, memo)
                    updated_count += 1
                else:
                    # Create new journal transaction
                    self._create_journal_transaction(match, memo)
                    created_count += 1
            
            # Commit all changes
            self.db.session.commit()
            
            logger.info(f"Journal sync completed: {created_count} created, {updated_count} updated")
            
            return {
                'success': True,
                'created_count': created_count,
                'updated_count': updated_count,
                'total_matched': len(matched_transactions)
            }
            
        except Exception as e:
            self.db.session.rollback()
            logger.error(f"Journal sync failed: {str(e)}")
            raise e
    
    def _create_journal_transaction(self, match, memo: str = None):
        """Create a new journal transaction from a matched transaction"""
        journal_type = self._determine_journal_type(match)
        
        journal_tx = self.JournalTransaction(
            job_id=match.job_id,
            subsidiary_id=match.subsidiary_id,
            matched_transaction_id=match.id,
            journal_type=journal_type,
            journal_memo=memo,
            journal_invoice_number=f"CPMT: {match.cb_invoice_number}" if match.cb_invoice_number else None,
            journal_payment_number=self._generate_payment_number(match),
            last_synced_at=datetime.utcnow(),
            # Copy all data from matched transaction
            cb_payment_date=match.cb_payment_date,
            cb_client_id=match.cb_client_id,
            cb_invoice_number=match.cb_invoice_number,
            cb_billing_entity=match.cb_billing_entity,
            cb_ar_account=match.cb_ar_account,
            cb_currency=match.cb_currency,
            cb_exchange_rate=match.cb_exchange_rate,
            cb_amount=match.cb_amount,
            cb_account=match.cb_account,
            cb_location=match.cb_location,
            cb_transtype=match.cb_transtype,
            cb_comment=match.cb_comment,
            cb_card_reference=match.cb_card_reference,
            cb_reasoncode=match.cb_reasoncode,
            cb_sepaprovider=match.cb_sepaprovider,
            cb_invoice_hash=match.cb_invoice_hash,
            cb_payment_hash=match.cb_payment_hash,
            cb_memo=match.cb_memo,
            stripe_client_number=match.stripe_client_number,
            stripe_type=match.stripe_type,
            stripe_stripe_id=match.stripe_stripe_id,
            stripe_created=match.stripe_created,
            stripe_description=match.stripe_description,
            stripe_amount=match.stripe_amount,
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
            stripe_phorest_client_id_metadata=match.stripe_phorest_client_id_metadata
        )
        
        self.db.session.add(journal_tx)
    
    def _update_journal_transaction(self, journal_tx, match, memo: str = None):
        """Update existing journal transaction with latest data from matched transaction"""
        # Update journal-specific fields
        if memo:
            journal_tx.journal_memo = memo
        journal_tx.journal_invoice_number = f"CPMT: {match.cb_invoice_number}" if match.cb_invoice_number else None
        journal_tx.journal_payment_number = self._generate_payment_number(match)
        journal_tx.last_synced_at = datetime.utcnow()
        
        # Update all copied data from matched transaction
        journal_tx.cb_payment_date = match.cb_payment_date
        journal_tx.cb_client_id = match.cb_client_id
        journal_tx.cb_invoice_number = match.cb_invoice_number
        journal_tx.cb_billing_entity = match.cb_billing_entity
        journal_tx.cb_ar_account = match.cb_ar_account
        journal_tx.cb_currency = match.cb_currency
        journal_tx.cb_exchange_rate = match.cb_exchange_rate
        journal_tx.cb_amount = match.cb_amount
        journal_tx.cb_account = match.cb_account
        journal_tx.cb_location = match.cb_location
        journal_tx.cb_transtype = match.cb_transtype
        journal_tx.cb_comment = match.cb_comment
        journal_tx.cb_card_reference = match.cb_card_reference
        journal_tx.cb_reasoncode = match.cb_reasoncode
        journal_tx.cb_sepaprovider = match.cb_sepaprovider
        journal_tx.cb_invoice_hash = match.cb_invoice_hash
        journal_tx.cb_payment_hash = match.cb_payment_hash
        journal_tx.cb_memo = match.cb_memo
        journal_tx.stripe_client_number = match.stripe_client_number
        journal_tx.stripe_type = match.stripe_type
        journal_tx.stripe_stripe_id = match.stripe_stripe_id
        journal_tx.stripe_created = match.stripe_created
        journal_tx.stripe_description = match.stripe_description
        journal_tx.stripe_amount = match.stripe_amount
        journal_tx.stripe_currency = match.stripe_currency
        journal_tx.stripe_converted_amount = match.stripe_converted_amount
        journal_tx.stripe_fees = match.stripe_fees
        journal_tx.stripe_net = match.stripe_net
        journal_tx.stripe_converted_currency = match.stripe_converted_currency
        journal_tx.stripe_details = match.stripe_details
        journal_tx.stripe_customer_id = match.stripe_customer_id
        journal_tx.stripe_customer_email = match.stripe_customer_email
        journal_tx.stripe_customer_name = match.stripe_customer_name
        journal_tx.stripe_purpose_metadata = match.stripe_purpose_metadata
        journal_tx.stripe_phorest_client_id_metadata = match.stripe_phorest_client_id_metadata
    
    def _determine_journal_type(self, match) -> str:
        """Determine journal type based on transaction characteristics"""
        # Check for refunds (negative amounts)
        if match.stripe_amount and match.stripe_amount < 0:
            return "Refunds"
        
        # Check for POA transactions
        if match.cb_invoice_number and 'POA' in str(match.cb_invoice_number).upper():
            return "POA"
        
        # Check for Salon Summit Installments
        if match.match_type == 'Salon Summit Installment':
            return "Salon Summit Installments"
        
        # Default to Main
        return "Main"
    
    def _generate_payment_number(self, match) -> str:
        """Generate payment number: CPMT: {invoice_number}-{date}"""
        if not match.cb_invoice_number:
            return None
        
        # Use payment date if available, otherwise use created date
        date_str = match.cb_payment_date or match.stripe_created
        if date_str:
            # Extract just the date part if it's a datetime
            if ' ' in str(date_str):
                date_str = str(date_str).split(' ')[0]
            return f"CPMT: {match.cb_invoice_number}-{date_str}"
        
        return f"CPMT: {match.cb_invoice_number}"
    
    def get_journal_transactions(self, job_id: int, subsidiary_id: int, journal_type: str = None) -> List:
        """
        Get journal transactions (READ-ONLY)
        
        Args:
            job_id: ID of the reconciliation job
            subsidiary_id: ID of the subsidiary
            journal_type: Optional filter by journal type
            
        Returns:
            List of journal transactions
        """
        query = self.JournalTransaction.query.filter_by(
            job_id=job_id,
            subsidiary_id=subsidiary_id
        )
        
        if journal_type:
            query = query.filter_by(journal_type=journal_type)
        
        return query.all()
    
    def clear_journal_data(self, job_id: int, subsidiary_id: int) -> bool:
        """
        Clear all journal data for a job/subsidiary
        This is the ONLY way to reset journal data
        
        Args:
            job_id: ID of the reconciliation job
            subsidiary_id: ID of the subsidiary
            
        Returns:
            bool: Success status
        """
        try:
            self.JournalTransaction.query.filter_by(
                job_id=job_id,
                subsidiary_id=subsidiary_id
            ).delete()
            
            self.db.session.commit()
            return True
            
        except Exception as e:
            self.db.session.rollback()
            logger.error(f"Failed to clear journal data: {str(e)}")
            return False

