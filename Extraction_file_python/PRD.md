# 📋 PROJECT REQUIREMENTS DOCUMENT (PRD)
## Purchase Order (PO) Email Extractor System

---

| Field | Details |
|-------|---------|
| **Project Name** | Purchase Order Email Extractor System |
| **Version** | v3.0 |
| **Date** | 2026-02-24 |
| **Status** | Active Development |
| **Author** | Development Team |
| **Technology Stack** | Python, OpenAI GPT-4o, SQL Server, Gmail IMAP, HTML/CSS/JS (Frontend) |

---

## 1. 📌 PROJECT OVERVIEW

### 1.1 Executive Summary
The **Purchase Order (PO) Email Extractor** is an automated system that continuously monitors a Gmail inbox for incoming emails containing Purchase Order data (in email body text or PDF attachments), extracts structured PO information using **OpenAI GPT-4o AI**, and stores the data in a **Microsoft SQL Server** database. The system includes a **web-based frontend dashboard** for viewing, searching, filtering, and exporting PO data.

### 1.2 Business Problem
- Manual extraction of PO data from emails and PDFs is **time-consuming and error-prone**
- Companies receive POs in **multiple formats** — formal tables, conversational emails, bullet points, HTML emails
- Data needs to be stored in a **centralized database** for tracking, reporting, and analysis
- Need for **real-time monitoring** — system must run continuously without manual intervention

### 1.3 Solution
An AI-powered automated pipeline that:
1. Polls Gmail inbox every 60-120 seconds
2. Detects new emails (unseen/unprocessed)
3. Extracts PO data from email body text AND PDF attachments
4. Uses OpenAI GPT-4o for intelligent data extraction
5. Stores extracted data in SQL Server database
6. Provides a web dashboard for viewing and exporting data

---

## 2. 🏗️ SYSTEM ARCHITECTURE

### 2.1 High-Level Architecture Diagram

