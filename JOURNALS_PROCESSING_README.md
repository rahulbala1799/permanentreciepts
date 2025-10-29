# Journals Processing - Summit Installments

## Overview
A **simplified, isolated** journals processing system for handling Salon Summit installments. Built as a separate Flask blueprint to keep code clean and maintainable.

## Architecture

### Files Created
1. **`journals_bp.py`** - Flask Blueprint with all business logic
2. **`templates/journals_processing.html`** - Standalone UI page
3. **Blueprint registration in `app.py`** (lines 31-39)
4. **Link added to `journal_preparation.html`** (after Reconciliation section)

### Database Tables Used
- **`fp_datasets`** - Dataset metadata (existing)
- **`fp_journal_rows`** - Original uploaded journals (existing, immutable)
- **`fp_summit_installments`** - Summit upload data (new, persistent)
- **`fp_processed_journals`** - Processed journals after split (new, persistent)

### Key Design Principles
1. **Original data never modified** - `fp_journal_rows` remains untouched
2. **Clear state management** - Summit data and processed journals are separate
3. **Easy reset** - Clear button deletes summit & processed data, restores original
4. **No interference with app.py** - Completely isolated blueprint

## Workflow

### Step 1: Upload Summit Data
- User uploads `summit upload.csv` (OAK ID, Region, Amount)
- Data stored in `fp_summit_installments` table
- Duplicate client IDs automatically combined
- State: **Summit Uploaded** ✅

### Step 2: Process Installments
1. **Copy** `fp_journal_rows` → `fp_processed_journals` (fresh, unmodified copy)
2. **Match** summit clients against processed journals by client_id
3. **Reduce** amounts proportionally in processed journals
4. **Create** new `Salon_Summit_Installments` rows in processed journals
5. **Verify** totals match (original = processed)
6. State: **Processing Complete** ✅

### Step 3: Download Journals
- Download any processed journal type as CSV
- Files include:
  - Main (with reduced amounts)
  - POA (with reduced amounts)
  - Cross_Subsidiary (with reduced amounts)
  - Salon_Summit_Installments (new journal)
- All files maintain original CSV format

### Clear & Restart
- **Clear All Data** button deletes:
  - `fp_summit_installments` (summit upload)
  - `fp_processed_journals` (processed results)
- **Original journals intact** in `fp_journal_rows`
- Can immediately re-upload and reprocess

## API Endpoints

### GET `/journals/`
Main journals processing page

### GET `/journals/api/status/<job_id>/<subsidiary_id>`
Get current status:
```json
{
  "success": true,
  "dataset_status": "committed",
  "original_journals": {"count": 2687, "total": 934026.16},
  "summit_uploaded": true,
  "summit_count": 155,
  "processing_complete": true,
  "processed_count": 2731
}
```

### POST `/journals/api/upload-summit/<job_id>/<subsidiary_id>`
Upload summit CSV data
```json
{
  "summit_data": [
    {"oak_id": "51728", "region": "USA", "installment_amount": 110.67},
    ...
  ]
}
```

### POST `/journals/api/process/<job_id>/<subsidiary_id>`
Process summit installments (split journals)

Response:
```json
{
  "success": true,
  "matched_count": 44,
  "total_summit_amount": 21709.26,
  "unmatched_count": 90,
  "unmatched_summit_total": 9249.66,
  "original_total": 934026.16,
  "processed_total": 934026.16,
  "verification_passed": true,
  "message": "✅ Matched 44 clients, 90 unmatched"
}
```

### DELETE `/journals/api/clear/<job_id>/<subsidiary_id>`
Clear summit data and processed journals

### GET `/journals/api/download/<job_id>/<subsidiary_id>/<journal_type>`
Download processed journal as CSV

### GET `/journals/api/list-journals/<job_id>/<subsidiary_id>`
List all available processed journals

## Matching Logic

### Client Matching
```python
for client_id, installment_amount in summit_by_client.items():
    if client_id in processed_lookup:
        client_rows = processed_lookup[client_id]
        total_client_amount = sum(row.amount for row in client_rows)
        
        if total_client_amount >= installment_amount:
            # MATCH! Reduce proportionally
            for row in client_rows:
                reduction = (row.amount / total_client_amount) * installment_amount
                row.amount -= reduction
```

### Unmatched Clients
Clients are marked as unmatched if:
1. **Not found in database** - Client ID doesn't exist in journals
2. **Insufficient amount** - Client's total < installment amount
3. **Zero amount** - Client has $0 in journals

## Verification

### Total Consistency Check
```
Original Total = Processed Total
Original Total = (Reduced Amounts in All Journals) + (Summit Journal Amounts)
```

If verification fails:
- ❌ Error message shown
- Data still committed (user can review)
- Clear & reprocess available

## Benefits of This Approach

1. **✅ Isolation** - No risk of breaking `app.py` functions
2. **✅ Simplicity** - Clear 3-step workflow
3. **✅ Safety** - Original data never modified
4. **✅ Transparency** - Easy to understand what's happening
5. **✅ Debuggability** - All data queryable in database
6. **✅ Repeatability** - Clear button restores to original state
7. **✅ Maintainability** - All logic in one blueprint file

## Troubleshooting

### No original journals found
- **Solution**: Go to "Further Processing" section, upload journals, commit, and load combined dataset

### Summit already uploaded
- **Solution**: Click "Clear All Data" to remove summit data and reprocess

### Processing already complete
- **Solution**: Click "Clear All Data" to reset and reprocess

### Totals don't match
- **Cause**: Usually due to insufficient amounts or mismatched client IDs
- **Solution**: Review unmatched clients list, verify summit CSV data

## Future Enhancements
- Add detailed matching view (show which clients matched/unmatched)
- Export unmatched clients as CSV
- Add region filtering
- Batch processing for multiple subsidiaries
- Audit log for all processing operations

