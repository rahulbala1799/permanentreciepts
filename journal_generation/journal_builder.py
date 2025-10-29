"""
Main Journal Builder Class
Handles journal generation for all subsidiaries

HARD RULE: This class is COMPLETELY READ-ONLY
- NEVER modifies any database data
- NEVER alters any existing transactions
- ONLY reads data and generates journal files
- Journal creation is completely separate from reconciliation
"""

import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import io


class JournalBuilder:
    """
    Main class for building journals from reconciliation data
    """
    
    def __init__(self, db, job_id: int, subsidiary_id: int, models=None):
        """
        Initialize the journal builder
        
        Args:
            db: SQLAlchemy database instance
            job_id: ID of the reconciliation job
            subsidiary_id: ID of the subsidiary (1=AUS, 2=CAN, 3=USA, 4=EU, 5=UK)
            models: Dictionary containing model classes (optional)
        """
        self.db = db
        self.job_id = job_id
        self.subsidiary_id = subsidiary_id
        self.models = models or {}
        
        # Subsidiary mapping
        self.subsidiary_names = {
            1: "Australia",
            2: "Canada",
            3: "USA",
            4: "EU",
            5: "UK"
        }
        
        self.subsidiary_name = self.subsidiary_names.get(subsidiary_id, "Unknown")
        
        # Hardcoded bank accounts for each subsidiary
        self.bank_accounts = {
            1: "10130 Bank : CB current a/c AU$ # 411110236694",  # Australia
            2: "10150 Bank : CIBC Current Account 9066314",  # Canada
            3: "10043 Bank : CIBC operating a/c US$ # 2605090",  # USA
            4: "10010 Bank : BOI current a/c EUR # 17013705",  # EU (Ireland)
            5: "10020 Bank : BOI current a/c GBP # 62100285"  # UK
        }
        
        # Billing entities for each subsidiary
        self.billing_entities = {
            1: "Ndevor Systems Ltd : Phorest Australia",
            2: "Ndevor Systems Ltd : Phorest Canada",
            3: "Ndevor Systems Ltd : Phorest US",
            4: "Ndevor Systems Ltd : Phorest Ireland",
            5: "Ndevor Systems Ltd : Phorest Ireland : Phorest UK"
        }
        
    def get_matched_transactions(self) -> pd.DataFrame:
        """
        Get all matched transactions as a DataFrame
        Reads directly from MatchedTransaction (same source as reconciliation)
        
        Returns:
            DataFrame with all matched transaction data
        """
        # Use MatchedTransaction directly (same as reconciliation & master upload)
        if 'MatchedTransaction' in self.models:
            MatchedTransaction = self.models['MatchedTransaction']
        else:
            # Fallback: try to get from db metadata
            MatchedTransaction = self.db.Model.registry._class_registry.data.get('MatchedTransaction')
        if not MatchedTransaction:
            raise ValueError("MatchedTransaction model not available")
        
        # Get matched transactions directly from source
        matches = MatchedTransaction.query.filter_by(
            job_id=self.job_id,
            subsidiary_id=self.subsidiary_id
        ).all()
        
        if not matches:
            return pd.DataFrame()
        
        # Convert to list of dicts with all cashbook columns
        data = []
        for match in matches:
            row = {
                'payment_date': match.cb_payment_date,
                'client_id': match.cb_client_id,
                'invoice_number': match.cb_invoice_number,
                'billing_entity': match.cb_billing_entity,
                'ar_account': match.cb_ar_account,
                'currency': match.cb_currency,
                'exchange_rate': match.cb_exchange_rate,
                'amount': match.stripe_amount,  # Use Stripe amount (same as reconciliation)
                'account': match.cb_account,
                'location': match.cb_location,
                'transtype': match.cb_transtype,
                'comment': match.cb_comment,
                'card_reference': match.cb_card_reference,
                'reasoncode': match.cb_reasoncode,
                'sepaprovider': match.cb_sepaprovider,
                'invoice_hash': match.cb_invoice_hash,
                'payment_hash': match.cb_payment_hash,
                'memo': match.cb_memo,
                # Include Stripe data for reference
                'stripe_amount': match.stripe_amount,
                'stripe_currency': match.stripe_currency,
                'stripe_converted_amount': match.stripe_converted_amount,
                'stripe_type': match.stripe_type,
                'stripe_created': match.stripe_created,
                'match_type': match.match_type if hasattr(match, 'match_type') else None
            }
            data.append(row)
        
        df = pd.DataFrame(data)
        
        # No longer adjust for installments - use raw amounts from MatchedTransaction
        # (Installment processing now handled separately in journals_bp.py)
        
        return df
    
    def get_all_stripe_transactions(self) -> pd.DataFrame:
        """Get ALL Stripe transactions (matched + unmatched)"""
        StripeTransaction = self.models.get('StripeTransaction')
        if not StripeTransaction:
            raise ValueError("StripeTransaction model not available")
        
        transactions = StripeTransaction.query.filter_by(
            job_id=self.job_id,
            subsidiary_id=self.subsidiary_id
        ).all()
        
        if not transactions:
            return pd.DataFrame()
        
        data = []
        for tx in transactions:
            row = {
                'id': tx.id,
                'client_number': tx.client_number,
                'type': tx.type,
                'stripe_id': tx.stripe_id,
                'created': tx.created,
                'description': tx.description,
                'amount': tx.amount,
                'currency': tx.currency,
                'converted_amount': tx.converted_amount,
                'fees': tx.fees,
                'net': tx.net,
                'converted_currency': tx.converted_currency,
                'details': tx.details,
                'customer_id': tx.customer_id,
                'customer_email': tx.customer_email,
                'customer_name': tx.customer_name,
                'purpose_metadata': tx.purpose_metadata,
                'phorest_client_id_metadata': tx.phorest_client_id_metadata,
                'description_client_id': tx.description_client_id
            }
            data.append(row)
        
        return pd.DataFrame(data)
    
    def get_all_cashbook_transactions(self) -> pd.DataFrame:
        """Get ALL Cashbook transactions (matched + unmatched)"""
        CashbookTransaction = self.models.get('CashbookTransaction')
        if not CashbookTransaction:
            raise ValueError("CashbookTransaction model not available")
        
        transactions = CashbookTransaction.query.filter_by(
            job_id=self.job_id,
            subsidiary_id=self.subsidiary_id
        ).all()
        
        if not transactions:
            return pd.DataFrame()
        
        data = []
        for tx in transactions:
            row = {
                'id': tx.id,
                'payment_date': tx.payment_date,
                'client_id': tx.client_id,
                'invoice_number': tx.invoice_number,
                'billing_entity': tx.billing_entity,
                'ar_account': tx.ar_account,
                'currency': tx.currency,
                'exchange_rate': tx.exchange_rate,
                'amount': tx.amount,
                'account': tx.account,
                'location': tx.location,
                'transtype': tx.transtype,
                'comment': tx.comment,
                'card_reference': tx.card_reference,
                'reasoncode': tx.reasoncode,
                'sepaprovider': tx.sepaprovider,
                'invoice_hash': tx.invoice_hash,
                'payment_hash': tx.payment_hash,
                'memo': tx.memo
            }
            data.append(row)
        
        return pd.DataFrame(data)
    
    def get_unmatched_stripe(self) -> pd.DataFrame:
        """Get unmatched Stripe transactions"""
        StripeTransaction = self.models.get('StripeTransaction')
        MatchedTransaction = self.models.get('MatchedTransaction')
        if not StripeTransaction or not MatchedTransaction:
            raise ValueError("Required models not available")
        
        # Get all matched Stripe IDs
        matched_ids = set()
        matches = MatchedTransaction.query.filter_by(
            job_id=self.job_id,
            subsidiary_id=self.subsidiary_id
        ).all()
        for match in matches:
            matched_ids.add(match.stripe_id)
        
        # Get unmatched Stripe transactions
        transactions = StripeTransaction.query.filter_by(
            job_id=self.job_id,
            subsidiary_id=self.subsidiary_id
        ).filter(~StripeTransaction.id.in_(matched_ids)).all()
        
        if not transactions:
            return pd.DataFrame()
        
        data = []
        for tx in transactions:
            row = {
                'id': tx.id,
                'client_number': tx.client_number,
                'type': tx.type,
                'created': tx.created,
                'description': tx.description,
                'amount': tx.amount,
                'currency': tx.currency,
                'net': tx.net
            }
            data.append(row)
        
        return pd.DataFrame(data)
    
    def get_unmatched_cashbook(self) -> pd.DataFrame:
        """Get unmatched Cashbook transactions"""
        CashbookTransaction = self.models.get('CashbookTransaction')
        MatchedTransaction = self.models.get('MatchedTransaction')
        if not CashbookTransaction or not MatchedTransaction:
            raise ValueError("Required models not available")
        
        # Get all matched Cashbook IDs
        matched_ids = set()
        matches = MatchedTransaction.query.filter_by(
            job_id=self.job_id,
            subsidiary_id=self.subsidiary_id
        ).all()
        for match in matches:
            matched_ids.add(match.cashbook_id)
        
        # Get unmatched Cashbook transactions
        transactions = CashbookTransaction.query.filter_by(
            job_id=self.job_id,
            subsidiary_id=self.subsidiary_id
        ).filter(~CashbookTransaction.id.in_(matched_ids)).all()
        
        if not transactions:
            return pd.DataFrame()
        
        data = []
        for tx in transactions:
            row = {
                'id': tx.id,
                'payment_date': tx.payment_date,
                'client_id': tx.client_id,
                'amount': tx.amount,
                'billing_entity': tx.billing_entity,
                'transtype': tx.transtype
            }
            data.append(row)
        
        return pd.DataFrame(data)
    
    def generate_master_journal(self, memo: Optional[str] = None) -> pd.DataFrame:
        """
        Generate the master journal file (all matched transactions)
        Format: Simple transaction list with all original columns from cashbook
        
        Args:
            memo: Optional memo text to populate in the Memo column
            
        Returns:
            DataFrame with master journal data in cashbook format
        """
        df = self.get_matched_transactions()
        
        if df.empty:
            return df
        
        # Apply memo if provided
        if memo:
            df['memo'] = memo
        else:
            df['memo'] = ''
        
        # Ensure the correct bank account is used (hardcoded per subsidiary)
        bank_account = self.bank_accounts.get(self.subsidiary_id, '')
        if bank_account:
            df['account'] = bank_account
        
        # Add the required formulas for invoice # and payment #
        journal_df = df.copy()
        
        # Invoice # formula: CPMT: {invoice_number}
        journal_df['invoice #'] = 'CPMT: ' + journal_df['invoice_number'].astype(str)
        
        # Payment # formula: CPMT: {invoice_number}-{date}
        # Convert date to string format (dd/mm/yyyy)
        journal_df['payment #'] = 'CPMT: ' + journal_df['invoice_number'].astype(str) + '-' + journal_df['payment_date'].astype(str)
        
        # Rename other columns to match cashbook upload format
        journal_df = journal_df.rename(columns={
            'location': 'Location',
            'card_reference': 'Card Reference',
            'memo': 'Memo'
        })
        
        # Sort by payment_date
        journal_df = journal_df.sort_values('payment_date')
        
        return journal_df
    
    def split_journals(self, master_df: pd.DataFrame, memo: Optional[str] = None) -> Dict[str, pd.DataFrame]:
        """
        Split the master journal into specific journal types:
        1. Refunds Journal (Refunds - double-entry Dr/Cr format)
        2. Salon Summit Installments Journal (Installment transactions - simple format)
        3. POA Journal (POA transactions - simple format)
        4. Main Journal (Regular transactions - simple format)
        
        Args:
            master_df: Master journal DataFrame
            memo: User-entered memo for journal entries
            
        Returns:
            Dictionary with journal type as key and DataFrame as value
        """
        if master_df.empty:
            return {}
        
        journals = {}
        
        # Get current subsidiary's billing entity
        current_billing_entity = self.billing_entities.get(self.subsidiary_id, '')
        
        # 1. REFUNDS JOURNAL (Negative amounts) - Double-Entry Format
        refunds_df = master_df[master_df['amount'] < 0].copy()
        if not refunds_df.empty:
            refunds_journal = self._generate_refunds_journal(refunds_df, memo)
            journals[f'Refunds_{self.subsidiary_name}'] = refunds_journal
        
        # Get remaining transactions (positive amounts)
        remaining_df = master_df[master_df['amount'] >= 0].copy()
        
        if not remaining_df.empty:
            # 2. SALON SUMMIT INSTALLMENTS JOURNAL - TEMPORARILY DISABLED
            # installment_mask = remaining_df.get('match_type', '').str.contains('Salon Summit Installment', case=False, na=False)
            # installment_df = remaining_df[installment_mask].copy()
            # if not installment_df.empty:
            #     journals[f'Salon_Summit_Installments_{self.subsidiary_name}'] = installment_df
            
            # 3. POA JOURNAL (invoice contains "POA") - Simple Format
            if not remaining_df.empty:
                poa_mask = remaining_df['invoice_number'].astype(str).str.contains('POA', case=False, na=False)
                poa_df = remaining_df[poa_mask].copy()
                if not poa_df.empty:
                    journals[f'POA_{self.subsidiary_name}'] = poa_df
                
                # 4. CROSS-SUBSIDIARY JOURNAL (different billing entity) - Simple Format
                non_poa_df = remaining_df[~poa_mask].copy()
                if not non_poa_df.empty:
                    # Define current subsidiary billing entity
                    current_subsidiary_entity = self.billing_entities.get(self.subsidiary_id, "")
                    cross_subsidiary_mask = non_poa_df['billing_entity'] != current_subsidiary_entity
                    cross_subsidiary_df = non_poa_df[cross_subsidiary_mask].copy()
                    if not cross_subsidiary_df.empty:
                        journals[f'Cross_Subsidiary_{self.subsidiary_name}'] = cross_subsidiary_df
                    
                    # 5. MAIN JOURNAL (Regular transactions - same billing entity) - Simple Format
                    main_df = non_poa_df[~cross_subsidiary_mask].copy()
                    if not main_df.empty:
                        journals[f'Main_{self.subsidiary_name}'] = main_df
        
        return journals
    
    def _generate_refunds_journal(self, refunds_df: pd.DataFrame, memo: Optional[str] = None) -> pd.DataFrame:
        """
        Generate double-entry refunds journal in accounting format
        Each refund creates 2 lines: Debit (AR) and Credit (Bank)
        
        Args:
            refunds_df: DataFrame with refund transactions (negative amounts)
            memo: User-entered memo for the journal
            
        Returns:
            DataFrame in double-entry format with Dr/Cr columns
        """
        from datetime import datetime
        import calendar
        
        if refunds_df.empty:
            return pd.DataFrame()
        
        journal_entries = []
        
        # Get the month and year from the first transaction to calculate EOM
        if not refunds_df.empty and 'payment_date' in refunds_df.columns:
            first_date_str = str(refunds_df.iloc[0]['payment_date'])
            try:
                # Try parsing dd/mm/yyyy format
                if '/' in first_date_str:
                    parts = first_date_str.split('/')
                    if len(parts) == 3:
                        day, month, year = parts
                        month = int(month)
                        year = int(year)
                else:
                    # Try parsing yyyy-mm-dd format
                    first_date = datetime.strptime(first_date_str[:10], '%Y-%m-%d')
                    month = first_date.month
                    year = first_date.year
                
                # Calculate end of month
                last_day = calendar.monthrange(year, month)[1]
                eom_date = f"{last_day:02d}/{month:02d}/{year}"
            except:
                # Fallback to generic EOM
                eom_date = "30/09/2025"
        else:
            eom_date = "30/09/2025"
        
        # Calculate total refund amount (sum of all negative amounts)
        total_refund_amount = abs(refunds_df['amount'].sum())
        
        # Get billing entity and bank account from first refund
        first_refund = refunds_df.iloc[0]
        billing_entity = first_refund['billing_entity']
        bank_account = first_refund['account']
        
        # Process each refund transaction (individual Dr entries)
        for idx, row in refunds_df.iterrows():
            amount_abs = abs(row['amount'])
            
            # Individual Dr entry for each refund
            entry = {
                'Date': row['payment_date'],
                'memo': memo if memo else 'MISC PAYMENT STRIPE',
                'Entity': billing_entity,
                'Name': row['client_id'],
                'Account': '11010 Accounts Receivable : Trade Debtors',
                'Management P&L': 'Balance Sheet',
                'Dept.': 'Balance Sheet',
                'Cost centre': 'Balance Sheet',
                'Region': self.subsidiary_name,
                'Dr': amount_abs,
                'Cr': ''
            }
            journal_entries.append(entry)
        
        # Final Cr entry - Bank Account (total sum)
        entry_cr = {
            'Date': eom_date,
            'memo': 'Refunds / Disputes',
            'Entity': billing_entity,
            'Name': '',
            'Account': bank_account,
            'Management P&L': 'Balance Sheet',
            'Dept.': 'Balance Sheet',
            'Cost centre': 'Balance Sheet',
            'Region': self.subsidiary_name,
            'Dr': '',
            'Cr': total_refund_amount
        }
        journal_entries.append(entry_cr)
        
        # Create DataFrame with proper column order
        refunds_journal_df = pd.DataFrame(journal_entries, columns=[
            'Date', 'memo', 'Entity', 'Name', 'Account', 
            'Management P&L', 'Dept.', 'Cost centre', 'Region', 'Dr', 'Cr'
        ])
        
        return refunds_journal_df
    
    def format_for_export(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Format DataFrame for export (match Cashbook upload format)
        
        Args:
            df: DataFrame to format
            
        Returns:
            Formatted DataFrame ready for export
        """
        if df.empty:
            return df
        
        # The columns were already renamed in generate_master_journal
        # Just select the columns in the correct order, handling both naming conventions
        export_columns_mapping = {
            'payment_date': 'payment_date',
            'client_id': 'client_id',
            'invoice_number': 'invoice_number',
            'billing_entity': 'billing_entity',
            'ar_account': 'ar_account',
            'currency': 'currency',
            'exchange_rate': 'exchange_rate',
            'amount': 'amount',
            'account': 'account',
            'Location': 'Location',  # Already capitalized
            'transtype': 'transtype',
            'comment': 'comment',
            'Card Reference': 'Card Reference',  # Already capitalized
            'reasoncode': 'reasoncode',
            'sepaprovider': 'sepaprovider',
            'invoice_hash': 'invoice #',  # Map invoice_hash to invoice #
            'payment_hash': 'payment #',  # Map payment_hash to payment #
            'Memo': 'Memo'  # Already capitalized
        }
        
        # Get available columns from the dataframe
        available_columns = []
        for col in export_columns_mapping.values():
            if col in df.columns:
                available_columns.append(col)
        
        # Create export dataframe with only these columns
        export_df = df[available_columns].copy()
        
        return export_df
    
    def generate_all(self, memo: Optional[str] = None) -> Dict:
        """
        Generate all journals for this subsidiary
        
        Args:
            memo: Optional memo text
            
        Returns:
            Dictionary with status and journal information
        """
        try:
            # Generate master journal
            master_df = self.generate_master_journal(memo)
            
            if master_df.empty:
                return {
                    'success': False,
                    'error': 'No matched transactions found'
                }
            
            # Split into specific journals
            journals = self.split_journals(master_df, memo)
            
            # Salon Summit Installments disabled
            
            # Calculate summary
            summary = {
                'master_count': len(master_df),
                'master_total': float(master_df['amount'].sum()),
                'journals': {}
            }
            
            for journal_name, journal_df in journals.items():
                # For refunds journal, sum Dr column; for others, sum amount column
                if 'Refunds_' in journal_name and 'Dr' in journal_df.columns:
                    # Refunds journal uses Dr/Cr format - sum the Dr column for total
                    total = float(journal_df['Dr'].replace('', 0).infer_objects(copy=False).sum())
                else:
                    # Regular journals use amount column
                    total = float(journal_df['amount'].sum()) if 'amount' in journal_df.columns else 0
                
                summary['journals'][journal_name] = {
                    'count': len(journal_df),
                    'total': total
                }
            
            return {
                'success': True,
                'subsidiary': self.subsidiary_name,
                'summary': summary,
                'journal_names': list(journals.keys())
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def export_journal_to_csv(self, journal_df: pd.DataFrame, journal_name: str) -> io.BytesIO:
        """
        Export a journal DataFrame to CSV format (exact match to provided examples)
        Handles both simple format (Main/POA) and double-entry format (Refunds)
        
        Args:
            journal_df: DataFrame to export
            journal_name: Name of the journal
            
        Returns:
            BytesIO object containing the CSV file
        """
        # Check if this is a refunds journal (has Dr/Cr columns)
        if 'Dr' in journal_df.columns and 'Cr' in journal_df.columns:
            # Refunds journal - already in correct format, export as-is
            export_df = journal_df
        else:
            # Regular journal - format for export
            export_df = self.format_for_export(journal_df)
        
        # Create CSV file in memory (no formatting, just raw CSV)
        output = io.BytesIO()
        export_df.to_csv(output, index=False, encoding='utf-8')
        output.seek(0)
        return output
    
    # SALON SUMMIT FUNCTIONALITY TEMPORARILY REMOVED
    def process_salon_summit_installments(self, summit_data: list, memo: str = None) -> dict:
        """Salon Summit functionality disabled"""
        return {'success': False, 'error': 'Salon Summit functionality temporarily disabled'}
    
    def _clean_amount(self, amount_str):
        """Clean amount string (remove commas, spaces, handle parentheses)"""
        if pd.isna(amount_str):
            return 0.0
        cleaned = str(amount_str).replace(',', '').strip()
        if cleaned.startswith('(') and cleaned.endswith(')'):
            cleaned = '-' + cleaned[1:-1]
        return float(cleaned) if cleaned else 0.0
    
    def _get_existing_journal_transactions(self):
        """Get existing journal transactions for matching (EXCLUDE REFUNDS)"""
        JournalTransaction = self.models.get('JournalTransaction')
        if not JournalTransaction:
            return []
        
        # Get all journal transactions EXCEPT refunds (negative amounts)
        # Refunds should not be split for Salon Summit installments
        return JournalTransaction.query.filter_by(
            job_id=self.job_id,
            subsidiary_id=self.subsidiary_id
        ).filter(JournalTransaction.cb_amount > 0).all()  # Only positive amounts (exclude refunds)
    
    def _find_matching_journal(self, journals, client_id, amount, tolerance=50.0):
        """Find matching journal transaction by client_id only (EXCLUDE REFUNDS)"""
        # Find by client_id only - don't worry about amount matching
        # BUT EXCLUDE REFUNDS (negative amounts) - they should never be split
        client_journals = [j for j in journals if j.cb_client_id == client_id and j.cb_amount and j.cb_amount > 0]
        
        if client_journals:
            # Return the first match (or could return the one with highest amount)
            # Since we're splitting, we want the original transaction
            return client_journals[0]
        
        return None
    
    def _generate_summary_file(self, client_installments, processed_count, memo):
        """Generate a summary CSV file showing matched and unmatched clients"""
        import os
        from datetime import datetime
        
        # Create summary data
        summary_data = []
        matched_count = 0
        unmatched_count = 0
        
        for client_id, installments in client_installments.items():
            total_installment = sum(installments)
            
            # Check if this client was processed (has a journal entry)
            JournalTransaction = self.models.get('JournalTransaction')
            if JournalTransaction:
                existing_entry = JournalTransaction.query.filter_by(
                    job_id=self.job_id,
                    subsidiary_id=self.subsidiary_id,
                    cb_client_id=client_id,
                    journal_type='Salon Summit Installments'
                ).first()
                
                if existing_entry:
                    status = "MATCHED"
                    matched_count += 1
                else:
                    status = "NOT FOUND"
                    unmatched_count += 1
            else:
                status = "ERROR"
                unmatched_count += 1
            
            summary_data.append({
                'Client_ID': client_id,
                'Individual_Installments': '; '.join([f'${amt:.2f}' for amt in installments]),
                'Total_Installment': f'${total_installment:.2f}',
                'Status': status,
                'Installment_Count': len(installments)
            })
        
        # Create DataFrame and save to CSV
        import pandas as pd
        summary_df = pd.DataFrame(summary_data)
        
        # Sort by status (MATCHED first, then NOT FOUND)
        summary_df = summary_df.sort_values(['Status', 'Client_ID'])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'Summit_Summary_Sub{self.subsidiary_id}_{timestamp}.csv'
        filepath = os.path.join(os.getcwd(), filename)
        
        # Save CSV
        summary_df.to_csv(filepath, index=False)
        
        return filepath
    
    def _create_installment_journal(self, original_journal, installment_amount, memo):
        """Create Salon Summit Installment journal entry"""
        JournalTransaction = self.models.get('JournalTransaction')
        if not JournalTransaction:
            return None
        
        # Create new journal transaction for installment
        installment_journal = JournalTransaction(
            job_id=original_journal.job_id,
            subsidiary_id=original_journal.subsidiary_id,
            matched_transaction_id=original_journal.matched_transaction_id,
            journal_type='Salon Summit Installments',
            journal_memo=memo or 'Salon Summit Installment',
            journal_invoice_number=f"CPMT: {original_journal.cb_invoice_number}-INSTALLMENT" if original_journal.cb_invoice_number else None,
            journal_payment_number=f"CPMT: {original_journal.cb_invoice_number}-{original_journal.cb_payment_date}-summit" if original_journal.cb_invoice_number else None,
            last_synced_at=datetime.utcnow(),
            # Copy all data from original journal
            cb_payment_date=original_journal.cb_payment_date,
            cb_client_id=original_journal.cb_client_id,
            cb_invoice_number=original_journal.cb_invoice_number,
            cb_billing_entity=original_journal.cb_billing_entity,
            cb_ar_account=original_journal.cb_ar_account,
            cb_currency=original_journal.cb_currency,
            cb_exchange_rate=original_journal.cb_exchange_rate,
            cb_amount=installment_amount,  # Use installment amount
            cb_account=original_journal.cb_account,
            cb_location=original_journal.cb_location,
            cb_transtype=original_journal.cb_transtype,
            cb_comment=original_journal.cb_comment,
            cb_card_reference=original_journal.cb_card_reference,
            cb_reasoncode=original_journal.cb_reasoncode,
            cb_sepaprovider=original_journal.cb_sepaprovider,
            cb_invoice_hash=f"{original_journal.cb_invoice_hash}-summit" if original_journal.cb_invoice_hash else None,
            cb_payment_hash=f"{original_journal.cb_payment_hash}-summit" if original_journal.cb_payment_hash else None,
            cb_memo=original_journal.cb_memo,
            stripe_client_number=original_journal.stripe_client_number,
            stripe_type=original_journal.stripe_type,
            stripe_stripe_id=original_journal.stripe_stripe_id,
            stripe_created=original_journal.stripe_created,
            stripe_description=original_journal.stripe_description,
            stripe_amount=installment_amount,  # Use installment amount
            stripe_currency=original_journal.stripe_currency,
            stripe_converted_amount=original_journal.stripe_converted_amount,
            stripe_fees=original_journal.stripe_fees,
            stripe_net=original_journal.stripe_net,
            stripe_converted_currency=original_journal.stripe_converted_currency,
            stripe_details=original_journal.stripe_details,
            stripe_customer_id=original_journal.stripe_customer_id,
            stripe_customer_email=original_journal.stripe_customer_email,
            stripe_customer_name=original_journal.stripe_customer_name,
            stripe_purpose_metadata=original_journal.stripe_purpose_metadata,
            stripe_phorest_client_id_metadata=original_journal.stripe_phorest_client_id_metadata
        )
        
        self.db.session.add(installment_journal)
        return installment_journal
    
    def _update_main_journal_for_split(self, original_journal, remaining_amount):
        """Update main journal to show remaining amount after split (ONLY for positive amounts - NOT refunds)"""
        # Only update if this is NOT a refund (positive amount)
        if original_journal.cb_amount and original_journal.cb_amount > 0:
            # Update the original journal to show remaining amount
            original_journal.cb_amount = remaining_amount
            original_journal.stripe_amount = remaining_amount
            original_journal.journal_memo = f"Remaining after Salon Summit split: {remaining_amount}"
        else:
            # Don't modify refunds - they should remain unchanged
            pass
        
        return original_journal
    
    def _get_salon_summit_installments(self) -> pd.DataFrame:
        """Salon Summit functionality disabled"""
        return pd.DataFrame()
    
    def _adjust_amounts_for_installments(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Adjust amounts for clients that have Salon Summit Installments
        Main Journal should show remaining amounts (original - installment)
        """
        JournalTransaction = self.models.get('JournalTransaction')
        if not JournalTransaction:
            return df
        
        # Get all Salon Summit Installment transactions
        installments = JournalTransaction.query.filter_by(
            job_id=self.job_id,
            subsidiary_id=self.subsidiary_id,
            journal_type='Salon Summit Installments'
        ).all()
        
        if not installments:
            return df
        
        # Create a mapping of client_id to installment amount
        installment_map = {}
        for inst in installments:
            client_id = inst.cb_client_id
            installment_amount = inst.cb_amount
            if client_id in installment_map:
                installment_map[client_id] += installment_amount or 0
            else:
                installment_map[client_id] = installment_amount or 0
        
        # Adjust amounts in the dataframe
        for client_id, installment_amount in installment_map.items():
            mask = df['client_id'] == client_id
            df.loc[mask, 'amount'] = df.loc[mask, 'amount'] - installment_amount
        
        return df
    
    def export_all_journals(self, memo: Optional[str] = None) -> Dict[str, io.BytesIO]:
        """
        Export all journals as CSV files (exact match to provided examples)
        
        Args:
            memo: Optional memo text
            
        Returns:
            Dictionary with journal name as key and BytesIO CSV file as value
        """
        master_df = self.generate_master_journal(memo)
        
        if master_df.empty:
            return {}
        
        journals = self.split_journals(master_df, memo)
        
        # Also add master journal
        journals['Master_Journal'] = master_df
        
        # Export each journal as CSV
        exported_journals = {}
        for journal_name, journal_df in journals.items():
            csv_file = self.export_journal_to_csv(journal_df, journal_name)
            exported_journals[journal_name] = csv_file
        
        return exported_journals