```
┌───────────────────────────────────────────────────────────────────┐
│                        GMAIL INBOX                                │
│  (deevan9391@gmail.com via IMAP SSL - Port 993)                  │
└──────────────────────┬────────────────────────────────────────────┘
                       │ IMAP Poll (every 60-120 sec)
                       ▼
┌───────────────────────────────────────────────────────────────────┐
│                    PYTHON BACKEND                                 │
│                                                                   │
│  ┌─────────────────┐   ┌─────────────────┐   ┌────────────────┐  │
│  │  Email Parser    │──▶│  PDF Extractor   │──▶│  AI Extractor  │  │
│  │  (IMAP/RFC822)   │   │  (pdfplumber)    │   │  (OpenAI 4o)   │  │
│  └─────────────────┘   │  (OCR/Tesseract) │   └───────┬────────┘  │
│                         └─────────────────┘           │            │
│                                                        ▼            │
│  ┌─────────────────┐   ┌─────────────────┐   ┌────────────────┐  │
│  │  JSON Backup     │   │  Logging System  │   │  DB Inserter   │  │
│  │  (Local Files)   │   │  (Rotating Logs) │   │  (pyodbc)      │  │
│  └─────────────────┘   └─────────────────┘   └───────┬────────┘  │
└───────────────────────────────────────────────────────┼───────────┘
                                                        │
                                                        ▼
┌───────────────────────────────────────────────────────────────────┐
│                  SQL SERVER DATABASE                               │
│  Server: 198.38.84.193:1234                                       │
│  DB: GG26_GagriLearning                                           │
│  Table: dbo.email_purchase_orders                                 │
└──────────────────────┬────────────────────────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────────────────────────┐
│                  FRONTEND DASHBOARD                               │
│  (HTML/CSS/JavaScript - Web Browser)                              │
│  View / Search / Filter / Export to Excel                         │
└───────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Breakdown

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Email Poller** | Python `imaplib` | Connects to Gmail IMAP, fetches UNSEEN emails |
| **Email Parser** | Python `email` / `BeautifulSoup` | Parses RFC822 emails (plain text + HTML) |
| **PDF Extractor** | `pdfplumber` + `pytesseract` | Extracts text from PDF attachments |
| **AI Extractor** | OpenAI GPT-4o API | Intelligent structured data extraction |
| **Database Layer** | `pyodbc` + SQL Server | Stores extracted PO data |
| **Duplicate Checker** | SQL queries | Prevents re-inserting same PO data |
| **JSON Backup** | Local filesystem | Saves extracted data as JSON files |
| **Logger** | Python `logging` + `colorlog` | Console + rotating file logs |
| **Frontend Dashboard** | HTML + CSS + JavaScript | Web UI for viewing/exporting data |

---

## 3. 📊 DATABASE SCHEMA

### 3.1 Table: `dbo.email_purchase_orders`

| Column Name | Data Type | Nullable | Description |
|-------------|-----------|----------|-------------|
| `id` | INT (Auto-increment) | NO | Primary Key |
| `po_number` | NVARCHAR(255) | YES | Purchase Order number (e.g., PO-2026-015) |
| `po_date` | DATE | YES | Date of the Purchase Order |
| `delivery_address` | NVARCHAR(MAX) | YES | Shipping / delivery address |
| `gst_number` | NVARCHAR(100) | YES | GSTIN / GST Registration Number |
| `cgst_number` | NVARCHAR(100) | YES | CGST Tax Amount |
| `sgst_number` | NVARCHAR(100) | YES | SGST Tax Amount |
| `igst_number` | NVARCHAR(100) | YES | IGST Tax Amount |
| `product_name` | NVARCHAR(500) | YES | Product / Chemical / Item name |
| `cas_number` | NVARCHAR(100) | YES | CAS Chemical Identifier |
| `cat_number` | NVARCHAR(100) | YES | Catalog / Item Code |
| `hsn_code` | NVARCHAR(50) | YES | HSN/SAC Code |
| `quantity` | DECIMAL(18,2) | YES | Ordered quantity (numeric) |
| `amount` | DECIMAL(18,2) | YES | Line item amount (numeric) |
| `email_from` | NVARCHAR(500) | YES | Sender email address |
| `email_date` | DATE | YES | Email sent date |

### 3.2 Database Connection Details

| Parameter | Value |
|-----------|-------|
| **Server** | `198.38.84.193,1234` |
| **Database** | `GG26_GagriLearning` |
| **Driver** | `ODBC Driver 17 for SQL Server` |
| **Encryption** | Yes (TrustServerCertificate=yes) |

---

## 4. 📧 EMAIL PROCESSING PIPELINE

### 4.1 Supported Email Formats

| Format | Support Status | Example |
|--------|---------------|---------|
| **Formal structured PO tables** | ✅ Supported | Tables with headers and rows |
| **Conversational paragraphs** | ✅ Supported | "Please find the PO details below..." |
| **Bullet point lists** | ✅ Supported | "• PO Number: PO-123" |
| **Mixed/partial data** | ✅ Supported | Email with some PO fields only |
| **HTML emails** | ✅ Supported | Rich-formatted emails |
| **Multiple POs in one email** | ✅ Supported | Several POs in one email |
| **PDF attachments** | ✅ Supported | PO data in attached PDFs |
| **Forwarded emails** | ✅ Supported | Nested forwarded content |
| **Scanned PDFs** | ✅ Supported (OCR) | Image-based PDFs via Tesseract |

### 4.2 Processing Flow

```
1. CONNECT   → Gmail IMAP SSL (port 993)
2. SEARCH    → Find UNSEEN emails in INBOX
3. FETCH     → Download email content (BODY.PEEK[])
4. PARSE     → Extract text (plain + HTML-to-text)
5. PDF CHECK → If PDF attached → Extract text (native + OCR fallback)
6. AI CALL   → Send to OpenAI GPT-4o with structured prompt
7. VALIDATE  → Normalize JSON, coerce types, fill missing fields
8. DUP CHECK → Check if PO already exists in DB
9. INSERT    → Insert new rows into SQL Server
10. MOVE     → Move email to 'processed' or 'failed' folder
11. LOG      → Write to console + rotating log file
12. REPEAT   → Wait 60 seconds → Go to step 1
```

### 4.3 Email Tracking & Deduplication

**Version 1 (`index.py`):**
- Uses a local file `processed_emails.txt`
- Stores unique email IDs (Message-ID header or MD5 hash)
- Prevents re-processing of already-handled emails

**Version 3 (`po_extractor.py`):**
- Uses IMAP flags (UNSEEN → SEEN)
- Moves processed emails to `processed` folder
- Moves failed emails to `failed` folder
- Database-level duplicate check (PO number + product + from + date)

---

## 5. 🤖 AI EXTRACTION DETAILS

### 5.1 OpenAI Configuration

| Parameter | Value |
|-----------|-------|
| **Model** | `gpt-4o` |
| **Temperature** | `0` (deterministic) |
| **Max Tokens** | `4000-4096` |
| **Retry Strategy** | 3 attempts with exponential backoff |

### 5.2 Extracted Fields Mapping

| Field | Aliases Found In Documents |
|-------|---------------------------|
| `po_number` | PO No, P.O. No, Purchase Order No, Order No, PO# |
| `po_date` | PO Date, Order Date, Purchase Date, Date |
| `gst_number` | GSTIN, GST No, GST Number, GST Registration No |
| `cgst_number` | CGST, Central GST (amount only, not %) |
| `sgst_number` | SGST, State GST (amount only, not %) |
| `igst_number` | IGST, Integrated GST (amount only, not %) |
| `product_name` | Item Description, Product Description, Material, Chemical Name |
| `cas_number` | CAS No, CAS Number (chemical identifier) |
| `cat_number` | Cat No, Catalog No, Product Code, Item Code, SKU |
| `hsn_code` | HSN, HSN Code, SAC Code |
| `quantity` | Qty, Quantity, Ordered Qty (numeric only) |
| `amount` | Line Total, Row Total, Unit Price (numeric only) |
| `delivery_address` | Delivery Address, Shipping Address, Ship To, Deliver To |
| `email_from` | Sender email address (from metadata) |
| `email_date` | Email sent date (from metadata, YYYY-MM-DD) |

### 5.3 GST Tax Extraction Rules

| Input Example | Extracted Value | Rule |
|--------------|----------------|------|
| `SGST 9% ₹450` | `450` | Extract amount ONLY |
| `CGST @ 18% 1200` | `1200` | Ignore percentage |
| `IGST 5%: Rs.300` | `300` | Numeric value only |
| `SGST 9%` (no amount) | `null` | Cannot extract if only % |

---

## 6. 🖥️ FRONTEND REQUIREMENTS

### 6.1 Dashboard Features

| Feature | Description | Priority |
|---------|-------------|----------|
| **Data Table** | Display all PO records from database | 🔴 HIGH |
| **Search** | Global text search across all fields | 🔴 HIGH |
| **Filter by Date** | Filter records by PO date range | 🔴 HIGH |
| **Filter by Sender** | Filter by email sender | 🟡 MEDIUM |
| **Sort Columns** | Click column headers to sort | 🟡 MEDIUM |
| **Export to Excel** | Download filtered data as .xlsx file | 🔴 HIGH |
| **Export to CSV** | Download filtered data as .csv file | 🟡 MEDIUM |
| **Pagination** | Navigate through large datasets | 🟡 MEDIUM |
| **Record Count** | Show total records and filtered count | 🟢 LOW |
| **Dark Mode** | Premium dark theme UI | 🟢 LOW |
| **Responsive Design** | Works on desktop, tablet, mobile | 🟡 MEDIUM |
| **Auto-Refresh** | Optionally refresh data periodically | 🟢 LOW |

### 6.2 Dashboard Columns

| # | Column | Width | Sortable | Searchable |
|---|--------|-------|----------|------------|
| 1 | PO Number | 120px | ✅ | ✅ |
| 2 | PO Date | 100px | ✅ | ✅ |
| 3 | Product Name | 200px | ✅ | ✅ |
| 4 | CAS Number | 120px | ✅ | ✅ |
| 5 | Cat Number | 120px | ✅ | ✅ |
| 6 | HSN Code | 100px | ✅ | ✅ |
| 7 | Quantity | 80px | ✅ | ❌ |
| 8 | Amount | 100px | ✅ | ❌ |
| 9 | GST Number | 150px | ✅ | ✅ |
| 10 | CGST | 80px | ✅ | ❌ |
| 11 | SGST | 80px | ✅ | ❌ |
| 12 | IGST | 80px | ✅ | ❌ |
| 13 | Delivery Address | 200px | ❌ | ✅ |
| 14 | Email From | 180px | ✅ | ✅ |
| 15 | Email Date | 100px | ✅ | ✅ |

---

## 7. 🔧 TECHNICAL REQUIREMENTS

### 7.1 Backend Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `openai` | Latest | OpenAI GPT-4o API client |
| `pyodbc` | Latest | SQL Server database connection |
| `pdfplumber` | Latest | Native PDF text extraction |
| `pytesseract` | Latest | OCR for scanned PDFs |
| `pdf2image` | Latest | Convert PDF pages to images (for OCR) |
| `Pillow` | Latest | Image processing |
| `beautifulsoup4` | Latest | HTML email parsing |
| `lxml` | Latest | HTML parser backend |
| `colorlog` | Latest | Colored console logging |
| `tenacity` | Latest | Retry logic with backoff |

### 7.2 Frontend Dependencies

| Library | Purpose |
|---------|---------|
| `SheetJS (xlsx)` | Client-side Excel export |
| `Google Fonts (Inter)` | Modern typography |
| Vanilla CSS | Custom dark-mode premium styling |

### 7.3 System Requirements

| Requirement | Specification |
|-------------|--------------|
| **Python** | 3.8+ |
| **OS** | Windows / Linux / macOS |
| **Browser** | Chrome, Edge, Firefox (latest) |
| **Network** | Internet access for Gmail IMAP + OpenAI API |
| **SQL Server** | MSSQL with ODBC Driver 17+ |
| **Tesseract** | Optional (for scanned PDF OCR) |

---

## 8. 🔐 SECURITY CONSIDERATIONS

| Area | Current Implementation | Recommendation |
|------|----------------------|----------------|
| **Gmail Credentials** | Hardcoded in source | Move to environment variables |
| **OpenAI API Key** | Hardcoded in source | Move to environment variables |
| **DB Credentials** | Hardcoded in source | Move to environment variables |
| **IMAP Connection** | SSL (port 993) | ✅ Already secure |
| **DB Connection** | Encrypted + TrustServerCertificate | ✅ Acceptable |
| **Data Validation** | Type coercion + null normalization | ✅ Good |
| **Duplicate Prevention** | DB-level + file-level checks | ✅ Good |

---

## 9. 📈 PERFORMANCE & SCALABILITY

| Metric | Current Value | Notes |
|--------|--------------|-------|
| **Poll Interval** | 60-120 seconds | Configurable |
| **Max Emails/Cycle** | 20 (index.py) | Configurable |
| **OpenAI Timeout** | 3 retries, exponential backoff | Robust |
| **DB Connection** | 30-second timeout | Per-operation |
| **Log Rotation** | 5 files × 5MB each | Automatic cleanup |
| **JSON Backups** | Per-email JSON files | In `extracted_pos/` folder |

---

## 10. 🚀 RUN MODES

### 10.1 Available Run Modes

| Mode | Command | Description |
|------|---------|-------------|
| **Live IMAP Polling** | `python po_extractor.py` | Continuous auto-processing |
| **Single File Test** | `python po_extractor.py --file email.eml` | Test a single .eml file |
| **DB Connection Test** | `python po_extractor.py --test-db` | Verify database connectivity |
| **Debug Mode** | `python po_extractor.py --debug` | Verbose logging output |
| **Legacy Continuous** | `python index.py` | Older version with PDF focus |
| **Legacy Single-Cycle** | `python index.py --once` | Run one cycle then stop |

---

## 11. 📂 FILE STRUCTURE

```
test mail working code/
├── index.py                    # v1: PDF-focused PO extractor (continuous polling)
├── po_extractor.py             # v3: Full email body + HTML extractor (IMAP watcher)
├── PRD.md                      # This requirements document
├── frontend/                   # Frontend dashboard website
│   ├── index.html              # Main dashboard page
│   ├── styles.css              # Premium dark-mode CSS
│   ├── app.js                  # Dashboard logic (search/filter/sort/export)
│   └── api.py                  # Python Flask API server for frontend
├── processed_emails.txt        # Tracks processed email IDs (v1)
├── extracted_pos/              # JSON backup files
├── logs/                       # Rotating log files
│   └── po_extractor.log
└── po_extractor.log            # Legacy log file (v1)
```

---

## 12. ✅ ACCEPTANCE CRITERIA

| # | Criteria | Status |
|---|---------|--------|
| 1 | System connects to Gmail IMAP over SSL | ✅ Done |
| 2 | System detects unseen/new emails | ✅ Done |
| 3 | System extracts text from email body (plain + HTML) | ✅ Done |
| 4 | System extracts text from PDF attachments (native + OCR) | ✅ Done |
| 5 | OpenAI GPT-4o accurately extracts PO fields | ✅ Done |
| 6 | Multi-product line items extracted separately | ✅ Done |
| 7 | Data inserted into SQL Server correctly | ✅ Done |
| 8 | Duplicate POs are not re-inserted | ✅ Done |
| 9 | Processed emails are moved to 'processed' folder | ✅ Done |
| 10 | Failed emails are moved to 'failed' folder | ✅ Done |
| 11 | System runs continuously without crashing | ✅ Done |
| 12 | JSON backup files are saved locally | ✅ Done |
| 13 | Rotating log files with console output | ✅ Done |
| 14 | Frontend dashboard displays all PO records | 🔄 Building |
| 15 | Excel export functionality | 🔄 Building |
| 16 | Search and filter capabilities in frontend | 🔄 Building |

---

## 13. 🔮 FUTURE ENHANCEMENTS

| # | Enhancement | Priority |
|---|------------|----------|
| 1 | Environment variables for all credentials | 🔴 HIGH |
| 2 | REST API for frontend integration | 🔴 HIGH |
| 3 | Email notification on extraction failure | 🟡 MEDIUM |
| 4 | Multi-user authentication for dashboard | 🟡 MEDIUM |
| 5 | Charts/graphs for PO analytics | 🟡 MEDIUM |
| 6 | Support for more email providers (Outlook, Yahoo) | 🟢 LOW |
| 7 | Webhook notifications | 🟢 LOW |
| 8 | Docker containerization | 🟡 MEDIUM |
| 9 | Unit test suite | 🟡 MEDIUM |
| 10 | PDF attachment preview in dashboard | 🟢 LOW |

---

*Document generated on 2026-02-24 | PO Extractor System v3.0*
