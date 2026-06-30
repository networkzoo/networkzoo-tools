# Expense Submission Setup Guide

The expense submission tool is now integrated with your existing Syncro-to-QBO backend. This guide walks you through configuration.

## Overview

- **Frontend:** `expense-submission.html` in Utilities-Web
- **Backend:** Existing `/api/expense-upload/submit` endpoint in Syncro-to-QBO (`api.py` line 1592)
- **Location:** Accessible at `/expense-submission.html` on your tools site
- **QBO Integration:** Creates QBO Purchase transactions with optional PDF attachments

## Quick Setup

### 1. Add Expense Vendors to Config

Edit your Syncro-to-QBO `config.json` and add your expense vendors in the `expense_vendors` section:

```json
{
  "expense_vendors": {
    "personal_meals": {
      "label": "Meals & Entertainment",
      "vendor_name": "Gord Hynes - Reimbursable",
      "vendor_id": "YOUR_VENDOR_ID",
      "account_id": "YOUR_EXPENSE_ACCOUNT_ID",
      "account_name": "Meals and Entertainment",
      "default_due_days": 0,
      "tax_code": "3"
    },
    "personal_travel": {
      "label": "Travel Expenses",
      "vendor_name": "Gord Hynes - Reimbursable",
      "vendor_id": "YOUR_VENDOR_ID",
      "account_id": "YOUR_TRAVEL_ACCOUNT_ID",
      "account_name": "Travel",
      "default_due_days": 0,
      "tax_code": "3"
    },
    "personal_software": {
      "label": "Software & Tools",
      "vendor_name": "Gord Hynes - Reimbursable",
      "vendor_id": "YOUR_VENDOR_ID",
      "account_id": "YOUR_SOFTWARE_ACCOUNT_ID",
      "account_name": "Software Subscriptions",
      "default_due_days": 0,
      "tax_code": "3"
    },
    "personal_office": {
      "label": "Office Supplies",
      "vendor_name": "Gord Hynes - Reimbursable",
      "vendor_id": "YOUR_VENDOR_ID",
      "account_id": "YOUR_OFFICE_ACCOUNT_ID",
      "account_name": "Office Supplies & Equipment",
      "default_due_days": 0,
      "tax_code": "3"
    },
    "personal_other": {
      "label": "Other Expenses",
      "vendor_name": "Gord Hynes - Reimbursable",
      "vendor_id": "YOUR_VENDOR_ID",
      "account_id": "YOUR_GENERAL_ACCOUNT_ID",
      "account_name": "Miscellaneous",
      "default_due_days": 0,
      "tax_code": "3"
    }
  }
}
```

### 2. Find Your QBO IDs

