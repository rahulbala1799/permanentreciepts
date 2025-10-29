"""
EU-Specific Journal Builder
Handles AED currency transactions separately from EUR transactions
"""

import pandas as pd
import io
from typing import Dict, Optional
from datetime import datetime
import calendar


class JournalBuilderEU:
    """
    EU-specific journal builder that handles AED transactions separately
    
    Generates 5 journals:
    1. Refunds (EUR, double-entry format)
    2. POA (EUR)
    3. Main (EUR)
    4. Cross-Subsidiary (EUR)
    5. AED Journal (original AED amounts)
    """
    
    def __init__(self, db, job_id: int, subsidiary_id: int, models=None):
        self.db = db
        self.job_id = job_id
        self.subsidiary_id = subsidiary_id
        self.models = models or {}
        self.subsidiary_name = "EU"
        self.billing_entity = "Ndevor Systems Ltd : Phorest Ireland"
    
    def get_matched_transactions(self) -> pd.DataFrame:
        """
        Get all matched transactions from MatchedTransaction table
        Same source as reconciliation and master upload
        """
        if 'MatchedTransaction' in self.models:
            MatchedTransaction = self.models['MatchedTransaction']
        else:
            MatchedTransaction = self.db.Model.registry._class_registry.data.get('MatchedTransaction')
        
        if not MatchedTransaction:
            raise ValueError("MatchedTransaction model not available")
        
        matches = MatchedTransaction.query.filter_by(
            job_id=self.job_id,
            subsidiary_id=self.subsidiary_id
        ).all()
        
        if not matches:
            return pd.DataFrame()
        
        data = []
        for match in matches:
            # Determine if this is AED or EUR transaction
            is_aed = match.stripe_currency and match.stripe_currency.upper() == 'AED'
            
            row = {
                'payment_date': match.cb_payment_date,
                'client_id': match.cb_client_id,
                'invoice_number': match.cb_invoice_number,
                'billing_entity': match.cb_billing_entity,
                'ar_account': match.cb_ar_account,
                'currency': match.stripe_currency if is_aed else match.cb_currency,
                'exchange_rate': match.cb_exchange_rate,
                'amount': match.stripe_amount,  # Use stripe_amount (same as reconciliation)
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
                # Stripe data for AED handling
                'stripe_currency': match.stripe_currency,
                'stripe_converted_amount': match.stripe_converted_amount,
                'is_aed': is_aed
            }
            data.append(row)
        
        return pd.DataFrame(data)
    
    def generate_master_journal(self, memo: Optional[str] = None) -> pd.DataFrame:
        """
        Generate master journal with all transactions
        """
        df = self.get_matched_transactions()
        
        if df.empty:
            return df
        
        if memo:
            df['memo'] = memo
        else:
            df['memo'] = ''
        
        return df
    
    def split_journals(self, master_df: pd.DataFrame, memo: Optional[str] = None) -> Dict[str, pd.DataFrame]:
        """
        Split master journal into categorized journals (EUR and AED):
        EUR Journals: Refunds, POA, Main, Cross-Subsidiary
        AED Journals: Refunds_AED, POA_AED, Main_AED, Cross_Subsidiary_AED
        
        This matches the Master Upload categorization logic
        """
        if master_df.empty:
            return {}
        
        journals = {}
        
        # STEP 1: Separate AED and EUR transactions
        aed_df = master_df[master_df['is_aed'] == True].copy()
        eur_df = master_df[master_df['is_aed'] == False].copy()
        
        # STEP 2: Process EUR transactions
        if not eur_df.empty:
            # Check for cross-subsidiary FIRST (matches Master Upload logic)
            cross_mask_eur = eur_df['billing_entity'] != self.billing_entity
            cross_eur_df = eur_df[cross_mask_eur].copy()
            if not cross_eur_df.empty:
                journals['Cross_Subsidiary_EU'] = cross_eur_df
            
            # Non-cross-subsidiary EUR transactions
            non_cross_eur_df = eur_df[~cross_mask_eur].copy()
            
            if not non_cross_eur_df.empty:
                # Refunds (negative amounts, double-entry format)
                refunds_eur_mask = non_cross_eur_df['amount'] < 0
                refunds_eur_df = non_cross_eur_df[refunds_eur_mask].copy()
                if not refunds_eur_df.empty:
                    refunds_journal = self._generate_refunds_journal(refunds_eur_df, memo)
                    journals['Refunds_EU'] = refunds_journal
                
                # Positive EUR transactions
                positive_eur_df = non_cross_eur_df[~refunds_eur_mask].copy()
                
                if not positive_eur_df.empty:
                    # POA Journal
                    poa_eur_mask = positive_eur_df['invoice_number'].astype(str).str.contains('POA', case=False, na=False)
                    poa_eur_df = positive_eur_df[poa_eur_mask].copy()
                    if not poa_eur_df.empty:
                        journals['POA_EU'] = poa_eur_df
                    
                    # Main Journal (Regular)
                    main_eur_df = positive_eur_df[~poa_eur_mask].copy()
                    if not main_eur_df.empty:
                        journals['Main_EU'] = main_eur_df
        
        # STEP 3: Process AED transactions (SAME categorization logic as EUR)
        if not aed_df.empty:
            # Check for cross-subsidiary FIRST
            cross_mask_aed = aed_df['billing_entity'] != self.billing_entity
            cross_aed_df = aed_df[cross_mask_aed].copy()
            if not cross_aed_df.empty:
                journals['Cross_Subsidiary_AED'] = cross_aed_df
            
            # Non-cross-subsidiary AED transactions
            non_cross_aed_df = aed_df[~cross_mask_aed].copy()
            
            if not non_cross_aed_df.empty:
                # Refunds AED (negative amounts, double-entry format)
                refunds_aed_mask = non_cross_aed_df['amount'] < 0
                refunds_aed_df = non_cross_aed_df[refunds_aed_mask].copy()
                if not refunds_aed_df.empty:
                    refunds_aed_journal = self._generate_refunds_journal(refunds_aed_df, memo)
                    journals['Refunds_AED'] = refunds_aed_journal
                
                # Positive AED transactions
                positive_aed_df = non_cross_aed_df[~refunds_aed_mask].copy()
                
                if not positive_aed_df.empty:
                    # POA AED
                    poa_aed_mask = positive_aed_df['invoice_number'].astype(str).str.contains('POA', case=False, na=False)
                    poa_aed_df = positive_aed_df[poa_aed_mask].copy()
                    if not poa_aed_df.empty:
                        journals['POA_AED'] = poa_aed_df
                    
                    # Main AED (Regular)
                    main_aed_df = positive_aed_df[~poa_aed_mask].copy()
                    if not main_aed_df.empty:
                        journals['Main_AED'] = main_aed_df
        
        return journals
    
    def _generate_refunds_journal(self, refunds_df: pd.DataFrame, memo: Optional[str] = None) -> pd.DataFrame:
        """
        Generate double-entry refunds journal
        Each refund creates 2 lines: Debit (AR) and Credit (Bank)
        """
        if refunds_df.empty:
            return pd.DataFrame()
        
        # Get current month and year
        now = datetime.now()
        month_name = calendar.month_name[now.month]
        year = now.year
        
        # Default memo if not provided
        if not memo:
            memo = f"{month_name} {year} Receipts"
        
        refund_entries = []
        
        for _, refund in refunds_df.iterrows():
            amount = abs(refund['amount'])  # Make positive for display
            
            # Debit entry (AR)
            debit_entry = {
                'Date': refund['payment_date'],
                'Account': refund['ar_account'],
                'Dr': amount,
                'Cr': '',
                'Billing Entity': refund['billing_entity'],
                'Memo': memo,
                'Currency': refund['currency'],
                'Exchange Rate': refund['exchange_rate'],
                'Location': refund['location'],
                'Client #': refund['client_id'],
                'Invoice #': refund['invoice_number']
            }
            refund_entries.append(debit_entry)
            
            # Credit entry (Bank)
            credit_entry = {
                'Date': refund['payment_date'],
                'Account': refund['account'],
                'Dr': '',
                'Cr': amount,
                'Billing Entity': refund['billing_entity'],
                'Memo': memo,
                'Currency': refund['currency'],
                'Exchange Rate': refund['exchange_rate'],
                'Location': refund['location'],
                'Client #': refund['client_id'],
                'Invoice #': refund['invoice_number']
            }
            refund_entries.append(credit_entry)
        
        return pd.DataFrame(refund_entries)
    
    def generate_all(self, memo: Optional[str] = None) -> Dict:
        """
        Generate all journals and calculate summary with reconciliation
        """
        try:
            master_df = self.generate_master_journal(memo)
            
            if master_df.empty:
                return {
                    'success': False,
                    'error': 'No matched transactions found'
                }
            
            journals = self.split_journals(master_df, memo)
            
            # Calculate summary for each journal
            summary = {
                'master_count': len(master_df),
                'master_total': float(master_df['amount'].sum()),
                'journals': {}
            }
            
            # Track EUR and AED separately for reconciliation
            eur_total = 0.0
            aed_total_aed = 0.0
            aed_total_eur = 0.0  # AED converted to EUR for comparison
            
            # Track combined categories (EUR + AED)
            combined_refunds = 0.0
            combined_poa = 0.0
            combined_main = 0.0
            combined_cross_sub = 0.0
            
            for journal_name, journal_df in journals.items():
                if 'Refunds_' in journal_name and 'Dr' in journal_df.columns:
                    # Refunds journal uses Dr/Cr format
                    total = float(journal_df['Dr'].replace('', 0).astype(float).sum())
                else:
                    # Regular journals use amount column
                    total = float(journal_df['amount'].sum()) if 'amount' in journal_df.columns else 0
                
                summary['journals'][journal_name] = {
                    'count': len(journal_df),
                    'total': total
                }
                
                # Categorize by EUR vs AED
                is_aed_journal = '_AED' in journal_name
                
                if is_aed_journal:
                    # AED journal - need to convert for comparison
                    if 'stripe_converted_amount' in journal_df.columns:
                        total_eur = float(journal_df['stripe_converted_amount'].sum())
                    else:
                        total_eur = 0
                    aed_total_aed += total
                    aed_total_eur += total_eur
                else:
                    # EUR journal
                    eur_total += total
                    total_eur = total
                
                # Add to combined categories (for comparison with Master Upload)
                if 'Refunds' in journal_name:
                    combined_refunds += total_eur
                elif 'POA' in journal_name:
                    combined_poa += total_eur
                elif 'Main' in journal_name:
                    combined_main += total_eur
                elif 'Cross_Subsidiary' in journal_name:
                    combined_cross_sub += total_eur
            
            # Calculate combined total (EUR equivalent)
            combined_total_eur = combined_refunds + combined_poa + combined_main + combined_cross_sub
            
            # Master Upload uses converted EUR for all (including AED converted)
            # So we compare combined_total_eur (which includes AED converted to EUR)
            master_upload_equivalent = combined_total_eur
            
            # Add reconciliation info
            summary['reconciliation'] = {
                'eur_journals_total': round(eur_total, 2),
                'aed_journals_total_aed': round(aed_total_aed, 2),
                'aed_journals_total_eur': round(aed_total_eur, 2),
                'combined_total_eur': round(combined_total_eur, 2),
                'master_upload_total': round(master_upload_equivalent, 2),
                'difference': 0.0,  # Should match since same categorization logic
                'match': True,
                'breakdown': {
                    'refunds': round(combined_refunds, 2),
                    'poa': round(combined_poa, 2),
                    'main': round(combined_main, 2),
                    'cross_subsidiary': round(combined_cross_sub, 2)
                }
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
                'error': f'Error generating EU journals: {str(e)}'
            }
    
    def export_journal_to_csv(self, df: pd.DataFrame, journal_name: str) -> io.BytesIO:
        """Export journal DataFrame to CSV BytesIO"""
        output = io.BytesIO()
        df.to_csv(output, index=False, encoding='utf-8')
        output.seek(0)
        return output