You need:
- **vendor_id:** Your personal QBO vendor ID (or create "Gord Hynes - Reimbursable" vendor if it doesn't exist)
- **account_id:** Expense account IDs in QBO

Run these Python scripts from Syncro-to-QBO directory to get them:

```bash
python list_qbo_vendors.py    # Lists all vendors with their IDs
python list_qbo_accounts.py   # Lists all accounts with their IDs
```

Look for:
- Expense accounts (Meals and Entertainment, Travel, Software Subscriptions, etc.)
- Create a vendor entry for yourself if not already present

### 3. Verify Setup

After updating config.json:

1. Restart your FastAPI server:
   ```bash
   pm2 restart expense-api
   # or
   uvicorn api:app --host 0.0.0.0 --port 8082
   ```

2. Test the vendor endpoint:
   ```
   GET http://win-k2p3qor5ri6.netbird.cloud:8082/api/expense-upload/vendors
   ```

   Should return your configured vendors.

3. Open the expense form:
   ```
   http://your-tools-domain/expense-submission.html
   ```

   If vendors load and form works, you're good!

## How It Works

### User Workflow
1. **Submit Form:** User fills out expense details (date, amount, vendor, description)
2. **Upload Receipt:** User optionally uploads receipt image/PDF
3. **Submit:** Form POSTs to `/api/expense-upload/submit`
4. **QBO Creation:** Backend creates a QBO Purchase (expense) transaction
5. **Attachment:** If receipt was uploaded, it's attached to the QBO Purchase
6. **Confirmation:** User sees link to view expense in QuickBooks

### Form Fields
- **Date:** When the expense occurred
- **Amount:** In CAD (or your configured currency)
- **Vendor:** Dropdown of configured expense vendors
- **Description:** Business purpose of the expense
- **Receipt:** Optional image/PDF attachment

### QBO Transaction Details
- **Type:** Purchase (QBO's expense/payment term)
- **Vendor:** Your personal vendor account
- **Account:** Category-specific expense account
- **Date:** Expense date
- **Amount:** Net amount (before tax unless tax_inclusive=true)
- **Tax:** Applied based on tax_code in vendor config
- **Attachment:** Receipt PDF if provided
- **DocNumber:** Auto-generated format: `EXP-YYYYMMDD-XXXXXXXX`

## Configuration Reference

### Vendor Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `label` | Yes | Display name in expense form dropdown |
| `vendor_name` | Yes | QBO vendor name (should match your personal vendor) |
| `vendor_id` | Yes | QBO vendor ID from `list_qbo_vendors.py` |
| `account_id` | Yes | QBO expense account ID from `list_qbo_accounts.py` |
| `account_name` | No | Display name of account (informational) |
| `default_due_days` | No | Days until reimbursement due (default: 0) |
| `tax_code` | No | QBO tax code (3 = GST, 7 = GST+PST, etc.) |
| `currency` | No | Currency code (default: CAD) |
| `tax_inclusive` | No | If true, amount already includes all tax (default: false) |

### Tax Handling

**tax_inclusive = false** (default)
- Amount is NET (before tax)
- QBO adds tax based on tax_code
- Best for: Expenses where you have the actual amount before tax

**tax_inclusive = true**
- Amount is already TOTAL (tax included)
- QBO doesn't add additional tax
- Best for: International purchases or already-taxed amounts

## Troubleshooting

### "No expense vendors configured yet"
- Check that `expense_vendors` section exists in config.json
- Verify it's not empty
- Restart FastAPI server

### Vendors load but form won't submit
- Check browser console (F12 → Console tab) for errors
- Verify API_BASE URL is correct in expense-submission.html (line 70)
- Check CORS is enabled in FastAPI (should be by default)

### "QBO Purchase creation failed"
- Verify vendor_id exists in your QBO account
- Verify account_id exists and is an Expense account
- Check QBO access token hasn't expired (run `qbo_auth.py` to refresh)
- Check tax_code is valid for your QBO

### Receipt not attaching
- Receipt attachment is non-fatal — expense is created even if attachment fails
- Check QBO file upload permissions
- Try with smaller file (<5 MB)
- For PDFs, verify it's a valid PDF file

### Wrong tax calculated
- Verify tax_code in vendor config
- Check tax_inclusive setting
- For Canada: code 3 = GST only, 7 = GST+PST

## API Reference

### GET `/api/expense-upload/vendors`
Returns configured expense vendors.

**Response:**
```json
{
  "vendors": [
    {
      "key": "personal_meals",
      "label": "Meals & Entertainment",
      "vendor_id": "123",
      "vendor_name": "Gord Hynes - Reimbursable",
      "account_id": "45",
      "account_name": "Meals and Entertainment",
      "default_due_days": 0,
      "tax_code": "3",
      "currency": "CAD"
    }
  ]
}
```

### POST `/api/expense-upload/submit`
Creates a QBO Purchase expense.

**Request:**
```json
{
  "vendor_key": "personal_meals",
  "txn_date": "2026-06-30",
  "amount": 125.50,
  "description": "Client lunch meeting",
  "tax_inclusive": false,
  "doc_number": "EXP-20260630-12550000",
  "pdf_b64": "base64-encoded-pdf-bytes",
  "pdf_name": "receipt.pdf"
}
```

**Response (Success):**
```json
{
  "purchase_id": "456",
  "doc_number": "EXP-20260630-12550000",
  "txn_date": "2026-06-30",
  "amount": 125.50,
  "vendor": "Gord Hynes - Reimbursable",
  "attachment_id": "789",
  "qbo_url": "https://app.qbo.intuit.com/app/purchase?txnId=456"
}
```

## Security Notes

- The expense form is only accessible on your private Netbird network
- Receipts are uploaded directly to QBO (not stored locally)
- No data is stored in a database — everything goes to QBO
- QBO access token should be rotated every 60 days

## Expenses vs Bills

This tool creates **Expenses (Purchases)** not **Bills**:

| Aspect | Expense (This Tool) | Bill (bill-upload.html) |
|--------|-------------|------|
| **Purpose** | Personal reimbursement | Vendor invoices you receive |
| **Payer** | You (employee) | Company (vendor relationship) |
| **QBO Type** | Purchase | Bill |
| **Workflow** | Submit → QBO → Review → Reimburse | Upload → QBO → Pay Vendor |
| **Who uses it** | You | Accounting team |

## Future Enhancements

- [ ] Email notifications on expense submission
- [ ] Approval workflow for expenses over threshold
- [ ] Bulk export of reimbursement batches
- [ ] Recurring expense templates
- [ ] Mobile app integration
- [ ] Receipt OCR for automatic parsing
