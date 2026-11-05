"""
╔══════════════════════════════════════════════════════════════════════════════╗
║     PO-BRAIN UNIFIED EXTRACTOR  –  PDF ATTACHMENTS + EMAIL BODY TEXT        ║
║                                                                              ║
║  Database : hyma_testdb (Server: 3.109.43.10,8016)                           ║
║  Prefix   : dbo.pobrain_ (3NF Enterprise Normalized Schema)                  ║
║  AI       : OpenAI GPT-4o (Structured JSON Line Item Extraction)             ║
║                                                                              ║
║  WORKFLOW:                                                                   ║
║    1. Connects to Gmail and polls for UNSEEN emails.                         ║
║    2. Checks for PDF attachments in the email.                               ║
║    3. If PDFs exist: extracts text (pdfplumber + pytesseract OCR fallback).  ║
║    4. If no PDFs: extracts text directly from plain/HTML email body.         ║
║    5. Calls OpenAI GPT-4o to extract PO details and line items.              ║
║    6. Populates relational DB tables: emails, attachments, jobs,             ║
║       purchase_orders, line_items, workflow_steps, processing_logs,          ║
║       error_logs, failed_transactions, and audit_logs in a transaction.      ║
║    7. Moves processed emails to 'processed' or 'failed' IMAP folders.        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import email as email_lib
import imaplib
import json
import logging
import os
import re
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
import time
import traceback
import hashlib
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from logging.handlers import RotatingFileHandler
from typing import Iterator, List, Optional, Tuple, Dict, Any

import pyodbc
import colorlog
from bs4 import BeautifulSoup
from openai import OpenAI

try:
    import pytesseract
    from PIL import Image
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


# ═════════════════════════════════════════════════════════════════════════════
#  §1  CONFIGURATION (Targeting the NEW hyma_testdb Database)
# ═════════════════════════════════════════════════════════════════════════════

# All timestamps in this pipeline are recorded in Indian Standard Time (UTC+5:30,
# no DST). Use now_ist() in Python; in SQL add 330 minutes to GETUTCDATE().
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist() -> datetime:
    """Current time in Indian Standard Time (timezone-aware)."""
    return datetime.now(IST)

OPENAI_API_KEY = os.environ.get(
    "OPENAI_API_KEY",
    "your-openai-api-key-here"
)
OPENAI_MODEL   = "gpt-4o"

IMAP_HOST             = "imap.gmail.com"
IMAP_PORT             = 993
IMAP_USE_SSL          = True
IMAP_USERNAME         = "ggitggitggit@gmail.com"
IMAP_PASSWORD         = "iksajinexdzpgzax"
IMAP_MAILBOX          = "INBOX"
IMAP_POLL_INTERVAL    = 60
IMAP_PROCESSED_FOLDER = "processed"
IMAP_FAILED_FOLDER    = "failed"
IMAP_SKIPPED_FOLDER   = "skipped"

# ── SMTP (OUTBOUND EMAIL) CONFIGURATION ─────────────────────────────────────
# Used for sending order acknowledgment emails to customers + internal copies.
# Uses the same Gmail account as IMAP; port 587 = STARTTLS (recommended for Gmail).
SMTP_HOST          = "smtp.gmail.com"
SMTP_PORT          = 587
SMTP_USERNAME      = IMAP_USERNAME    # same Gmail account
SMTP_PASSWORD      = IMAP_PASSWORD    # same app password
SMTP_FROM_NAME     = "Hyma Synthesis"
SMTP_FROM_ADDRESS  = IMAP_USERNAME
# Internal copy of every order acknowledgment is always CC'd here (temporary testing additions included):
SMTP_INTERNAL_CC   = ["plnarayana23@gmail.com"]


# ── BRANCH EMAIL IMAP CONFIGURATIONS ─────────────────────────────────────────
HYDERABAD_IMAP_USERNAME = "jingchaka1@gmail.com"
HYDERABAD_IMAP_PASSWORD = "auabgwlblbekbuhy"

BANGLORE_IMAP_USERNAME  = "narayanagagri@gmail.com"
BANGLORE_IMAP_PASSWORD  = "aefcccrrtuuijijy"

# ── BRANCH EMAIL CONFIGURATION ──────────────────────────────────────────────
# Configure recipient addresses that route to Hyderabad or Bangalore.
HYDERABAD_BRANCH_EMAILS = ["info@hymasynthesis.com", "jingchaka1@gmail.com", "ggitggitggit@gmail.com"]
BANGLORE_BRANCH_EMAILS  = ["bangloreinfo@hymasynthesis.com", "narayanagagri@gmail.com"]

# ── PO RELEVANCE PRE-FILTER ──────────────────────────────────────────────────
# Skip obviously non-PO mail (newsletters, notifications) BEFORE calling OpenAI,
# to save API cost and keep the database clean. An email is processed only if it
# has a PDF attachment OR its subject/body contains a PO keyword — AND its sender
# is not in the blocklist. Set ENABLE_PO_PREFILTER = False to process every email
# (legacy behaviour).
ENABLE_PO_PREFILTER = True

# Sender substrings that never send purchase orders (matched case-insensitively
# against the full "From" header). Keep these specific to avoid blocking real
# vendors.
PO_SENDER_BLOCKLIST = [
    "linkedin.com", "notion.so", "ollama.com", "kaggle.com", "docusign.com",
    "adobe.com", "lovable.dev", "n8n.io", "openai.com", "skywork.ai",
    "vapi.ai", "exotel.com", "mail.google.com", "accounts.google.com",
]

# ── LEGACY ERP INSERT (tblClientOrder / tblComment / SAT_WebOrder_Tracking) ───
# ENABLED. The schema-mismatch bugs were fixed on 2026-06-09 and verified end-to-end
# (all 3 tables insert for a registered vendor):
#   • OrderID (tblClientOrder/tblComment) + WebOrderID (SAT) now receive a generated
#     numeric order number (MAX+1 across the order tables — the ERP has no sequence).
#   • The PO reference STRING now goes into POID (tblClientOrder) and SONo (SAT).
#   • WebOrderID is now supplied (was the NOT-NULL failure).
# The insert only runs when a PO's vendor_email matches dbo.tblRegistration (PersonID
# lookup), so unknown senders are skipped.
# ⚠ Order numbers use MAX+1, which is safe for this single-instance pipeline against
#   hyma_testdb. If pointed at a PRODUCTION ERP that mints its own order numbers, use
#   the ERP's real generator instead to avoid races/collisions.
# Set to False to disable writing to the ERP tables entirely.
ENABLE_LEGACY_ERP_INSERT = True

# Dynamic DB Credentials provided by user
MSSQL_SERVER   = "3.109.43.10,8016"
MSSQL_DATABASE = "hyma_testdb"
MSSQL_USERNAME = "avrasynt_db"
MSSQL_PASSWORD = "avra_1234"
MSSQL_DRIVER   = "ODBC Driver 17 for SQL Server"

LOG_LEVEL = "INFO"


# ═════════════════════════════════════════════════════════════════════════════
#  §2  HIGH-PRECISION DATETIME LOGGING SYSTEM
# ═════════════════════════════════════════════════════════════════════════════

def _setup_logger(level: str = LOG_LEVEL) -> logging.Logger:
    logger = logging.getLogger("po_extractor")
    if logger.handlers:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Render all log timestamps in IST regardless of the server's local timezone.
    # Use *args so it works whether called bound (self, ts) or unbound (ts,) — the
    # timestamp is always the last argument.
    logging.Formatter.converter = lambda *a: datetime.fromtimestamp(a[-1] or 0.0, IST).timetuple()

    # Colorized Console Formatter with Millisecond Datetime precision
    console_fmt = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s.%(msecs)03d [%(levelname)-8s]%(reset)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            "DEBUG":    "cyan",
            "INFO":     "green",
            "WARNING":  "yellow",
            "ERROR":    "red",
            "CRITICAL": "bold_red",
        },
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(console_fmt)
    logger.addHandler(ch)

    # Local file rotating logs
    class SafeRotatingFileHandler(RotatingFileHandler):
        def doRollover(self):
            try:
                super().doRollover()
            except PermissionError:
                # Ignore lock errors if another process is running and holds the log file
                pass

    os.makedirs("logs", exist_ok=True)
    fh = SafeRotatingFileHandler(
        "logs/po_extractor.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)
    return logger

log = _setup_logger()


# ═════════════════════════════════════════════════════════════════════════════
#  §3  DATABASE CONNECTIVITY & HELPER BINDINGS
# ═════════════════════════════════════════════════════════════════════════════

def _conn_str() -> str:
    return (
        f"DRIVER={{{MSSQL_DRIVER}}};"
        f"SERVER={MSSQL_SERVER};"
        f"DATABASE={MSSQL_DATABASE};"
        f"UID={MSSQL_USERNAME};"
        f"PWD={MSSQL_PASSWORD};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=yes;"
    )

@contextmanager
def _db_conn():
    conn = pyodbc.connect(_conn_str(), timeout=30)
    try:
        # Fail fast on lock contention instead of hanging forever. The pipeline
        # sometimes opens a second connection (e.g. log_to_db → pobrain_processing_logs,
        # which has an FK to pobrain_emails) while an outer transaction still holds
        # a lock on the same row. Without a lock timeout that self-blocks and leaves
        # the connection idle-in-transaction, freezing the whole table. 15s → the
        # blocked statement errors out, the transaction rolls back and locks release.
        conn.execute("SET LOCK_TIMEOUT 15000")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def test_db_connection() -> bool:
    """Verifies connection to database and existence of pobrain_ tables."""
    try:
        with _db_conn() as conn:
            cursor = conn.execute("SELECT COUNT(1) FROM dbo.pobrain_lkp_status")
            row = cursor.fetchone()
            count = row[0] if row else 0
        log.info(f"✓ DB Connected! Found {count} status lookup codes in dbo.pobrain_lkp_status.")
        return True
    except Exception as exc:
        log.error(f"✗ DB Connection Failed: {exc}")
        return False


def create_notifications(cursor, type_code: str, title: str, message: str, related_po_number: Optional[str] = None, related_error_id: Optional[int] = None) -> None:
    """Inserts a notification record for all active users in dbo.pobrain_notifications."""
    try:
        # Fetch all active user IDs
        cursor.execute("SELECT user_id FROM dbo.pobrain_users WHERE is_active = 1")
        user_ids = [row[0] for row in cursor.fetchall()]
        
        # Fallback to user_id = 2 (admin) if no active users are returned
        if not user_ids:
            user_ids = [2]
            
        sql = """
        INSERT INTO dbo.pobrain_notifications (
            user_id, type, title, message, is_read, related_po_number, related_error_id, created_at, read_at
        ) VALUES (?, ?, ?, ?, 0, ?, ?, DATEADD(MINUTE, 330, GETUTCDATE()), NULL)
        """
        for uid in user_ids:
            cursor.execute(
                sql,
                uid,
                type_code[:50],
                title[:255],
                message,
                related_po_number[:50] if related_po_number else None,
                related_error_id
            )
        log.info(f"✓ Notifications created for {len(user_ids)} users: '{title}'")
    except Exception as exc:
        log.warning(f"Failed to create notifications: {exc}")


# ── Database Log Writers ──────────────────────────────────────────────────────

def log_to_db(email_id: Optional[int], level_code: str, message: str, sender: Optional[str] = None, subject: Optional[str] = None, correlation_id: Optional[str] = None):
    """Inserts a structured log record directly into dbo.pobrain_processing_logs."""
    try:
        # Resolve log level ID from code
        level_map = {"DEBUG": 1, "INFO": 2, "WARN": 3, "ERROR": 4, "FATAL": 5}
        level_id = level_map.get(level_code.upper(), 2)

        sql = """
        INSERT INTO dbo.pobrain_processing_logs (
            email_id, log_level_id, sender_email, email_subject, message, module_name, correlation_id, logged_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, DATEADD(MINUTE, 330, GETUTCDATE()))
        """
        with _db_conn() as conn:
            conn.execute(
                sql, 
                email_id, 
                level_id, 
                sender[:320] if sender else None, 
                subject[:500] if subject else None, 
                message[:2000], 
                "unified_po_extractor", 
                correlation_id
            )
    except Exception as exc:
        log.debug(f"Failed writing log row to database: {exc}")


def write_workflow_step(conn, email_id: int, stage_id: int, status_id: int, started_at: datetime, completed_at: datetime, remarks: str) -> None:
    """Inserts workflow step analytics to track pipeline stage metrics."""
    try:
        duration = int((completed_at - started_at).total_seconds() * 1000)
        sql = """
        INSERT INTO dbo.pobrain_workflow_steps (
            email_id, stage_id, status_id, service_name, started_at, completed_at, duration_ms, remarks, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, DATEADD(MINUTE, 330, GETUTCDATE()))
        """
        conn.execute(sql, email_id, stage_id, status_id, "unified_po_extractor", started_at, completed_at, duration, remarks[:500])
    except Exception as exc:
        log.warning(f"Failed writing workflow step {stage_id}: {exc}")


# ═════════════════════════════════════════════════════════════════════════════
#  §4  EMAIL TEXT & ATTACHMENT PARSER
# ═════════════════════════════════════════════════════════════════════════════

def _decode_hdr(raw: str) -> str:
    try:
        return str(make_header(decode_header(raw or "")))
    except Exception:
        return raw or ""

def _html_to_text(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "head", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")  # type: ignore[union-attr]
        return re.sub(r"\n{3,}", "\n\n", text).strip()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html).strip()

def _decode_part(part) -> Optional[str]:
    try:
        payload = part.get_payload(decode=True)
        if payload is None:
            return None
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    except Exception:
        return None


def parse_email_structure(raw_bytes: bytes) -> Dict[str, Any]:
    """Parses raw email bytes into headers, metadata, text body and downloads PDFs."""
    msg = email_lib.message_from_bytes(raw_bytes)

    sender  = _decode_hdr(msg.get("From",    "") or "")
    recipient = _decode_hdr(msg.get("To",     "") or "")
    subject = _decode_hdr(msg.get("Subject", "") or "")

    raw_date   = msg.get("Date", "") or ""
    email_date = now_ist()
    try:
        parsed = parsedate_to_datetime(raw_date)
        # Normalise the sender's timezone to IST so it matches every other timestamp.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        email_date = parsed.astimezone(IST)
    except Exception:
        pass

    plain_parts: List[str] = []
    html_parts:  List[str] = []
    attachments: List[Tuple[str, bytes]] = []

    for part in msg.walk():
        ctype = part.get_content_type()
        disposition = part.get("Content-Disposition", "") or ""
        filename = _decode_hdr(part.get_filename() or "")

        # Detect PDF attachment
        if "attachment" in disposition.lower() or filename.lower().endswith(".pdf") or ctype == "application/pdf":
            payload = part.get_payload(decode=True)
            if payload and filename:
                attachments.append((filename, bytes(payload)))
            continue

        # Extract text body segments
        payload = _decode_part(part)
        if not payload:
            continue
        if ctype == "text/plain":
            plain_parts.append(payload)
        elif ctype == "text/html":
            html_parts.append(payload)

    body = ""
    if plain_parts:
        body = "\n\n".join(plain_parts).strip()
    elif html_parts:
        body = _html_to_text("\n".join(html_parts))

    return {
        "from":        sender,
        "to":          recipient,
        "date":        email_date,
        "subject":     subject,
        "body":        body,
        "attachments": attachments
    }


# ── PDF Content Extractor (Native + OCR) ──────────────────────────────────────

def extract_pdf_native(pdf_path: str) -> str:
    if not PDFPLUMBER_AVAILABLE:
        return ""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text() or ""
                if page_text:
                    text += f"\n--- Page {i} ---\n{page_text}"
                tables = page.extract_tables() or []
                for table in tables:
                    for row in table:
                        if row:
                            text += "\n" + " | ".join(c.strip() if c else "" for c in row)
    except Exception as exc:
        log.warning(f"Native PDF Plumber failed on {pdf_path}: {exc}")
    return text.strip()


def extract_pdf_ocr(pdf_path: str) -> str:
    if not OCR_AVAILABLE:
        log.warning("Tesseract OCR libraries not installed. Skipping OCR.")
        return ""
    text = ""
    try:
        images = convert_from_path(pdf_path, dpi=300)
        for i, img in enumerate(images, 1):
            page_text = pytesseract.image_to_string(img, lang="eng")
            if page_text.strip():
                text += f"\n--- Page {i} (OCR) ---\n{page_text}"
    except Exception as exc:
        log.warning(f"OCR execution failed on {pdf_path}: {exc}")
    return text.strip()


def extract_text_from_pdf(pdf_path: str) -> Tuple[str, bool]:
    """Extracts text. Returns (extracted_text, is_ocr_used)."""
    native = extract_pdf_native(pdf_path)
    if len(native.strip()) > 50:
        return native, False
        
    log.info(f"  Sparse text found in '{os.path.basename(pdf_path)}'. Routing to OCR pipeline...")
    ocr = extract_pdf_ocr(pdf_path)
    if len(ocr.strip()) > 10:
        return ocr, True
        
    return "", False


# ═════════════════════════════════════════════════════════════════════════════
#  §5  AI EXTRACTION ENGINE
# ═════════════════════════════════════════════════════════════════════════════

_SYSTEM_PROMPT = """You are a senior intelligent PO document processing AI.
Your job is to read the provided text (which is either extracted from a PDF attachment or parsed from an email body text) and extract Purchase Order data.

RULES:
1. Extract ALL line items as a JSON array of objects. One object per product/chemical line item.
2. If multiple items belong to the same PO, create separate objects (repeat PO-level fields like po_number, delivery_address, vendor, etc. in every row).
3. Extract exact numeric GST TAX amounts only (ignore %, ignore currency symbols). Labeled: CGST, SGST, IGST. If only a percentage exists with no amount, set to null.
4. Convert dates to YYYY-MM-DD format.
5. Do NOT invent or guess values. Set missing items to null.
6. Return ONLY the valid JSON array. Do not include markdown code blocks, explanation text, or fences.
7. IDENTITY RULE — READ CAREFULLY: "HYMA SYNTHESIS PRIVATE LIMITED" (a.k.a. "Hyma Synthesis",
   PAN AASPA3762P, GST 36AAFCA3762P1Z8, address A/28/1/19 Road No.15 IDA Nacharam Hyderabad 500076)
   is US — the SUPPLIER who RECEIVES this Purchase Order and ships the goods. The PO is issued BY a
   customer TO us. Therefore vendor_name and vendor_email must be the CUSTOMER who issued the PO
   (the buyer / the party the goods are delivered to), and must NEVER be Hyma Synthesis. Ignore any
   block labelled "Vendor Name", "Goods Supplier Details", "Supplier", or "To:" — those refer to us.

FIELDS MAP:
- po_number        → Purchase Order #, PO No, Order Number
- po_date          → Date PO was issued (format YYYY-MM-DD)
- vendor_name      → The CUSTOMER / BUYER company that ISSUED this PO and to whom the goods are
                     delivered (the company shown in the PO header/logo, the bill-to / ship-to /
                     delivery-plant party). NEVER "Hyma Synthesis" — that is us, the supplier.
                     Examples: "FDC Limited", "Dr. Reddy's Laboratories Ltd."
- vendor_email     → The BUYER's / CUSTOMER's contact email — look under "Contact Details", "Buyer",
                     "Buyer's Name", "E Mail ID", or the purchase contact of the PO-issuing company.
                     NEVER our (Hyma Synthesis) email.
- delivery_address → Delivery / shipping destination
- gst_number       → GSTIN / GST Registration # of vendor or buyer
- cgst_number      → CGST tax amount ONLY (numeric value, e.g. 450)
- sgst_number      → SGST tax amount ONLY (numeric value, e.g. 450)
- igst_number      → IGST tax amount ONLY (numeric value, e.g. 900)
- product_name     → Chemical / item / product description
- cas_number       → CAS chemical registry number (e.g. 64-17-5)
- cat_number       → Catalog number or part code
- hsn_code         → HSN/SAC code
- pack_size        → Pack / packing size of the item AS PRINTED ON THE PO, e.g. "100 mg",
                     "1 kg", "500 ml", "25 KG", "10 x 6 ml". This is the physical pack the
                     product is supplied in — NOT the ordered quantity. null if not shown.
                     Do NOT invent or normalise an internal code; copy what the PO says.
- quantity         → Qty ordered (numeric only, no units)
- unit_of_measure  → unit of measure (e.g. bottles, kg, L)
- unit_price       → price per unit (numeric)
- amount           → total line price (quantity * unit_price)
- discount         → Discount PERCENT for the line if the PO prints one (numeric only,
                     e.g. 10 for "10%"). null if the PO shows no discount.
- gst_rate         → Total GST PERCENT for the line if the PO prints one (numeric only,
                     e.g. 18 for "GST @ 18%" or "IGST 18%"). null if not shown.

OUTPUT FORMAT:
[
  {
    "po_number": null,
    "po_date": null,
    "vendor_name": null,
    "vendor_email": null,
    "delivery_address": null,
    "gst_number": null,
    "cgst_number": null,
    "sgst_number": null,
    "igst_number": null,
    "product_name": null,
    "cas_number": null,
    "cat_number": null,
    "hsn_code": null,
    "pack_size": null,
    "quantity": null,
    "unit_of_measure": null,
    "unit_price": null,
    "amount": null,
    "discount": null,
    "gst_rate": null
  }
]"""

def clean_and_parse_json(raw: str) -> List[Dict[str, Any]]:
    """Clean fences and parse JSON list."""
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]

    parsed = json.loads(cleaned)
    if isinstance(parsed, dict):
        return [parsed]
    return parsed


def extract_data_via_openai(extracted_text: str, source_type: str) -> List[Dict[str, Any]]:
    """Sends the document text to OpenAI and parses structured line items."""
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    prompt = (
        f"SOURCE DOCUMENT TYPE: {source_type}\n"
        f"DOCUMENT TEXT CONTENT:\n"
        f"----------------------------------------\n"
        f"{extracted_text}\n"
        f"----------------------------------------\n"
        f"Extract all line items in full detail according to instructions."
    )
    
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        max_tokens=4000,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": prompt}
        ]
    )
    raw_content = response.choices[0].message.content or ""
    return clean_and_parse_json(raw_content)


# ═════════════════════════════════════════════════════════════════════════════
#  §6  TRANSACTIONAL PIPELINE WRITING LOGIC (10 Normalized Tables)
# ═════════════════════════════════════════════════════════════════════════════

# Type Parsers
def _has_value(val) -> bool:
    """True if val is a meaningful (non-empty, non-null-ish) value."""
    return val is not None and str(val).strip().lower() not in ("", "null", "none", "n/a", "na")

def _to_decimal(val) -> Optional[float]:
    if val is None: return None
    try:
        cleaned = re.sub(r"[^\d\.]", "", str(val).replace(",", ""))
        return float(cleaned) if cleaned else None
    except Exception: return None

def _to_date(val) -> Optional[str]:
    if val is None: return None
    s = str(val).strip()
    if s.lower() in ("null", "none", ""): return None
    if re.match(r"^\d{4}-\d{2}-\d{2}", s): return s[:10]
    return s[:10]


def check_po_duplicate(conn, po_number: str) -> bool:
    sql = "SELECT COUNT(1) FROM dbo.pobrain_purchase_orders WHERE po_number = ?"
    cursor = conn.execute(sql, po_number)
    return cursor.fetchone()[0] > 0


def lookup_person_id_by_email(cursor, email: str) -> Optional[int]:
    """Lookup PersonID from tblRegistration by EMailID (kept for compatibility)."""
    info = lookup_customer_by_email(cursor, email)
    return info["person_id"] if info else None


def resolve_product_details(cursor, cas: Optional[Any], po_catalog_no: Optional[Any], product_name: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Resolve both CatalogNo and HSNCODE from dbo.tblGroupSubNames.

    Returns:
        Tuple[Optional[str], Optional[str]]: (resolved_catalog_no, resolved_hsn_code)
    """
    printed = str(po_catalog_no).strip() if po_catalog_no and str(po_catalog_no).strip() else None
    cas_key = str(cas).strip() if cas and str(cas).strip() else None

    resolved_cat = None

    try:
        # 1. Validate the PO-printed catalog number against the master.
        if printed:
            cursor.execute(
                "SELECT TOP 1 CatalogNo FROM dbo.tblGroupSubNames "
                "WHERE LTRIM(RTRIM(CatalogNo)) = ?",
                printed,
            )
            row = cursor.fetchone()
            if row:
                resolved_cat = row[0]

        # 2. Resolve by CAS only when it is unambiguous (single distinct catalog).
        if not resolved_cat and cas_key:
            cursor.execute(
                "SELECT DISTINCT CatalogNo FROM dbo.tblGroupSubNames "
                "WHERE LTRIM(RTRIM(Cas)) = ? AND CatalogNo IS NOT NULL "
                "AND LTRIM(RTRIM(CatalogNo)) <> ''",
                cas_key,
            )
            matches = [r[0] for r in cursor.fetchall()]
            if len(matches) == 1:
                resolved_cat = matches[0]

        # 3. Fall back to matching by ChemicalName (product name)
        if not resolved_cat and product_name and product_name.strip():
            p_name = product_name.strip()
            # Try exact match first
            cursor.execute(
                "SELECT TOP 1 CatalogNo FROM dbo.tblGroupSubNames "
                "WHERE LTRIM(RTRIM(ChemicalName)) = ?",
                p_name,
            )
            row = cursor.fetchone()
            if row:
                resolved_cat = row[0]
            else:
                # Try substring match
                cursor.execute(
                    "SELECT TOP 1 CatalogNo FROM dbo.tblGroupSubNames "
                    "WHERE ChemicalName LIKE ?",
                    f"%{p_name}%",
                )
                row = cursor.fetchone()
                if row:
                    resolved_cat = row[0]
    except Exception as e:
        log.warning(f"Failed to resolve CatalogNo (cas={cas}, printed={po_catalog_no}, name={product_name}): {e}")

    # Fallback catalog code
    final_cat = resolved_cat if resolved_cat else printed

    # Fetch corresponding HSNCODE if we resolved a catalog number
    final_hsn = None
    if final_cat:
        try:
            cursor.execute(
                "SELECT TOP 1 HSNCODE FROM dbo.tblGroupSubNames WHERE LTRIM(RTRIM(CatalogNo)) = ? AND HSNCODE IS NOT NULL",
                final_cat,
            )
            row = cursor.fetchone()
            if row:
                final_hsn = str(row[0]).strip()
        except Exception as e:
            log.warning(f"Failed to retrieve HSNCODE for CatalogNo {final_cat}: {e}")

    return final_cat, final_hsn


def parse_pack_to_base_units(pack_str: Optional[str]) -> Optional[Tuple[float, str]]:
    """Parse a pack size string (e.g. '500 gm', '1 Kg', '2.5 L') into (value_in_base_unit, unit_type).
    unit_type is either 'g' (grams/solid) or 'ml' (milliliters/liquid).
    """
    if not pack_str:
        return None
    s = pack_str.lower().strip()
    s = re.sub(r'\s+', '', s)
    
    # Solids (kg, g, gm, grams)
    m_kg = re.search(r'([0-9.]+)(?:kg|kgs)', s)
    if m_kg:
        return float(m_kg.group(1)) * 1000.0, "g"
        
    m_gm = re.search(r'([0-9.]+)(?:g|gm|gms|gram|grams)', s)
    if m_gm:
        return float(m_gm.group(1)), "g"
        
    # Liquids (ml, l, lt, liters)
    m_ml = re.search(r'([0-9.]+)(?:ml|mls)', s)
    if m_ml:
        return float(m_ml.group(1)), "ml"
        
    m_l = re.search(r'([0-9.]+)(?:l|lt|lts|liter|liters)', s)
    if m_l:
        return float(m_l.group(1)) * 1000.0, "ml"
        
    return None


def lookup_db_unit_price(cursor, catalog_no: Optional[str], pack_size: Optional[str], branch_location: Optional[str], uom: Optional[str] = None) -> Optional[float]:
    """Resolve the unit price from the branch-specific stock pricing tables strictly.
    No default fallback to email price, but scaling from other database pack sizes is allowed.
    """
    if not catalog_no:
        return None

    # Determine table name based on branch
    branch = branch_location.strip().lower() if branch_location else "default"
    if "bangalore" in branch:
        table_name = "dbo.WebStock_Bangalore"
    elif "ahmedabad" in branch or "ahmadabad" in branch:
        table_name = "dbo.WebStock_Ahmadabad"
    else:
        table_name = "dbo.WebStock"

    # Resolve effective pack size string (use UOM if pack_size is empty/N/A)
    effective_pack = None
    if pack_size and pack_size.strip().lower() not in ("", "n/a", "none", "null"):
        effective_pack = pack_size.strip()
    elif uom and uom.strip().lower() not in ("", "n/a", "none", "null", "pcs", "box", "kit"):
        effective_pack = f"1 {uom.strip()}"

    # 1. Try direct lookup first
    if effective_pack:
        pack_code = lookup_pack_code(cursor, effective_pack)
        if pack_code:
            try:
                query = f"SELECT TOP 1 Price FROM {table_name} WHERE LTRIM(RTRIM(ItemCode)) = ? AND LTRIM(RTRIM(PackCode)) = ?"
                cursor.execute(query, catalog_no.strip(), pack_code.strip())
                row = cursor.fetchone()
                if row and row[0] is not None:
                    p_str = str(row[0]).strip()
                    if p_str:
                        return float(p_str)
            except Exception as e:
                log.warning(f"Direct price lookup failed for ItemCode={catalog_no}, PackCode={pack_code} in {table_name}: {e}")

    # 2. Fallback: Parse and scale the price from another available pack size in the database
    if effective_pack:
        target_parsed = parse_pack_to_base_units(effective_pack)
        if target_parsed:
            target_val, target_unit = target_parsed
            try:
                # Retrieve all pack sizes and prices for this product
                cursor.execute(f"SELECT PackSize, Price FROM {table_name} WHERE LTRIM(RTRIM(ItemCode)) = ?", catalog_no.strip())
                db_prices = []
                for row in cursor.fetchall():
                    p_sz = row[0]
                    p_str = str(row[1]).strip() if row[1] is not None else ""
                    price_val = float(p_str) if p_str else None
                    if price_val:
                        parsed_db = parse_pack_to_base_units(p_sz)
                        if parsed_db:
                            db_prices.append((parsed_db[0], parsed_db[1], price_val))

                # Try matching same unit type first (e.g. g vs g, ml vs ml)
                matches = [db for db in db_prices if db[1] == target_unit]
                if not matches and db_prices:
                    # Cross-unit fallback: if no same unit, match any valid entry
                    matches = db_prices
                
                if matches:
                    db_val, _, db_price = matches[0]
                    if db_val > 0.0:
                        scaled_price = (target_val / db_val) * db_price
                        log.info(f"Scaled unit price for ItemCode={catalog_no}, target={effective_pack} from db_size={db_val}: {scaled_price}")
                        return scaled_price
            except Exception as e:
                log.warning(f"Failed to perform pricing scaling for ItemCode={catalog_no}, target={effective_pack} in {table_name}: {e}")

    return None


def lookup_erp_error(cursor, error_code: str) -> Dict[str, str]:
    """Retrieve error reason and recommended solution from the master error lookup table."""
    try:
        cursor.execute(
            "SELECT error_reason, recommended_solution FROM dbo.pobrain_erp_errors_master WHERE error_code = ?",
            error_code
        )
        row = cursor.fetchone()
        if row:
            return {"reason": row[0], "solution": row[1]}
    except Exception as exc:
        log.warning(f"Failed to query pobrain_erp_errors_master for {error_code}: {exc}")
    
    # Fallback default values
    return {
        "reason": "An unexpected error occurred during the ERP insertion process.",
        "solution": "Review the application logs or stack trace to identify the cause of the failure and retry processing."
    }


def send_erp_notification_email(
    po_num: str,
    email_data: dict,
    is_success: bool,
    error_code: Optional[str] = None,
    error_details: Optional[Dict[str, str]] = None
) -> None:
    """Send an email notification to the internal CC list regarding the ERP insertion status."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text      import MIMEText

    try:
        orig_subject = email_data.get("subject", "(No Subject)")
        orig_from    = email_data.get("from", "Unknown")
        orig_date    = str(email_data.get("date"))

        # Determine color, prefix emoji, and status text
        if error_code == "DUPLICATE_SKIPPED":
            status_text = "SKIPPED (DUPLICATE)"
            prefix = "🟡"
        else:
            status_text = "SUCCESS" if is_success else "FAILED"
            prefix = "🟢" if is_success else "🔴"
        
        # Build subject for the notification email
        notification_subject = f"{prefix} {status_text}: ERP Pipeline | PO: {po_num} | Subject: {orig_subject}"

        # Build HTML body
        if error_code == "DUPLICATE_SKIPPED":
            html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 14px; color: #222; }}
  h2   {{ color: #856404; }}
  table {{ border-collapse: collapse; margin-top: 10px; }}
  td    {{ border: 1px solid #ccc; padding: 7px 10px; }}
  .duplicate-box {{ background: #fff3cd; border: 1px solid #ffeeba; padding: 15px; border-radius: 5px; margin-top: 15px; color: #856404; }}
</style>
</head>
<body>
  <h2>PO Processing Skipped (Duplicate Order)</h2>
  <p>The pipeline received a purchase order that has already been processed previously.</p>
  <hr>
  <h3>Mail Details</h3>
  <table>
    <tr><td><strong>PO Number:</strong></td><td>{po_num}</td></tr>
    <tr><td><strong>Original Subject:</strong></td><td><span style="background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 14px; display: inline-block;">{orig_subject}</span></td></tr>
    <tr><td><strong>Sender:</strong></td><td>{orig_from}</td></tr>
    <tr><td><strong>Received At:</strong></td><td>{orig_date}</td></tr>
  </table>
  
  <div class="duplicate-box">
    <h3 style="margin-top:0;">Duplicate Check Information</h3>
    <p>This PO number already exists in the PO-Brain database. The pipeline has skipped re-inserting it to prevent order duplication.</p>
  </div>
</body>
</html>"""
        elif is_success:
            html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 14px; color: #222; }}
  h2   {{ color: green; }}
  table {{ border-collapse: collapse; margin-top: 10px; }}
  td    {{ border: 1px solid #ccc; padding: 7px 10px; }}
</style>
</head>
<body>
  <h2>ERP Insertion Completed Successfully</h2>
  <p>The purchase order has been successfully extracted and inserted into the ERP database.</p>
  <hr>
  <h3>Mail Details</h3>
  <table>
    <tr><td><strong>PO Number:</strong></td><td>{po_num}</td></tr>
    <tr><td><strong>Original Subject:</strong></td><td><span style="background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 14px; display: inline-block;">{orig_subject}</span></td></tr>
    <tr><td><strong>Sender:</strong></td><td>{orig_from}</td></tr>
    <tr><td><strong>Received At:</strong></td><td>{orig_date}</td></tr>
  </table>
</body>
</html>"""
        else:
            reason = error_details.get("reason", "Unknown") if error_details else "Unknown"
            solution = error_details.get("solution", "Unknown") if error_details else "Unknown"
            html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 14px; color: #222; }}
  h2   {{ color: red; }}
  table {{ border-collapse: collapse; margin-top: 10px; }}
  td    {{ border: 1px solid #ccc; padding: 7px 10px; }}
  .error-box {{ background: #fdf2f2; border: 1px solid #f5c2c2; padding: 15px; border-radius: 5px; margin-top: 15px; }}
</style>
</head>
<body>
  <h2>ERP Insertion Failed</h2>
  <p>The purchase order was successfully saved to PO-Brain but failed to insert into the ERP legacy tables.</p>
  <hr>
  <h3>Mail Details</h3>
  <table>
    <tr><td><strong>PO Number:</strong></td><td>{po_num}</td></tr>
    <tr><td><strong>Original Subject:</strong></td><td><span style="background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 14px; display: inline-block;">{orig_subject}</span></td></tr>
    <tr><td><strong>Sender:</strong></td><td>{orig_from}</td></tr>
    <tr><td><strong>Received At:</strong></td><td>{orig_date}</td></tr>
  </table>
  
  <div class="error-box">
    <h3 style="margin-top:0; color: #9b1c1c;">Error Information</h3>
    <p><strong>Error Code:</strong> <code style="background:#f1f1f1; padding:2px 4px; border-radius:3px;">{error_code}</code></p>
    <p><strong>Error Reason:</strong> {reason}</p>
    <p><strong>Recommended Solution:</strong> {solution}</p>
  </div>
</body>
</html>"""

        # Compose MIME message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = notification_subject
        msg["From"]    = f"{SMTP_FROM_NAME} <{SMTP_FROM_ADDRESS}>"
        msg["To"]      = ", ".join(SMTP_INTERNAL_CC)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # Send via SMTP
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM_ADDRESS, SMTP_INTERNAL_CC, msg.as_string())

        log.info(f"  ERP NOTIFICATION SENT: {status_text} for PO '{po_num}' -> {SMTP_INTERNAL_CC}")
        try:
            log_to_db(
                None, "INFO",
                f"ERP notification email ({status_text}) sent to {', '.join(SMTP_INTERNAL_CC)} for PO '{po_num}'.",
                orig_from, orig_subject, None
            )
        except Exception as l_exc:
            log.debug(f"Failed logging ERP notification send event: {l_exc}")
    except Exception as exc:
        log.warning(f"  ERP NOTIFICATION FAILED (non-fatal): {exc}")


def lookup_customer_by_email(cursor, email: Optional[str]) -> Optional[Dict[str, Any]]:
    """Resolve the ERP customer for a vendor/buyer email via dbo.tblRegistration.

    Returns the master-data we attach to ERP orders: PersonID (FK), the customer's
    internal CompanyCode, Discount, and contact details (Name, MobileNo, City)
    used in order acknowledgment emails. None when the email is not a registered
    customer. This is a deterministic exact-email match -- no guessing.
    """
    if not email or not email.strip():
        return None
    try:
        cursor.execute(
            "SELECT TOP 1 PersonID, CompanyCode, Discount, "
            "ContPerson AS FullName, "
            "Phone1 AS MobileNo, City, CompanyName "
            "FROM dbo.tblRegistration WHERE EMailID = ?",
            email.strip(),
        )
        row = cursor.fetchone()
        if not row:
            return None
        # Some master rows store CompanyCode as an empty/blank string -- treat that
        # as "no value" so we persist a true NULL instead of ''.
        company_code = row[1].strip() if isinstance(row[1], str) and row[1].strip() else None
        return {
            "person_id":    row[0],
            "company_code": company_code,
            "discount":     int(row[2]) if row[2] is not None else None,
            "full_name":    row[3].strip() if row[3] else None,
            "mobile_no":    str(row[4]).strip() if row[4] else None,
            "city":         str(row[5]).strip() if row[5] else None,
            "company_name": str(row[6]).strip() if row[6] else None,
        }
    except Exception as e:
        log.warning(f"Failed to lookup customer for email {email}: {e}")
        return None






def _normalize_pack(text: Any) -> str:
    """Clean prefixes and unit abbreviations for accurate pack-size matching."""
    if not text:
        return ""
    s = str(text).lower().strip()
    s = re.sub(r"^1\s*[xX\*]\s*", "", s)
    s = re.sub(r"[^a-z0-9.]", "", s)
    s = re.sub(r"(?:gm|gms|grams|gram)$", "g", s)
    s = re.sub(r"(?:mls)$", "ml", s)
    s = re.sub(r"(?:lt|lts|liters|liter)$", "l", s)
    return s


def lookup_pack_code(cursor, pack_size: Optional[Any]) -> Optional[str]:
    """Resolve the ERP PackCode from dbo.Avra2020_PackingCodes by NORMALIZED match.

    The PO's printed pack size (e.g. "10 x 6 ml") is normalized and compared
    against both PackCode and PackDesc. Returns None when there is no confident
    match — PackCode then stays NULL rather than being guessed wrong.
    """
    if not pack_size or not str(pack_size).strip():
        return None
    target = _normalize_pack(pack_size)
    if not target:
        return None
    try:
        cursor.execute("SELECT PackCode, PackDesc FROM dbo.Avra2020_PackingCodes")
        for code, desc in cursor.fetchall():
            if code and _normalize_pack(code) == target:
                return code
            if desc and _normalize_pack(desc) == target:
                return code
        return None
    except Exception as e:
        log.warning(f"Failed to lookup PackCode for pack size {pack_size}: {e}")
        return None


def _clean_pack_size_display(pack_size: Optional[str]) -> Optional[str]:
    """Strip prefix multipliers (like '1 x', '1 *', '1x') from pack size display strings."""
    if not pack_size:
        return pack_size
    s = pack_size.strip()
    s = re.sub(r"^1\s*[xX\*]\s*", "", s)
    s = re.sub(r"^1[xX\*]\s*", "", s)
    return s


def _to_pct(val: Any) -> Optional[float]:
    """Parse a percentage into a plain number: '18', 18, '18%', '18 %' -> 18.0.
    Returns None for absent/blank/non-numeric input."""
    if val is None:
        return None
    s = str(val).strip().rstrip("%").strip()
    if not s or s.lower() in ("null", "none", "na", "n/a"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def resolve_gst_rate(cursor, cas: Optional[Any], catalog: Optional[Any], product_name: Optional[str] = None) -> Optional[float]:
    """Resolve the GST % from dbo.tblGroupSubNames.GSTPER (values like '18%', '5%').

    Order (deterministic, no guessing): CatalogNo exact match → else CAS only when
    it maps to a single distinct GST % → else ChemicalName fallback.
    Returns None when not found / ambiguous.
    """
    cat = str(catalog).strip() if catalog and str(catalog).strip() else None
    cas_key = str(cas).strip() if cas and str(cas).strip() else None
    try:
        if cat:
            cursor.execute(
                "SELECT TOP 1 GSTPER FROM dbo.tblGroupSubNames "
                "WHERE LTRIM(RTRIM(CatalogNo)) = ? AND GSTPER IS NOT NULL", cat)
            row = cursor.fetchone()
            if row:
                p = _to_pct(row[0])
                if p is not None:
                    return p
        if cas_key:
            cursor.execute(
                "SELECT DISTINCT GSTPER FROM dbo.tblGroupSubNames "
                "WHERE LTRIM(RTRIM(Cas)) = ? AND GSTPER IS NOT NULL "
                "AND LTRIM(RTRIM(GSTPER)) <> ''", cas_key)
            rates = {_to_pct(r[0]) for r in cursor.fetchall()}
            rates.discard(None)
            if len(rates) == 1:
                return rates.pop()
        
        # 3. Fallback to product name
        if product_name and product_name.strip():
            cursor.execute(
                "SELECT TOP 1 GSTPER FROM dbo.tblGroupSubNames "
                "WHERE LTRIM(RTRIM(ChemicalName)) = ? AND GSTPER IS NOT NULL",
                product_name.strip(),
            )
            row = cursor.fetchone()
            if row:
                p = _to_pct(row[0])
                if p is not None:
                    return p
    except Exception as e:
        log.warning(f"Failed to resolve GST rate (cas={cas}, cat={catalog}, name={product_name}): {e}")
    return None


def normalize_quantity_to_packs(qty: Optional[float], pack_size: Optional[str]) -> float:
    """Normalize extracted quantity to pack count (e.g. quantity=250 for 250 G pack -> 1 pack)."""
    if qty is None or qty <= 0.0:
        return 1.0
    if not pack_size:
        return qty

    parsed = parse_pack_to_base_units(pack_size)
    if parsed:
        pack_weight, _ = parsed
        if pack_weight > 0.0:
            calculated_packs = qty / pack_weight
            if qty >= pack_weight:
                return round(calculated_packs, 3)
    return qty


def compute_line_financials(cursor, item: Dict[str, Any], cust_discount: Optional[Any], resolved_catalog_no: Optional[str] = None, branch_location: Optional[str] = None) -> Dict[str, Any]:
    """Single source of truth for a line's money fields — used by BOTH the ERP
    (tblClientOrder) and the PO-Brain writes.

    Strictly fetches and applies pricing, discount %, and GST % from the database only.
    No fallback to email values. Normalizes quantity to pack counts.
    """
    raw_qty = _to_decimal(item.get("quantity"))
    pack_size = item.get("pack_size")
    
    qty = normalize_quantity_to_packs(raw_qty, pack_size)
    if qty is None:
        qty = 1.0

    # Resolve unit price strictly from database stock tables (no fallback to email)
    db_price = lookup_db_unit_price(cursor, resolved_catalog_no, pack_size, branch_location, uom=item.get("unit_of_measure"))
    unit_price = db_price if db_price is not None else 0.0

    # Calculate price based on DB unit price and normalized pack quantity
    price = qty * unit_price

    # Discount %: Strictly from customer master (ignore email/PO discount)
    disc_pct = _to_pct(cust_discount) if cust_discount is not None else 0.0

    # GST %: Strictly from database master (ignore email/PO GST)
    gst_pct = resolve_gst_rate(cursor, item.get("cas_number"), item.get("cat_number"), item.get("product_name"))
    if gst_pct is None:
        gst_pct = 0.0

    discount_amt = price * disc_pct / 100.0
    discount_price = price - discount_amt
    gst_amount = discount_price * gst_pct / 100.0

    # Determine CGST/SGST vs IGST split
    cgst_a, sgst_a, igst_a = None, None, None
    cgst_r, sgst_r, igst_r = None, None, None
    
    is_igst = False
    delivery_addr = str(item.get("delivery_address") or "").lower()
    if delivery_addr and not any(kw in delivery_addr for kw in ("telangana", "hyderabad", "secunderabad", "nacharam", "mallapur")):
        is_igst = True

    if is_igst:
        igst_r = gst_pct
        igst_a = gst_amount
    else:
        cgst_r = gst_pct / 2.0
        sgst_r = gst_pct / 2.0
        cgst_a = gst_amount / 2.0
        sgst_a = gst_amount / 2.0

    return {
        "qty": qty, 
        "unit_price": unit_price, 
        "price": price, 
        "amount": price,
        "disc_pct": disc_pct, 
        "discount_amt": discount_amt, 
        "discount_price": discount_price,
        "gst_pct": gst_pct, 
        "gst_amount": gst_amount,
        "cgst_a": cgst_a, "sgst_a": sgst_a, "igst_a": igst_a,
        "cgst_r": cgst_r, "sgst_r": sgst_r, "igst_r": igst_r,
        "line_total": discount_price + gst_amount,
    }


def send_order_acknowledgment_email(
    order_id: int,
    po_num: str,
    vendor_email: str,
    customer: dict,
    items: List[Dict[str, Any]],
    comments: Optional[str] = None,
    financials: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Send a rich HTML order acknowledgment email to the customer + internal CC.

    Recipients:
      TO  : vendor_email (the buyer who placed the PO)
      CC  : SMTP_INTERNAL_CC (e.g. sales@hymasynthesis.com)
    Template: Hyma standard order acknowledgment with line-item table + summary.

    `financials` is the list of per-item money dicts (from compute_line_financials),
    computed DURING the DB transaction and passed in so this function needs no DB
    connection — it is sent AFTER the transaction commits, never holding locks.
    Errors are caught and logged so they never affect the order.
    """
    financials = financials or []
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text      import MIMEText

    try:
        # ── Collect customer details ─────────────────────────────────────────
        company_name = customer.get("company_name") or customer.get("company_code") or "N/A"
        full_name    = customer.get("full_name")    or "Customer"
        mobile_no    = customer.get("mobile_no")    or "N/A"
        city         = customer.get("city")         or "N/A"

        # ── Build line-item rows ──────────────────────────────────────────────
        line_rows_html   = ""
        total_unit_price = 0.0
        total_price      = 0.0
        total_net_price  = 0.0   # sum of NET prices after discount (= Discount Price column total)
        total_gst        = 0.0

        for idx, item in enumerate(items, 1):
            # Reuse the financials computed during the DB write so the numbers the
            # customer sees exactly match what was stored (no DB access here).
            fin        = financials[idx - 1] if idx - 1 < len(financials) else {}
            qty        = fin.get("qty") or 0.0
            unit_price = fin.get("unit_price") or 0.0
            price      = fin.get("price") or 0.0
            # net_price = price AFTER discount is applied (what the customer actually pays
            # before GST). This is shown in the "Discount Price" column per the layout.
            net_price  = fin.get("discount_price") or 0.0
            disc_amt   = fin.get("discount_amt") or 0.0    # actual money taken off
            line_disc  = fin.get("disc_pct") or 0          # per-line discount %
            # Use 'is not None' check so that a resolved rate of 0% displays as "0%"
            # instead of falling back to N/A (Python treats 0 as falsy).
            gst_rate_pct = fin.get("gst_pct")              # may be None or a number (including 0)
            gst_rate     = gst_rate_pct if gst_rate_pct is not None else 0.0
            gst_price    = fin.get("gst_amount") or 0.0    # GST on the net price
            total_item   = fin.get("line_total") or 0.0

            total_unit_price += unit_price
            total_price      += price
            total_net_price  += net_price
            total_gst        += gst_price

            # Read the DB-enriched values injected by insert_into_legacy_tables.
            # Fall back to the raw GPT value if enrichment wasn't available.
            display_cat    = item.get("cat_number") or 'N/A'
            display_hsn    = item.get("hsn_code")   or 'N/A'
            display_cas    = item.get("cas_number") or 'N/A'
            display_pack   = item.get("pack_size")  or 'N/A'
            uom            = item.get("unit_of_measure") or ""
            display_qty    = f"{qty} {uom}".strip() if uom else f"{qty}"
            # GST %: prefer the resolved rate stored in _resolved_gst_pct; if absent,
            # fall back to fin.get("gst_pct"). Show 'N/A' only when truly unresolved.
            _r_gst = item.get("_resolved_gst_pct", gst_rate_pct)
            display_gst_pct = f"{int(_r_gst)}%" if _r_gst is not None else 'N/A'

            line_rows_html += f"""
            <tr>
              <td>{order_id}</td>
              <td>{display_cat}</td>
              <td>{display_hsn}</td>
              <td>{display_gst_pct}</td>
              <td>{display_cas}</td>
              <td>{item.get('product_name') or 'N/A'}</td>
              <td>{display_pack}</td>
              <td>{display_qty if qty else 'N/A'}</td>
              <td>{unit_price:.2f}</td>
              <td>{price:.2f}</td>
              <td>{line_disc}%</td>
              <td>{net_price:.2f}</td>
              <td>{gst_price:.2f}</td>
              <td><strong>{total_item:.2f}</strong></td>
            </tr>"""

        # grand_total = sum of NET prices + total GST (= sum of all line_totals)
        grand_total = total_net_price + total_gst

        # ── Comments block (only if present) ─────────────────────────────────
        comments_html = (
            f"<tr><td><strong>Comments:</strong></td>"
            f"<td>{comments}</td></tr>"
            if comments else ""
        )

        # ── Full HTML body ────────────────────────────────────────────────────
        html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  body      {{ font-family: Arial, sans-serif; font-size: 14px; color: #222; }}
  h2        {{ color: #1a5276; }}
  table     {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
  th        {{ background: #1a5276; color: #fff; padding: 8px; text-align: center; }}
  td        {{ border: 1px solid #ccc; padding: 7px 10px; }}
  .summary  {{ margin-top: 20px; max-width: 420px; }}
  .summary td:last-child {{ text-align: right; font-weight: bold; }}
  .grand    {{ background: #f0f3ff; }}
  .footer   {{ margin-top: 30px; color: #555; font-size: 13px; }}
  a         {{ color: #1a5276; }}
</style>
</head>
<body>
<p>Dear <strong>{full_name}</strong>,</p>
<p>Thank you for your order.</p>
<p>We acknowledge the receipt of the order copy. The material ordered against
<strong>Order No: {order_id}</strong> will be processed subject to product availability.</p>

<hr>
<h2>Customer Details</h2>
<table class="summary">
  <tr><td><strong>Company Name:</strong></td>      <td>{company_name}</td></tr>
  <tr><td><strong>Customer Name:</strong></td>     <td>{full_name}</td></tr>
  <tr><td><strong>Email:</strong></td>             <td>{vendor_email}</td></tr>
  <tr><td><strong>Contact No:</strong></td>        <td>{mobile_no}</td></tr>
  <tr><td><strong>City:</strong></td>              <td>{city}</td></tr>
  {comments_html}
</table>

<hr>
<h2>Order Details</h2>
<table>
  <thead>
    <tr>
      <th>Order No</th><th>Item Code</th><th>HSN Code</th><th>GST %</th>
      <th>CAS No</th><th>Chemical Name</th><th>Pack Size</th><th>Quantity</th>
      <th>Unit Price (Rs.)</th><th>Price (Rs.)</th><th>Discount %</th><th>Discount Price</th>
      <th>GST Price</th><th>Total Price</th>
    </tr>
  </thead>
  <tbody>{line_rows_html}</tbody>
  <tfoot>
    <tr style="background:#eef2ff;">
      <td colspan="7" style="border-top:2px solid #1a5276;"></td>
      <td style="text-align:right;font-weight:bold;border-top:2px solid #1a5276;">Total:</td>
      <td style="font-weight:bold;border-top:2px solid #1a5276;">{total_unit_price:.2f}</td>
      <td style="font-weight:bold;border-top:2px solid #1a5276;">{total_price:.2f}</td>
      <td style="border-top:2px solid #1a5276;"></td>
      <td style="font-weight:bold;border-top:2px solid #1a5276;">{total_net_price:.2f}</td>
      <td style="font-weight:bold;border-top:2px solid #1a5276;">{total_gst:.2f}</td>
      <td style="font-weight:bold;border-top:2px solid #1a5276;">{grand_total:.2f}</td>
    </tr>
  </tfoot>
</table>

<div class="footer">
  <p>We will get back to you in case any clarification is required or notify you
     by email in case of any discrepancy.</p>
  <p>For any queries, please contact:<br>
     <a href="mailto:sales@hymasynthesis.com">sales@hymasynthesis.com</a><br>
     <a href="mailto:enquiry@hymasynthesis.com">enquiry@hymasynthesis.com</a>
  </p>
</div>
</body>
</html>"""

        # ── Compose MIME message ─────────────────────────────────────────────
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Hyma | Web | Order | {order_id}"
        msg["From"]    = f"{SMTP_FROM_NAME} <{SMTP_FROM_ADDRESS}>"
        msg["To"]      = vendor_email
        msg["Cc"]      = ", ".join(SMTP_INTERNAL_CC)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # ── Send via SMTP (STARTTLS) ─────────────────────────────────────────
        all_recipients = [vendor_email] + SMTP_INTERNAL_CC
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM_ADDRESS, all_recipients, msg.as_string())

        log.info(
            f"  EMAIL SENT: Order acknowledgment for Order {order_id} / PO '{po_num}' "
            f"-> {vendor_email}  CC: {SMTP_INTERNAL_CC}"
        )
        try:
            log_to_db(
                None, "INFO",
                f"Order acknowledgment email sent to {vendor_email} for Order {order_id} (PO: '{po_num}').",
                vendor_email, f"Hyma | Web | Order | {order_id}", None
            )
        except Exception as l_exc:
            log.debug(f"Failed logging acknowledgment email send event: {l_exc}")

    except Exception as exc:
        # Email failure must NEVER abort the ERP transaction.
        log.warning(f"  EMAIL FAILED (non-fatal): Could not send acknowledgment for PO '{po_num}': {exc}")


def insert_into_legacy_tables(
    cursor,
    po_num: str,
    po_date: Optional[str],
    vendor_email: Optional[str],
    items: List[Dict[str, Any]],
    email_data: dict,
    branch_location: Optional[str] = None
) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    """Insert PO data into legacy tables: tblClientOrder, tblComment, SAT_WebOrder_Tracking."""

    if not items:
        return None, None

    try:
        # Lookup PersonID by vendor email
        if not vendor_email:
            log.warning(f"No vendor email provided for PO {po_num}. Skipping legacy table inserts.")
            return None, None

        customer = lookup_customer_by_email(cursor, vendor_email)
        if customer is None:
            log.warning(f"Could not find PersonID for vendor email {vendor_email}. Skipping legacy table inserts.")
            return None, None

        person_id        = customer["person_id"]
        cust_company_code = customer["company_code"]   # tblRegistration.CompanyCode
        cust_discount     = customer["discount"]        # tblRegistration.Discount (int %)

        # Generate a fresh numeric ERP order number. OrderID (tblClientOrder /
        # tblComment) and WebOrderID (SAT_WebOrder_Tracking) share this value. The
        # ERP has no sequence object, so we take MAX+1 across the order tables.
        # NOTE: safe for this single-instance pipeline; a live ERP that mints its
        # own order numbers would need its real generator to avoid races. Within
        # this transaction uncommitted rows are visible, so multiple POs in one
        # email each receive a distinct number.
        cursor.execute(
            "SELECT ISNULL(MAX(n), 0) + 1 FROM ("
            " SELECT MAX(OrderID) AS n FROM dbo.tblClientOrder"
            " UNION ALL SELECT MAX(WebOrderID) FROM dbo.SAT_WebOrder_Tracking) x"
        )
        new_order_id = int(cursor.fetchone()[0])

        # OrderDate / WebOrderDate are reused across the rows; WebOrderDate is NOT
        # NULL so fall back to today (IST) when the PO has no date.
        order_date   = _to_date(po_date) or now_ist().strftime("%Y-%m-%d")
        company_code = cust_company_code  # customer's CompanyCode from tblRegistration

        line_financials: List[Dict[str, Any]] = []

        # enriched_items are copies of the raw GPT items, augmented with values
        # resolved from ERP master tables (catalog_no, gst_rate). These enriched
        # dicts are passed into the acknowledgment email so the customer sees the
        # DB-resolved Item Code and GST % instead of N/A.
        enriched_items: List[Dict[str, Any]] = []

        for idx, item in enumerate(items, 1):
            # Resolve ERP master codes by deterministic lookup (NOT from GPT):
            #   CatalogNo ← Hyma catalog no from tblGroupSubNames (else PO value/NULL)
            #   PackCode  ← Avra2020_PackingCodes match on the PO pack size (else NULL)
            #   HSNCode   ← Resolved HSNCODE from tblGroupSubNames matching catalog_no
            catalog_no, resolved_hsn = resolve_product_details(cursor, item.get("cas_number"), item.get("cat_number"), item.get("product_name"))
            pack_code = lookup_pack_code(cursor, item.get("pack_size"))

            # Single shared money calc (PO-first discount/GST, GST on the NET price).
            fin = compute_line_financials(cursor, item, cust_discount, resolved_catalog_no=catalog_no, branch_location=branch_location)
            line_financials.append(fin)

            qty            = fin["qty"]
            unit_price     = fin["unit_price"]
            price          = fin["price"]
            discount       = fin["disc_pct"]          # Discount %  (PO else customer master)
            discount_price = fin["discount_price"]    # NET price after discount
            gst_tax        = fin["gst_pct"]           # GST %  (PO else GSTPER master)
            gst_price      = fin["gst_amount"]        # GST charged on the NET price

            # Resolve HSN fallback: DB resolved HSNCODE -> else extracted PO HSNCode
            final_hsn = resolved_hsn if resolved_hsn else (item.get("hsn_code") or "")

            insert_sql = """
            INSERT INTO dbo.tblClientOrder (
                PersonID, CompanyCode, PackCode, PackSize, CASNo, ChemicalName,
                CatalogNo, Quantity, UnitPrice, CurrentQty, DItemCode, ItemCode,
                Price, Discount, DiscountPrice, CAS, OrderID, POID, Flag,
                OrderDate, HSNCode, GSTTAX, Plateform, GstPrice
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            cursor.execute(insert_sql, (
                person_id,                                          # PersonID
                company_code,                                       # CompanyCode (tblRegistration)
                pack_code,                                          # PackCode (Avra2020_PackingCodes)
                _clean_pack_size_display(item.get("pack_size"))[:50] if _has_value(item.get("pack_size")) else None,  # PackSize varchar(50)
                item.get("cas_number")[:30] if item.get("cas_number") else None,  # CASNo
                item.get("product_name")[:500] if item.get("product_name") else None,  # ChemicalName
                catalog_no[:50] if catalog_no else None,            # CatalogNo (Hyma catalog, tblGroupSubNames)
                qty,                                                # Quantity
                unit_price,                                         # UnitPrice
                qty,                                                # CurrentQty (same as Quantity)
                None,                                               # DItemCode (no master source)
                catalog_no[:50] if catalog_no else None,            # ItemCode (inserted resolved cat_number here)
                price,                                              # Price
                int(discount) if discount is not None else None,    # Discount % (PO else customer master)
                discount_price,                                     # DiscountPrice (NET price after discount)
                item.get("cas_number")[:30] if item.get("cas_number") else None,  # CAS
                new_order_id,                                       # OrderID (numeric ERP order no.)
                po_num[:50] if po_num else None,                    # POID (PO reference string)
                0,                                                  # Flag (default 0)
                order_date,                                         # OrderDate
                final_hsn[:20] if final_hsn else None,              # HSNCode
                int(gst_tax) if gst_tax is not None else None,      # GSTTAX (int column)
                "Email",                                            # Plateform
                gst_price                                           # GstPrice
            ))

            log.info(f"  ✓ Inserted into tblClientOrder: PO {po_num}, Item {idx}")

            # Build the enriched item for the acknowledgment email.
            # Start with a copy of the raw GPT item, then overlay DB-resolved values
            # so the email shows the authoritative ERP catalog code and GST rate.
            enriched = dict(item)
            enriched["pack_size"] = _clean_pack_size_display(item.get("pack_size"))
            if catalog_no:
                enriched["cat_number"] = catalog_no
            if final_hsn:
                enriched["hsn_code"] = final_hsn
            if gst_tax is not None:
                # Store resolved GST % back onto the item so the template can read it
                # without going through the financials dict (avoids the 0-is-falsy trap).
                enriched["_resolved_gst_pct"] = gst_tax
            enriched_items.append(enriched)

        # 2. Insert into tblComment (one row per PO, if there are notes)
        # Extract any notes from email body or subject
        email_body = email_data.get("body", "")
        notes = None

        # Try to extract special notes/comments if present
        if "note" in email_body.lower() or "comment" in email_body.lower():
            notes = email_body[:1000]  # Take first 1000 chars of body as comment

        if notes:
            comment_sql = """
            INSERT INTO dbo.tblComment (OrderID, Comment, CreatedDate, CreatedBy)
            VALUES (?, ?, DATEADD(MINUTE, 330, GETUTCDATE()), ?)
            """
            cursor.execute(comment_sql, new_order_id, notes, person_id)
            log.info(f"  ✓ Inserted into tblComment: PO {po_num}")

        # 3. Insert into SAT_WebOrder_Tracking (one row per PO)
        web_order_cust_code = cust_company_code  # customer's CompanyCode (tblRegistration)

        tracking_sql = """
        INSERT INTO dbo.SAT_WebOrder_Tracking (
            WebOrderID, WebOrderDate, WebOrderCustCode, WebOrderTimeStamp, SONo, SODate
        ) VALUES (?, ?, ?, DATEADD(MINUTE, 330, GETUTCDATE()), ?, ?)
        """
        cursor.execute(tracking_sql, (
            new_order_id,                    # WebOrderID (numeric PK, required)
            order_date,                      # WebOrderDate (NOT NULL)
            web_order_cust_code,             # WebOrderCustCode (if available, else NULL)
            po_num[:20] if po_num else None, # SONo (PO number string, varchar(20))
            order_date                       # SODate
        ))

        log.info(f"  Inserted into SAT_WebOrder_Tracking: PO {po_num}")

        # 4. Build the acknowledgment-email payload and return it so the CALLER can
        #    send it AFTER the DB transaction commits (SMTP must never run while the
        #    transaction is open, or its network I/O holds DB locks the whole time).
        customer_for_email = {
            "company_name": customer.get("company_name") or cust_company_code,
            "company_code": cust_company_code,
            "full_name":    customer.get("full_name"),
            "mobile_no":    customer.get("mobile_no"),
            "city":         customer.get("city"),
            "discount":     cust_discount,
        }
        email_comments = None
        if "note" in (email_data.get("body") or "").lower() or "comment" in (email_data.get("body") or "").lower():
            email_comments = (email_data.get("body") or "")[:500]

        email_payload = {
            "order_id":     new_order_id,
            "po_num":       po_num,
            "vendor_email": vendor_email,
            "customer":     customer_for_email,
            "items":        enriched_items,   # DB-enriched copies, not raw GPT items
            "comments":     email_comments,
            "financials":   line_financials,
        }
        return new_order_id, email_payload

    except Exception as e:
        log.error(f"Error inserting into legacy tables for PO {po_num}: {e}")
        raise


def determine_branch(to_email: Optional[str], delivery_address: Optional[str]) -> str:
    to_email_lower = (to_email or "").lower()

    # 1. Primary check: Configured branch email addresses
    for hyd_email in HYDERABAD_BRANCH_EMAILS:
        if hyd_email.lower() in to_email_lower:
            return "Hyderabad"

    for blr_email in BANGLORE_BRANCH_EMAILS:
        if blr_email.lower() in to_email_lower:
            return "Bangalore"

    # 2. Fallback check: Delivery address keywords
    if delivery_address:
        addr_lower = delivery_address.lower()
        if any(kw in addr_lower for kw in ["bangalore", "bengaluru", "electronic city", "ka - 560", "karnataka"]):
            return "Bangalore"
        elif any(kw in addr_lower for kw in ["hyderabad", "secunderabad", "nacharam", "ts - 500", "telangana"]):
            return "Hyderabad"

    return "Other"


def _generate_auto_po_number(cursor, email_date):
    """Generate a unique auto PO number when the email carries no PO number.

    Format : PO/info/YYYYMMDD
    Collision: if that key already exists in pobrain_purchase_orders for this date,
               append a numeric suffix: PO/info/YYYYMMDD-2, -3 etc.

    The date used is the email own received date (IST). Falls back to
    today (IST) when the email date is unavailable.
    """
    from datetime import datetime as _dt
    date_str = (email_date or now_ist()).strftime("%Y%m%d")
    base     = f"PO/info/{date_str}"

    # Count existing auto-POs for this date to resolve collisions.
    cursor.execute(
        "SELECT COUNT(1) FROM dbo.pobrain_purchase_orders WHERE po_number LIKE ?",
        f"{base}%",
    )
    row   = cursor.fetchone()
    count = row[0] if row else 0

    if count == 0:
        return base               # first auto-PO of the day
    return f"{base}-{count + 1}" # e.g. PO/info/20260707-2


def save_parsed_data_to_db(
    email_data,
    email_db_id,
    attachment_db_id,
    extraction_job_db_id,
    extracted_items,
    correlation_id,
    branch_location=None,
):
    """
    Saves extracted records into purchase_orders, line_items, and audit_logs
    in a single transaction.
    """
    stats = {"inserted": 0, "skipped": 0, "errors": 0}
    success_list = []
    failure_list = []
    if not extracted_items:
        return stats, success_list, failure_list

    # Work that must run only AFTER the data transaction commits — so it never
    # holds DB locks. Best-effort processing-log rows (log_to_db opens its own
    # connection) and the acknowledgment email (SMTP network I/O). Flushed below
    # the `with` block; if the transaction rolls back, none of this runs.
    deferred_logs: List[Tuple[Any, ...]] = []
    deferred_emails: List[Dict[str, Any]] = []
    deferred_notification_emails: List[Dict[str, Any]] = []

    with _db_conn() as conn:
        cursor = conn.cursor()

        # GROUP items by PO number. Items with no PO number are NOT discarded --
        # they receive an auto-generated PO number in the format PO/info/YYYYMMDD
        # (using the email own received date). All no-PO items in the same email
        # are grouped together under a single auto-generated key.
        po_groups = {}
        auto_generated_po_nums = []  # track which POs were auto-named

        # 1. Collect items that already carry a real PO number.
        for item in extracted_items:
            po_num = (item.get("po_number") or "").strip()
            if _has_value(po_num):
                po_groups.setdefault(po_num, []).append(item)

        # 2. Group ALL items lacking a PO number under one auto-generated key.
        no_po_items = [
            i for i in extracted_items
            if not _has_value((i.get("po_number") or "").strip())
        ]
        if no_po_items:
            auto_po = _generate_auto_po_number(cursor, email_data.get("date"))
            auto_generated_po_nums.append(auto_po)
            po_groups[auto_po] = no_po_items
            log.info(
                f"  WARNING: {len(no_po_items)} item(s) had no PO number. "
                f"Auto-generated PO number assigned: '{auto_po}'"
            )
            deferred_logs.append((
                email_db_id, "WARN",
                f"Auto-generated PO number '{auto_po}' for {len(no_po_items)} item(s) with no PO number.",
                email_data.get("from"), email_data.get("subject"), correlation_id
            ))

        if not po_groups:
            log.info("  No extractable purchase order items found for this email.")
            return stats, success_list, failure_list

        for po_num, items in po_groups.items():
            try:
                # 1. Duplicate check
                if check_po_duplicate(cursor, po_num):
                    log.info(f"  SKIP Duplicate: PO Number '{po_num}' already exists in database.")
                    stats["skipped"] += len(items)
                    now = now_ist()
                    write_workflow_step(cursor, email_db_id, 7, 46, now, now, f"Duplicate check skipped PO: {po_num}")
                    
                    # Queue duplicate log for pobrain_processing_logs
                    deferred_logs.append((
                        email_db_id, "WARN",
                        f"Duplicate check skipped: PO Number '{po_num}' already exists in database.",
                        email_data.get("from"), email_data.get("subject"), correlation_id
                    ))

                    # Record duplicate in pobrain_failed_transactions
                    try:
                        first_item = items[0] if items else {}
                        dup_po_date = _to_date(first_item.get("po_date"))
                        if not dup_po_date and email_data.get("date"):
                            dup_po_date = email_data.get("date").strftime("%Y-%m-%d") if isinstance(email_data.get("date"), datetime) else str(email_data.get("date"))[:10]
                        dup_qty = sum(_to_decimal(i.get("quantity")) or 0.0 for i in items)
                        dup_amt = sum(_to_decimal(i.get("amount")) or 0.0 for i in items)
                        dup_prod = (first_item.get("product_name") or "DUPLICATE ORDER")[:500]

                        ft_dup_sql = """
                        INSERT INTO dbo.pobrain_failed_transactions (
                            email_id, extraction_job_id, po_number, po_date, product_name, quantity, amount,
                            email_from, email_date, error_reason, error_category_id, is_reprocessed, failed_at, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 3, 0, DATEADD(MINUTE, 330, GETUTCDATE()), DATEADD(MINUTE, 330, GETUTCDATE()))
                        """
                        cursor.execute(
                            ft_dup_sql,
                            email_db_id,
                            extraction_job_db_id,
                            po_num[:50] if po_num else "UNKNOWN",
                            dup_po_date,
                            dup_prod,
                            dup_qty if dup_qty > 0 else None,
                            dup_amt if dup_amt > 0 else None,
                            email_data.get("from")[:320] if email_data.get("from") else None,
                            email_data.get("date"),
                            f"Duplicate Order: PO Number '{po_num}' already exists in database."
                        )
                    except Exception as ft_exc:
                        log.warning(f"Failed inserting duplicate into pobrain_failed_transactions: {ft_exc}")

                    # Queue duplicate skipped notification to admin
                    deferred_notification_emails.append({
                        "po_num": po_num,
                        "email_data": email_data,
                        "is_success": False,
                        "error_code": "DUPLICATE_SKIPPED"
                    })
                    continue

                # Take first item's headers
                first = items[0]

                # Resolve PO date with email date fallback
                po_date_raw = first.get("po_date")
                po_date_str = _to_date(po_date_raw)
                if not po_date_str:
                    email_dt = email_data.get("date")
                    if email_dt:
                        if isinstance(email_dt, datetime):
                            po_date_str = email_dt.strftime("%Y-%m-%d")
                        else:
                            po_date_str = str(email_dt)[:10]
                    else:
                        po_date_str = now_ist().strftime("%Y-%m-%d")

                # Determine branch first so we can use it to lookup pricing during financial calculation
                branch = branch_location if branch_location else determine_branch(
                    email_data.get("to"), first.get("delivery_address")
                )

                # Resolve the ERP customer using the envelope sender email address directly
                from email.utils import parseaddr
                _, sender_email = parseaddr(email_data.get("from") or "")
                v_email = sender_email.strip()

                customer        = lookup_customer_by_email(cursor, v_email)
                po_company_code = customer["company_code"] if customer else None
                cust_discount   = customer["discount"] if (customer and "discount" in customer) else None

                # Compute each real line's money fields ONCE (shared with the line
                # insert below and the ERP write) so every total reconciles. Junk rows
                # (no product AND no qty AND no amount) are excluded here exactly as
                # they are from the line-item insert.
                line_fins = []
                for i in items:
                    iqty = _to_decimal(i.get("quantity"))
                    iamt = _to_decimal(i.get("amount"))
                    if not _has_value(i.get("product_name")) and not iqty and not iamt:
                        continue
                    # Resolve HSN and catalog details first
                    cat_no, resolved_hsn = resolve_product_details(cursor, i.get("cas_number"), i.get("cat_number"), i.get("product_name"))
                    # Enforce branch-specific price lookup inside financials
                    fin = compute_line_financials(cursor, i, cust_discount, resolved_catalog_no=cat_no, branch_location=branch)
                    line_fins.append((i, cat_no, resolved_hsn, fin))

                # PO-level totals:
                #   subtotal_amount      = Σ gross price
                #   total_discount_amount= Σ discount taken off
                #   total_tax_amount     = Σ GST (charged on the net price)
                #   total_amount (grand) = Σ net price + Σ GST  (= subtotal − discount + tax)
                qty_sum     = sum(item_info[3]["qty"] or 0.0 for item_info in line_fins)
                subtotal    = sum(item_info[3]["price"] or 0.0 for item_info in line_fins)
                tax_sum     = sum(item_info[3]["gst_amount"] or 0.0 for item_info in line_fins)
                total_net   = sum(item_info[3]["discount_price"] or 0.0 for item_info in line_fins)
                total_disc  = sum(item_info[3]["discount_amt"] or 0.0 for item_info in line_fins)
                grand_total = total_net + tax_sum
                total_discount_amt = total_disc if total_disc else None

                # 2. Insert into dbo.pobrain_purchase_orders (PO Master)
                po_sql = """
                INSERT INTO dbo.pobrain_purchase_orders (
                    extraction_job_id, email_id, po_number, po_date, vendor_name, vendor_email,
                    delivery_address, gst_number, company_code, total_quantity, subtotal_amount,
                    total_tax_amount, total_amount, currency_code, status_id, is_duplicate,
                    branch_location, total_discount_amount, created_at, created_by
                ) OUTPUT INSERTED.po_id VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'INR', 31, 0, ?, ?, DATEADD(MINUTE, 330, GETUTCDATE()), 'SYSTEM')
                """
                po_params = (
                    extraction_job_db_id,
                    email_db_id,
                    po_num,
                    po_date_str,
                    first.get("vendor_name")[:300]    if first.get("vendor_name")    else "Unknown Vendor",
                    v_email[:320]                     if v_email                     else None,
                    first.get("delivery_address")[:1000] if first.get("delivery_address") else None,
                    first.get("gst_number")[:20]      if first.get("gst_number")     else None,
                    po_company_code,
                    qty_sum,
                    subtotal,
                    tax_sum,
                    grand_total,
                    branch,
                    total_discount_amt
                )
                cursor.execute(po_sql, po_params)
                po_row = cursor.fetchone()
                po_id  = po_row[0] if po_row else None
                if po_id is None:
                    raise RuntimeError(
                        f"INSERT into pobrain_purchase_orders returned no ID for PO '{po_num}'"
                    )

                li_sql = """
                INSERT INTO dbo.pobrain_purchase_order_line_items (
                    po_id, line_number, product_name, cas_number, cat_number, hsn_code,
                    quantity, unit_of_measure, unit_price, amount,
                    cgst_amount, sgst_amount, igst_amount, cgst_rate, sgst_rate, igst_rate,
                    pack_size, pack_code, item_code, discount, discount_price,
                    gst_rate, gst_amount, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, DATEADD(MINUTE, 330, GETUTCDATE()))
                """
                line_no = 0
                for item, catalog_no, resolved_hsn, fin in line_fins:
                    line_no += 1
                    prod_name  = item.get("product_name")
                    pack_size = _clean_pack_size_display(item.get("pack_size"))
                    pack_code = lookup_pack_code(cursor, pack_size)
                    item_code = catalog_no[:50] if catalog_no else None
                    final_hsn = resolved_hsn if resolved_hsn else (item.get("hsn_code") or "")

                    li_params = (
                        po_id,
                        line_no,
                        prod_name[:500] if (prod_name and _has_value(prod_name)) else "Unspecified Item",
                        item.get("cas_number")[:30]  if item.get("cas_number")  else None,
                        catalog_no[:50]               if catalog_no              else None,
                        final_hsn[:20]                if final_hsn               else None,
                        fin["qty"] or 0.0,
                        item.get("unit_of_measure")[:20] if item.get("unit_of_measure") else "pcs",
                        fin["unit_price"] or 0.0,
                        fin["price"] or 0.0,
                        fin["cgst_a"], fin["sgst_a"], fin["igst_a"],
                        fin["cgst_r"], fin["sgst_r"], fin["igst_r"],
                        pack_size[:100] if pack_size else None,
                        pack_code[:50] if pack_code else None,
                        item_code,
                        int(fin["disc_pct"]) if fin["disc_pct"] is not None else None,
                        fin["discount_price"],
                        fin["gst_pct"],
                        fin["gst_amount"],
                    )
                    cursor.execute(li_sql, li_params)
                    stats["inserted"] += 1

                audit_sql = """
                INSERT INTO dbo.pobrain_audit_logs (
                    table_name, record_id, action_type, changed_by, old_values, new_values,
                    ip_address, correlation_id, changed_at
                ) VALUES ('pobrain_purchase_orders', ?, 'INSERT', 'SYSTEM', NULL, ?,
                          '127.0.0.1', ?, DATEADD(MINUTE, 330, GETUTCDATE()))
                """
                new_vals = json.dumps({
                    "po_id": po_id, "po_number": po_num,
                    "total_amount": grand_total, "items_count": len(items)
                })
                cursor.execute(audit_sql, po_id, new_vals, correlation_id)

                erp_order_id = None
                erp_success = False
                err_code = None
                
                if ENABLE_LEGACY_ERP_INSERT:
                    try:
                        if not v_email:
                            err_code = "MISSING_EMAIL"
                            raise ValueError("No vendor/buyer email address was provided or extracted.")
                        
                        customer = lookup_customer_by_email(cursor, v_email)
                        if customer is None:
                            err_code = "CUSTOMER_NOT_FOUND"
                            raise ValueError(f"Could not find PersonID for vendor email {v_email}.")
                        
                        erp_order_id, email_payload = insert_into_legacy_tables(
                            cursor,
                            po_num,
                            po_date_str,
                            v_email[:320],
                            items,
                            email_data,
                            branch_location=branch
                        )
                        if erp_order_id:
                            erp_success = True
                            cursor.execute(
                                "UPDATE dbo.pobrain_purchase_orders SET is_erp_inserted = 1, erp_order_id = ? WHERE po_id = ?",
                                erp_order_id, po_id
                            )
                            if email_payload:
                                deferred_emails.append(email_payload)
                        else:
                            err_code = "ERP_UNKNOWN_ERROR"
                            raise RuntimeError("Legacy insert failed without returning an Order ID.")
                    except Exception as erp_exc:
                        if not err_code:
                            if isinstance(erp_exc, pyodbc.Error):
                                err_code = "ERP_DB_INSERT_ERROR"
                            else:
                                err_code = "ERP_UNKNOWN_ERROR"
                        
                        log.warning(f"  ERP legacy insert failed (non-fatal for PO-Brain): {erp_exc}")
                        err_details = lookup_erp_error(cursor, err_code)
                        cursor.execute(
                            """
                            UPDATE dbo.pobrain_emails
                            SET erp_insertion_status = 'FAILED',
                                erp_error_code = ?,
                                erp_error_reason = ?,
                                erp_error_solution = ?
                            WHERE email_id = ?
                            """,
                            err_code,
                            err_details["reason"][:500],
                            err_details["solution"][:1000],
                            email_db_id
                        )
                        cursor.execute(
                            """
                            UPDATE dbo.pobrain_purchase_orders
                            SET is_erp_inserted = 0,
                                erp_error_code = ?,
                                erp_error_reason = ?,
                                erp_error_solution = ?
                            WHERE po_id = ?
                            """,
                            err_code,
                            err_details["reason"][:500],
                            err_details["solution"][:1000],
                            po_id
                        )
                        failure_list.append({
                            "po_num": po_num,
                            "subject": email_data.get("subject", "(No Subject)"),
                            "from": email_data.get("from", "Unknown"),
                            "status": "FAILED",
                            "code": err_code,
                            "reason": err_details["reason"],
                            "solution": err_details["solution"]
                        })
                        deferred_notification_emails.append({
                            "po_num": po_num,
                            "email_data": email_data,
                            "is_success": False,
                            "error_code": err_code,
                            "error_details": err_details
                        })
                        deferred_logs.append((
                            email_db_id, "ERROR",
                            f"ERP Insertion Failed for PO '{po_num}' [{err_code}]: {err_details['reason']}",
                            email_data.get("from"), email_data.get("subject"), correlation_id
                        ))
                        try:
                            # Map error category ID (2: VALIDATION_ERROR, 8: MISSING_DATA, 14: UNKNOWN_ERROR)
                            err_cat_id = 8 if err_code == "MISSING_EMAIL" else (2 if err_code == "CUSTOMER_NOT_FOUND" else 14)
                            first_prod = (first.get("product_name") or "PO Line Item")[:500] if first else "PO Line Item"
                            ft_erp_sql = """
                            INSERT INTO dbo.pobrain_failed_transactions (
                                email_id, extraction_job_id, po_number, po_date, product_name, quantity, amount,
                                email_from, email_date, error_reason, error_category_id, is_reprocessed, failed_at, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, DATEADD(MINUTE, 330, GETUTCDATE()), DATEADD(MINUTE, 330, GETUTCDATE()))
                            """
                            cursor.execute(
                                ft_erp_sql,
                                email_db_id,
                                extraction_job_db_id,
                                po_num[:50] if po_num else "UNKNOWN",
                                po_date_str,
                                first_prod,
                                qty_sum if qty_sum else None,
                                grand_total if grand_total else None,
                                v_email[:320] if v_email else (email_data.get("from")[:320] if email_data.get("from") else None),
                                email_data.get("date"),
                                f"[{err_code}] {err_details['reason']}"[:1000],
                                err_cat_id
                            )
                        except Exception as ft_exc:
                            log.warning(f"Failed inserting ERP failure into pobrain_failed_transactions: {ft_exc}")
                else:
                    err_code = "ERP_UNKNOWN_ERROR"
                    err_details = lookup_erp_error(cursor, err_code)
                    failure_list.append({
                        "po_num": po_num,
                        "subject": email_data.get("subject", "(No Subject)"),
                        "from": email_data.get("from", "Unknown"),
                        "status": "FAILED",
                        "code": err_code,
                        "reason": "ERP insertion is disabled in settings.",
                        "solution": "Enable ENABLE_LEGACY_ERP_INSERT in settings."
                    })
                    cursor.execute(
                        """
                        UPDATE dbo.pobrain_purchase_orders
                        SET is_erp_inserted = 0,
                            erp_error_code = ?,
                            erp_error_reason = ?,
                            erp_error_solution = ?
                        WHERE po_id = ?
                        """,
                        err_code,
                        "ERP insertion is disabled in settings.",
                        "Enable ENABLE_LEGACY_ERP_INSERT in settings.",
                        po_id
                    )
                    deferred_logs.append((
                        email_db_id, "WARN",
                        f"ERP insertion skipped for PO '{po_num}': ERP insertion is disabled in settings.",
                        email_data.get("from"), email_data.get("subject"), correlation_id
                    ))
                 
                if erp_success:
                    cursor.execute(
                        """
                        UPDATE dbo.pobrain_emails
                        SET erp_insertion_status = 'SUCCESS',
                            erp_error_code = NULL,
                            erp_error_reason = NULL,
                            erp_error_solution = NULL
                        WHERE email_id = ?
                        """,
                        email_db_id
                    )
                    cursor.execute(
                        """
                        UPDATE dbo.pobrain_purchase_orders
                        SET erp_error_code = NULL,
                            erp_error_reason = NULL,
                            erp_error_solution = NULL
                        WHERE po_id = ?
                        """,
                        po_id
                    )
                    success_list.append({
                        "po_num": po_num,
                        "subject": email_data.get("subject", "(No Subject)"),
                        "from": email_data.get("from", "Unknown")
                    })
                    deferred_notification_emails.append({
                        "po_num": po_num,
                        "email_data": email_data,
                        "is_success": True
                    })
                    deferred_logs.append((
                        email_db_id, "INFO",
                        f"ERP Insert Successful: Created ERP Order ID {erp_order_id} for PO '{po_num}'.",
                        email_data.get("from"), email_data.get("subject"), correlation_id
                    ))

                log.info(f"  SAVED: PO '{po_num}' with {len(items)} line item(s).")
                deferred_logs.append((
                    email_db_id, "INFO",
                    f"Saved PO {po_num} with {len(items)} line items",
                    email_data.get("from"), email_data.get("subject"), correlation_id
                ))

            except Exception as exc:
                log.error(f"  DATABASE TRANSACTION ERROR writing PO {po_num}: {exc}")
                log.debug(traceback.format_exc())
                stats["errors"] += len(items)
                raise

    # ── Post-commit flush ─────────────────────────────────────────────────────
    # The data transaction has committed and released all its locks. Only now do
    # we write the best-effort processing logs and send the acknowledgment emails,
    # so neither can ever block the tables (this was the source of the idle-in-
    # transaction lock-ups on pobrain_emails / pobrain_notifications).
    for lg in deferred_logs:
        log_to_db(*lg)
    for ep in deferred_emails:
        send_order_acknowledgment_email(**ep)
    for nep in deferred_notification_emails:
        send_erp_notification_email(**nep)

    return stats, success_list, failure_list


# ── Pipeline Failure Loggers ──────────────────────────────────────────────────

def handle_pipeline_failure(
    email_data: dict,
    email_db_id: int,
    attachment_db_id: Optional[int],
    job_db_id: Optional[int],
    error_message: str,
    stack_trace: str,
    correlation_id: str
) -> None:
    """Populates error_logs and failed_transactions tables on process failure."""
    try:
        # Use None for FK columns when email_db_id was never established (e.g. INSERT itself failed)
        safe_email_id = email_db_id if email_db_id > 0 else None

        with _db_conn() as conn:
            cursor = conn.cursor()
            
            # 1. Update emails table status to EMAIL_FAILED (4) — only if we have a valid email record
            if email_db_id > 0:
                cursor.execute(
                    "UPDATE dbo.pobrain_emails SET status_id = 4, failure_reason = ?, updated_at = DATEADD(MINUTE, 330, GETUTCDATE()) WHERE email_id = ?",
                    error_message[:1000], email_db_id
                )

            # 2. Insert into dbo.pobrain_error_logs
            err_sql = """
            INSERT INTO dbo.pobrain_error_logs (
                email_id, attachment_id, job_id, error_category_id, error_code, error_message, 
                stack_trace, failed_module, severity, retry_attempt, is_resolved, occurred_at
            ) OUTPUT INSERTED.error_id VALUES (?, ?, ?, 1, 'PIPELINE_ERROR', ?, ?, 'unified_po_extractor', 2, 0, 0, DATEADD(MINUTE, 330, GETUTCDATE()))
            """
            cursor.execute(err_sql, safe_email_id, attachment_db_id, job_db_id, error_message[:2000], stack_trace)
            error_id_row = cursor.fetchone()
            error_id = error_id_row[0] if error_id_row else None

            # 3. Insert into dbo.pobrain_failed_transactions
            ft_sql = """
            INSERT INTO dbo.pobrain_failed_transactions (
                email_id, extraction_job_id, po_number, po_date, product_name, quantity, amount, 
                email_from, email_date, error_reason, error_category_id, is_reprocessed, failed_at, created_at
            ) VALUES (?, ?, 'UNKNOWN', NULL, 'UNPARSED RAW EMAIL', NULL, NULL, ?, ?, ?, 1, 0, DATEADD(MINUTE, 330, GETUTCDATE()), DATEADD(MINUTE, 330, GETUTCDATE()))
            """
            cursor.execute(
                ft_sql, 
                safe_email_id, 
                job_db_id, 
                email_data.get("from")[:320] if email_data.get("from") else None, 
                email_data.get("date"), 
                error_message[:1000]
            )
            
            # Create failure notification
            try:
                title = f"PO Processing Failed: PIPELINE_ERROR"
                message = f"Email from {email_data.get('from')} (Subject: '{email_data.get('subject')}') failed during processing. Error: {error_message[:500]}"
                create_notifications(cursor, "FAILURE", title, message, related_error_id=error_id)
            except Exception as ne:
                log.warning(f"Error creating failure notification: {ne}")
            
            log.info("  ✗ FAILED Transaction saved in error logs and failed_transactions table.")
            log_to_db(safe_email_id, "ERROR", f"Pipeline failure logged: {error_message}", email_data.get("from"), email_data.get("subject"), correlation_id)

    except Exception as exc:
        log.warning(f"Failed writing exception state to database: {exc}")


# ═════════════════════════════════════════════════════════════════════════════
#  §7  UNIFIED PIPELINE PROCESSOR
# ═════════════════════════════════════════════════════════════════════════════

# ── TWO-TIER PO KEYWORD DETECTION ENGINE ─────────────────────────────────────
#
# TIER 1 — Direct Keywords (no context required)
#   Any single phrase from this list, found in subject OR body (case-insensitive,
#   whole-word/phrase), immediately classifies the email as a PO.
#
# TIER 2 — Context-Dependent Keywords
#   Ambiguous words (e.g. "Order", "Reference") that are only valid PO signals
#   when a qualifying context word appears within CONTEXT_WINDOW_CHARS characters
#   of the trigger keyword.
#
# Both tiers are checked in is_likely_po_email() below.
# ─────────────────────────────────────────────────────────────────────────────

# Maximum character distance (before + after trigger) within which a context
# word must appear for a Tier 2 match to count.
CONTEXT_WINDOW_CHARS: int = 300

# ── TIER 1: DIRECT KEYWORDS (no context needed) ───────────────────────────────
_PO_DIRECT_KEYWORDS: List[str] = [
    # Core PO / Purchase Order identifiers
    "PO", "PO No", "PO Number", "PO#",
    "P.O.", "P.O. No", "P.O. Number",
    "Purchase Order", "Purchase Order No", "Purchase Order Number",
    # Standalone order numbering markers
    "Order No", "Order Number", "Order ID", "Order#",
    # Customer / Buyer variants
    "Customer PO", "Customer PO Number", "Customer Purchase Order",
    "Buyer PO", "Buyer's PO", "Your PO", "Client PO",
    "Procurement Order", "Material Purchase Order", "Chemical Purchase Order",
    # Safe standalone "order" compound phrases
    "Customer Order", "Your Order",
    # Order lifecycle / status (standalone — unambiguous)
    "Order Confirmation", "Order Confirmed",
    "Order Acknowledgement", "Order Acknowledgment",
    "Order Accepted", "Order Received",
    "Order Booking", "Order Placed", "Order Placement",
    "New Order", "Repeat Order", "Bulk Order", "Trial Order",
    "Release Order", "Blanket Order", "Contract Order",
    "Material Order", "Chemical Order", "Product Order", "Supply Order",
    # Requests / Requisitions (standalone unambiguous phrases)
    "Purchase Request", "Procurement Request", "Purchase Requisition",
    # "Against" / "As Per" / "Regarding" / "Referring to" PO phrases
    "Against PO", "Against Purchase Order", "Against Your Order",
    "As Per PO", "As Per Purchase Order", "As Per Your Order",
    "Regarding PO", "Regarding Your Order",
    "Referring to PO", "Referring to Your Order",
    "With Reference to PO", "With Reference to Your Order",
    # Received / Acknowledged
    "Received PO", "PO Received", "Purchase Order Received",
    "We Received Your Order",
    "Thank You for Your Order", "Thank You for Your Purchase Order",
    "Acknowledging Your Order", "Acknowledging Your Purchase Order",
    # Processing / Details
    "Order Processing", "Processing Your Order",
    "Order Details", "Order Information",
    # Dispatch / Shipment / Invoice / Delivery action phrases
    "Dispatch Against PO", "Dispatch Against Your Order",
    "Shipment Against PO", "Shipment Against Your Order",
    "Invoice Against PO", "Invoice Against Your Order",
    "Material Booked Against PO", "Material Booked Against Your Order",
    "Delivery Against PO", "Delivery Against Your Order",
    # Action ordering phrases (common in plain-text order emails)
    "arrange the below material", "arrange the below materials", "arrange the material", "arrange the materials",
    "send the following material", "send the following materials", "send the follwing material", "send the material", "send the materials",
    "req for quote", "req for quotation", "request for quote", "request for quotation",
]

# ── TIER 2: CONTEXT-DEPENDENT KEYWORDS ────────────────────────────────────────
# { trigger_phrase: [context_words_that_validate_it] }
# A match fires only when a context word appears within CONTEXT_WINDOW_CHARS
# characters (before OR after) of the trigger phrase in the combined text.
_PO_CONTEXT_KEYWORDS: Dict[str, List[str]] = {
    "Order":             ["your order", "customer order", "purchase order",
                          "received your order", "thank you for your order",
                          "as per your order", "regarding your order",
                          "against your order", "book", "process",
                          "below order", "book and process"],
    "Order Reference":   ["customer order", "purchase order"],
    "Order Ref":         ["customer order", "purchase order"],
    "Material Request":  ["purchase", "procurement"],
    "Supply Request":    ["order", "purchase"],
    "PR Number":         ["purchase requisition"],
    "Requisition":       ["purchase requisition"],
    "Customer Reference":["purchase order", "customer order"],
    "Customer Ref":      ["purchase order"],
    "Client Reference":  ["purchase order"],
    "Reference Number":  ["purchase order", "customer order"],
    "Reference":         ["purchase order", "your order"],
    "Ref":               ["purchase order", "po"],
}

# ── KEYWORD-SPECIFIC PATTERN OVERRIDES ────────────────────────────────────────
# Some short Tier-1 keywords need a custom regex instead of the plain word-
# boundary pattern to avoid well-known false positives.
#   "PO"   → must NOT match "PO Box" (postal/mailing address in signatures).
#   "P.O." → same exclusion for the dotted variant.
# Add further overrides here if new false-positive cases are discovered.
_PO_KEYWORD_OVERRIDES: Dict[str, str] = {
    "PO":   r'\bpo\b(?!\s*box)',    # "PO Box" = mailing address, not a purchase order
    "P.O.": r'\bp\.o\.(?!\s*box)', # same for the dotted form
}


def is_likely_po_email(sender: str, subject: str, body: str, attachments: list) -> Tuple[bool, str]:
    """Enhanced multi-tier heuristic gate ensuring all official and informal order/quote emails are processed.

    Prevents skipping due to singular/plural variations (e.g. material vs materials, order vs orders),
    unofficial/formal phrasing differences, or quotation/rate inquiries.
    """
    sender_l = (sender or "").lower()

    # ── Hard blocklist: known non-PO senders ──────────────────────────────────
    for blocked in PO_SENDER_BLOCKLIST:
        if blocked in sender_l:
            return False, f"sender matches blocklist token '{blocked}'"

    # ── PDF attachment: always process ────────────────────────────────────────
    if attachments:
        return True, "has PDF attachment"

    # Build a single lowercased search corpus from subject + body
    combined: str = f"{subject or ''}\n{body or ''}".lower()

    # ── TIER 1: Direct keyword match (with singular/plural regex flexibility) ─────
    for kw in _PO_DIRECT_KEYWORDS:
        pattern = _PO_KEYWORD_OVERRIDES.get(kw)
        if not pattern:
            # Neutralize singular/plural endings automatically (e.g. material -> materials, quote -> quotes/quotations)
            escaped_kw = re.escape(kw.lower())
            if escaped_kw.endswith(r's'):
                pattern = r'\b' + escaped_kw[:-1] + r's?\b'
            else:
                pattern = r'\b' + escaped_kw + r's?\b'

        if re.search(pattern, combined, re.IGNORECASE):
            return True, f"Tier-1 direct keyword match: '{kw}'"

    # ── TIER 2: Action Intent & Informal/Official Request Patterns ───────────────
    # Catches informal/formal request phrases regardless of singular/plural
    ACTION_PATTERNS = [
        r'\b(?:please\s+)?(?:arrange|send|dispatch|provide|share|quote|supply|deliver|book|process|need|require|order|purchase)\b.*?\b(?:material|item|product|chemical|solvent|salt|goods|qty|quantity|order|quote|price|rate)s?\b',
        r'\b(?:req|request|inquiry|enquiry)\b.*?\b(?:quote|quotation|price|rate|cost)s?\b',
        r'\b(?:best\s+price|price\s+list|offer|commercial\s+terms|rate\s+card)\b',
        r'\b(?:price|rate|cost|rs\.?|inr|\$)\b.*?\bper\b\s*(?:kg|g|ltr|piece|pack|unit|nos)s?\b',
    ]
    for act_pat in ACTION_PATTERNS:
        if re.search(act_pat, combined, re.IGNORECASE):
            return True, f"Action request pattern match: '{act_pat}'"

    # ── TIER 3: Structural Order Line Item Patterns ──────────────────────────────
    # Catches quantity + unit patterns (e.g. "25 kgs @ 125", "Qty: 100 pcs")
    QUANTITY_PATTERNS = [
        r'\b(?:qty|quantity)\s*[:=]?\s*\d+',
        r'\b\d+\s*(?:kgs?|grams?|g|mg|lbs?|ltrs?|liters?|ml|pack|pcs?|pieces?|units?|nos|drums?|bags?)\b',
        r'\b\d+\s*@\s*\d+\b',
    ]
    for q_pat in QUANTITY_PATTERNS:
        if re.search(q_pat, combined, re.IGNORECASE):
            return True, f"Structural quantity line-item match: '{q_pat}'"

    # ── TIER 4: Context-dependent keyword match ───────────────────────────────
    for trigger_kw, context_words in _PO_CONTEXT_KEYWORDS.items():
        trigger_pattern = r'\b' + re.escape(trigger_kw.lower()) + r's?\b'
        for m in re.finditer(trigger_pattern, combined):
            win_start = max(0, m.start() - CONTEXT_WINDOW_CHARS)
            win_end   = min(len(combined), m.end() + CONTEXT_WINDOW_CHARS)
            window    = combined[win_start:win_end]
            for ctx in context_words:
                if ctx.lower() in window:
                    return True, (
                        f"Tier-4 context keyword match: '{trigger_kw}' "
                        f"near '{ctx}' (within {CONTEXT_WINDOW_CHARS} chars)"
                    )

    return False, "no PDF attachment and no PO/Order patterns matched"


def process_single_email_bytes(raw_bytes: bytes, uid: Optional[str], watcher: Optional[Any] = None, branch_location: Optional[str] = None) -> bool:
    """Processes one raw email block completely in the 3NF pipeline."""
    start_time = now_ist()
    correlation_id = f"CORR-{hashlib.md5(raw_bytes[:1000]).hexdigest()[:12].upper()}"

    # Parse headers and attachments
    email_data = parse_email_structure(raw_bytes)
    sender = email_data.get("from", "unknown")
    subject = email_data.get("subject", "(no subject)")
    attachments = email_data.get("attachments", [])

    # ── PO RELEVANCE PRE-FILTER ───────────────────────────────────────────────
    # Skip obvious non-PO mail BEFORE spending an OpenAI call or writing records.
    if ENABLE_PO_PREFILTER:
        is_po, reason = is_likely_po_email(sender, subject, email_data.get("body", ""), attachments)
        if not is_po:
            log.info("=" * 72)
            log.info(f"⊘ SKIPPED (pre-filter) | {reason}")
            log.info(f"  From: {sender} | Subject: '{subject}'")
            log.info("=" * 72)
            log_to_db(None, "INFO", f"Skipped non-PO email (pre-filter): {reason}", sender, subject, correlation_id)
            if watcher and uid:
                watcher.mark_skipped(uid)
            return False

    log.info("=" * 72)
    log.info(f"▶ RECEIVING EMAIL | Correlation ID: {correlation_id}")
    log.info(f"  Subject: '{subject}'")
    log.info(f"  From:    {sender}")
    log.info(f"  Date:    {email_data.get('date')}")
    log.info(f"  Attach:  {len(attachments)} PDF(s) found")
    log.info("=" * 72)

    email_db_id = 0
    attachment_db_id = None
    job_db_id = None

    try:
        # ── Duplicate guard: skip if another instance already cataloged this email ──
        # IMAP UIDs are per-MAILBOX, so the same uid number (e.g. "5") refers to
        # DIFFERENT emails in the Hyderabad vs Bangalore inboxes. Namespacing the
        # stored key by branch prevents one branch's email from being wrongly
        # skipped as a "duplicate" of the other branch's same-numbered UID.
        uid_scope = (branch_location or "default").lower()
        mail_uid = f"{uid_scope}:{uid}" if uid else f"local-hash-{hashlib.md5(raw_bytes).hexdigest()[:20]}"
        with _db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT email_id FROM dbo.pobrain_emails WHERE mail_uid = ?", mail_uid)
            existing = cursor.fetchone()
        if existing:
            log.info(f"⟳ SKIP: Email UID '{uid}' already cataloged (mail_uid={mail_uid}). Duplicate skipped.")
            if watcher and uid:
                watcher.mark_processed(uid)
            return False

        # 1. Establish Master Email Record in dbo.pobrain_emails (Status: EMAIL_PROCESSING = 2)
        with _db_conn() as conn:
            cursor = conn.cursor()
            
            body_preview = email_data.get("body", "")[:1000]

            sql_mail = """
            INSERT INTO dbo.pobrain_emails (
                mail_uid, email_from, email_to, email_subject, email_received_at, email_body_preview, 
                attachment_count, has_pdf, status_id, retry_count, max_retries, created_at, created_by
            ) OUTPUT INSERTED.email_id VALUES (?, ?, ?, ?, ?, ?, ?, ?, 2, 0, 3, DATEADD(MINUTE, 330, GETUTCDATE()), 'SYSTEM')
            """
            cursor.execute(
                sql_mail, 
                mail_uid, 
                sender[:320], 
                email_data.get("to")[:320] if email_data.get("to") else None,
                subject[:500], 
                email_data.get("date"), 
                body_preview, 
                len(attachments), 
                1 if attachments else 0
            )
            email_row = cursor.fetchone()
            email_db_id = email_row[0] if email_row else 0

            # Write intake workflow step
            write_workflow_step(cursor, email_db_id, 1, 43, start_time, now_ist(), "Email cataloged in master table")

        log_to_db(email_db_id, "INFO", "Started email ingestion pipeline.", sender, subject, correlation_id)

        # ── Pipeline Path Decision: Attachments vs Body Text ──────────────────
        
        extracted_text = ""
        source_type = ""
        is_ocr_needed = False

        if attachments:
            # Route A: Extract ALL attached PDF(s)
            source_type = "PDF_ATTACHMENT"
            now_attach = now_ist()
            extracted_text_blocks = []
            
            with tempfile.TemporaryDirectory() as tmpdir:
                for att_idx, (filename, payload) in enumerate(attachments, 1):
                    pdf_path = os.path.join(tmpdir, f"{att_idx}_{filename}")
                    with open(pdf_path, "wb") as f:
                        f.write(payload)

                    # Insert attachment metadata into dbo.pobrain_email_attachments (Status: ATTACH_PARSING = 12)
                    with _db_conn() as conn:
                        cursor = conn.cursor()
                        file_hash = hashlib.sha256(payload).hexdigest()
                        
                        sql_att = """
                        INSERT INTO dbo.pobrain_email_attachments (
                            email_id, file_name, file_type, file_size_bytes, storage_path, file_hash, 
                            status_id, ocr_required, created_at, created_by
                        ) OUTPUT INSERTED.attachment_id VALUES (?, ?, 'pdf', ?, '/storage/temp', ?, 12, 0, DATEADD(MINUTE, 330, GETUTCDATE()), 'SYSTEM')
                        """
                        cursor.execute(sql_att, email_db_id, filename[:500], len(payload), file_hash)
                        att_row = cursor.fetchone()
                        att_id = att_row[0] if att_row else None
                        if attachment_db_id is None:
                            attachment_db_id = att_id
                        
                        # Update metrics
                        write_workflow_step(cursor, email_db_id, 2, 43, now_attach, now_ist(), f"Attachment metadata saved for: {filename}")

                    log_to_db(email_db_id, "INFO", f"Saved attachment metadata for #{att_idx} ({filename}). Hash = {file_hash[:16]}...", sender, subject, correlation_id)

                    # Extract Text (Native vs OCR)
                    now_parse = now_ist()
                    att_text, is_ocr_needed = extract_text_from_pdf(pdf_path)
                    
                    with _db_conn() as conn:
                        cursor = conn.cursor()
                        if is_ocr_needed:
                            cursor.execute(
                                "UPDATE dbo.pobrain_email_attachments SET ocr_required = 1, ocr_status_id = 16, status_id = 13 WHERE attachment_id = ?",
                                att_id
                            )
                            write_workflow_step(cursor, email_db_id, 4, 43, now_parse, now_ist(), f"Tesseract OCR fallback processed for {filename}")
                        else:
                            cursor.execute("UPDATE dbo.pobrain_email_attachments SET status_id = 13 WHERE attachment_id = ?", att_id)
                            write_workflow_step(cursor, email_db_id, 3, 43, now_parse, now_ist(), f"Native PDF text extracted for {filename}")

                    if att_text and att_text.strip():
                        extracted_text_blocks.append(f"=== ATTACHMENT #{att_idx} ({filename}) ===\n{att_text.strip()}")

            extracted_text = "\n\n".join(extracted_text_blocks)

        else:
            # Route B: Extract Email body text directly
            source_type = "EMAIL_BODY_TEXT"
            extracted_text = email_data.get("body", "")
            
            log_to_db(email_db_id, "INFO", "No attachments found. Processing raw email body text.", sender, subject, correlation_id)

        if not extracted_text.strip():
            raise ValueError("No extractable textual content found in PDFs or email body.")

        # 2. Establish Job in dbo.pobrain_extraction_jobs (Status: EXTR_EXTRACTING = 22, Engine: 3 Azure/AI equivalent)
        now_job = now_ist()
        with _db_conn() as conn:
            cursor = conn.cursor()
            
            sql_job = """
            INSERT INTO dbo.pobrain_extraction_jobs (
                attachment_id, status_id, engine_id, confidence_score, validation_status_id, 
                items_extracted, raw_extraction_json, started_at, attempt_number, created_at, created_by
            ) OUTPUT INSERTED.job_id VALUES (?, 22, 3, NULL, NULL, 0, NULL, DATEADD(MINUTE, 330, GETUTCDATE()), 1, DATEADD(MINUTE, 330, GETUTCDATE()), 'SYSTEM')
            """
            cursor.execute(sql_job, attachment_db_id)
            job_row = cursor.fetchone()
            job_db_id = job_row[0] if job_row else None

        # 3. Call OpenAI GPT-4o for Extraction
        items = extract_data_via_openai(extracted_text, source_type)
        
        # Save JSON output in Job record
        with _db_conn() as conn:
            cursor = conn.cursor()
            sql_update_job = """
            UPDATE dbo.pobrain_extraction_jobs 
            SET status_id = 23, confidence_score = 95.00, items_extracted = ?, 
                raw_extraction_json = ?, completed_at = DATEADD(MINUTE, 330, GETUTCDATE()), duration_ms = ?
            WHERE job_id = ?
            """
            dur = int((now_ist() - now_job).total_seconds() * 1000)
            cursor.execute(sql_update_job, len(items), json.dumps(items), dur, job_db_id)
            
            # Workflow step for AI
            write_workflow_step(cursor, email_db_id, 5, 43, now_job, now_ist(), f"OpenAI extraction returned {len(items)} rows")

        # 4. Save normalized PO data and Line Items to DB
        now_save = now_ist()
        assert job_db_id is not None, "Extraction job ID must be established"
        stats, success_list, failure_list = save_parsed_data_to_db(email_data, email_db_id, attachment_db_id, job_db_id, items, correlation_id, branch_location)
        
        # 5. Pipeline Finalization
        with _db_conn() as conn:
            cursor = conn.cursor()
            duration_ms = int((now_ist() - start_time).total_seconds() * 1000)
            
            # Determine email status based on PO processing outcomes
            if failure_list and not success_list:
                email_status = 4  # EMAIL_FAILED
                primary_fail = failure_list[0]
                fail_reason = f"[{primary_fail.get('code', 'FAILED')}] {primary_fail.get('reason', 'Processing failed')}"[:1000]
                wf_status = 44   # WF_FAILED
                wf_remarks = f"Processing failed: {len(failure_list)} failed PO item(s)"
            else:
                email_status = 3  # EMAIL_COMPLETED
                fail_reason = None
                wf_status = 43   # WF_COMPLETED
                wf_remarks = "All PO transactions written successfully" if not failure_list else f"Completed with {len(failure_list)} failed items"

            # Write final workflow analytics
            write_workflow_step(cursor, email_db_id, 8, wf_status, now_save, now_ist(), wf_remarks)
            
            # Set Email status
            cursor.execute(
                "UPDATE dbo.pobrain_emails SET status_id = ?, failure_reason = ?, processing_started_at = ?, processing_completed_at = DATEADD(MINUTE, 330, GETUTCDATE()), processing_duration_ms = ? WHERE email_id = ?",
                email_status, fail_reason, start_time, duration_ms, email_db_id
            )

            # Create notification
            try:
                po_numbers = list(set(str(item.get("po_number")).strip() for item in items if _has_value(item.get("po_number"))))
                po_numbers_str = ", ".join(po_numbers)
                if email_status == 4:
                    title = f"PO Processing Failed: {po_numbers_str}" if po_numbers_str else "PO Processing Failed"
                    message = f"Email from {sender} (Subject: '{subject}') failed processing. Reason: {fail_reason}"
                    create_notifications(cursor, "FAILURE", title, message, related_po_number=po_numbers[0] if po_numbers else None)
                else:
                    title = f"PO Extraction Successful: {po_numbers_str}" if po_numbers_str else "PO Extraction Successful"
                    message = f"Email from {sender} (Subject: '{subject}') was successfully processed. Extracted {len(items)} line item(s) across PO(s): {po_numbers_str or 'N/A'}."
                    create_notifications(cursor, "SUCCESS", title, message, related_po_number=po_numbers[0] if po_numbers else None)
            except Exception as e:
                log.warning(f"Error creating notification: {e}")

        # Display Extraction Results summary in the console
        log.info("=" * 80)
        log.info("                          EXTRACTION RESULTS                            ")
        log.info("=" * 80)
        
        log.info("\nSuccessfully Inserted into ERP:")
        if success_list:
            for idx, s_item in enumerate(success_list, 1):
                log.info(f"  {idx}. PO Number       : {s_item['po_num']}")
                log.info(f"     Original Subject: {s_item['subject']}")
                log.info(f"     Sender Email    : {s_item['from']}")
        else:
            log.info("  (None)")
            
        log.info("\nFailed to Insert into ERP:")
        if failure_list:
            for idx, f_item in enumerate(failure_list, 1):
                log.info(f"  {idx}. PO Number           : {f_item['po_num']}")
                log.info(f"     Original Subject    : {f_item['subject']}")
                log.info(f"     Sender Email        : {f_item['from']}")
                log.info(f"     ERP Insertion Status: {f_item['status']}")
                log.info(f"     Error Code          : {f_item['code']}")
                log.info(f"     Error Reason        : {f_item['reason']}")
                log.info(f"     Solution            : {f_item['solution']}")
        else:
            log.info("  (None)")
        log.info("\n" + "=" * 80)

        log.info(f"✓ PIPELINE SUCCESS (UID={uid}) | Correlation: {correlation_id}\n")
        if failure_list:
            log_to_db(email_db_id, "WARN", f"Completed email parsing with {len(failure_list)} failed PO item(s).", sender, subject, correlation_id)
        else:
            log_to_db(email_db_id, "INFO", "Completed email parsing pipeline successfully.", sender, subject, correlation_id)
        
        if watcher and uid:
            watcher.mark_processed(uid)
        return True

    except Exception as exc:
        err_msg = str(exc)
        stack = traceback.format_exc()
        log.error(f"✗ PIPELINE FAILED (UID={uid}) | Correlation: {correlation_id} | {err_msg}")
        
        # Save structural errors into pobrain_error_logs and pobrain_failed_transactions
        handle_pipeline_failure(email_data, email_db_id, attachment_db_id, job_db_id, err_msg, stack, correlation_id)
            
        if watcher and uid:
            watcher.mark_failed(uid)
        return False


# ═════════════════════════════════════════════════════════════════════════════
#  §8  IMAP INTAKE WATCHER
# ═════════════════════════════════════════════════════════════════════════════

class ImapClientWatcher:
    def __init__(self):
        self._conn: Optional[imaplib.IMAP4_SSL] = None
        self._active_username: Optional[str] = None
        self._active_password: Optional[str] = None

    def connect(self, username: Optional[str] = None, password: Optional[str] = None) -> None:
        if username is not None:
            self._active_username = username
        if password is not None:
            self._active_password = password

        if not self._active_username or not self._active_password:
            self._active_username = IMAP_USERNAME
            self._active_password = IMAP_PASSWORD

        log.info(f"Connecting to IMAP secure mailbox: {IMAP_HOST}:{IMAP_PORT} for {self._active_username}")
        try:
            self._conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            self._conn.login(self._active_username, self._active_password)
            log.info("✓ Secure login successful.")
            self._select(IMAP_MAILBOX)
        except Exception as exc:
            log.error(f"✗ Secure login failed: {exc}")
            raise

    def _select(self, mailbox: str) -> None:
        assert self._conn is not None, "IMAP connection not established"
        self._conn.select(f'"{mailbox}"')

    def _ensure_folder(self, folder: str) -> None:
        assert self._conn is not None, "IMAP connection not established"
        status, _ = self._conn.select(folder)
        if status != "OK":
            self._conn.create(folder)
            log.info(f"Created secure archive folder: '{folder}'")
        self._select(IMAP_MAILBOX)

    def fetch_unseen_uids(self) -> Iterator[Tuple[bytes, str]]:
        try:
            self._select(IMAP_MAILBOX)
            assert self._conn is not None, "IMAP connection not established"
            status, data = self._conn.uid("search", "UNSEEN")
            if status != "OK" or not data or not data[0]:
                return
            
            uids = data[0].split()
            log.info(f"Discovered {len(uids)} unseen email(s) in inbox.")
            for uid in uids:
                uid_str = uid.decode()
                status, msg_data = self._conn.uid("fetch", uid_str, "(BODY.PEEK[])")
                if status == "OK" and msg_data and msg_data[0] is not None:
                    yield msg_data[0][1], uid_str
        except Exception as exc:
            log.warning(f"IMAP fetch drop: {exc}. Retrying reconnection...")
            self.connect()

    def mark_seen(self, uid: str) -> None:
        try:
            assert self._conn is not None
            self._conn.uid("store", uid, "+FLAGS", r"(\Seen)")
        except Exception as exc:
            log.warning(f"Could not flag seen for UID {uid}: {exc}")

    def mark_processed(self, uid: str) -> None:
        self.mark_seen(uid)
        self._move(uid, IMAP_PROCESSED_FOLDER)

    def mark_failed(self, uid: str) -> None:
        self.mark_seen(uid)
        self._move(uid, IMAP_FAILED_FOLDER)

    def mark_skipped(self, uid: str) -> None:
        self.mark_seen(uid)
        self._move(uid, IMAP_SKIPPED_FOLDER)

    def _move(self, uid: str, folder: str) -> None:
        try:
            self._ensure_folder(folder)
            assert self._conn is not None
            self._conn.uid("copy", uid, folder)
            self._conn.uid("store", uid, "+FLAGS", r"(\Deleted)")
            self._conn.expunge()
            log.debug(f"Relocated email UID {uid} → '{folder}'")
        except Exception as exc:
            log.error(f"Error relocating email UID {uid} → '{folder}': {exc}")

    def run_polling_loop(self, once: bool = False) -> None:
        log.info(f"Pipeline started successfully. Sequential branch monitoring enabled (interval: {IMAP_POLL_INTERVAL}s).")
        if once:
            log.info("Single execution mode (--once) active. Process will exit after checking all mailboxes.")
        else:
            log.info("Press Ctrl+C to terminate.")
        log.info("=" * 72)
        
        accounts = [
            {"username": HYDERABAD_IMAP_USERNAME, "password": HYDERABAD_IMAP_PASSWORD, "branch": "Hyderabad"},
            {"username": BANGLORE_IMAP_USERNAME, "password": BANGLORE_IMAP_PASSWORD, "branch": "Bangalore"}
        ]
        
        while True:
            try:
                for acc in accounts:
                    if not acc["username"] or not acc["password"]:
                        log.warning(f"Skipping IMAP configuration for {acc['branch']}: username or password not set.")
                        continue
                    
                    try:
                        self.connect(acc["username"], acc["password"])
                        for raw_bytes, uid in self.fetch_unseen_uids():
                            process_single_email_bytes(raw_bytes, uid, self, branch_location=acc["branch"])
                    except Exception as e:
                        log.error(f"Error processing mailbox {acc['username']} ({acc['branch']}): {e}")
                    finally:
                        if self._conn:
                            try:
                                self._conn.logout()
                            except Exception:
                                pass
                            self._conn = None
            except KeyboardInterrupt:
                log.info("Polling terminated by user.")
                break
            except Exception as exc:
                log.error(f"Ingestion loop error: {exc}")
                
            if once:
                log.info("Single cycle completed. Exiting.")
                break
                
            time.sleep(IMAP_POLL_INTERVAL)


# ═════════════════════════════════════════════════════════════════════════════
#  §9  CLI RUN MODES
# ═════════════════════════════════════════════════════════════════════════════

def run_single_file_test(eml_path: str) -> None:
    """Offline run mode to process a single EML file directly."""
    log.info(f"Loading single local email file: {eml_path}")
    try:
        with open(eml_path, "rb") as f:
            raw_bytes = f.read()
    except FileNotFoundError:
        log.error(f"Failed to find EML file: {eml_path}")
        sys.exit(1)

    process_single_email_bytes(raw_bytes, None, None)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="unified_po_extractor",
        description="Unified PO Extractor — Extracts from PDFs AND Email body text dynamically → 3NF pobrain_ schema.",
    )
    parser.add_argument("--file", "-f", metavar="EMAIL.eml", help="Process a single EML file offline")
    parser.add_argument("--test-db", action="store_true", help="Verify DB connection parameters and lookup tables")
    parser.add_argument("--once", action="store_true", help="Process unseen emails once and exit immediately")
    args = parser.parse_args()

    if args.test_db:
        if test_db_connection():
            print("\n  ✅ DB connection and lookup integrity verified successfully!")
        else:
            print("\n  ❌ DB Connection verification failed.")
            sys.exit(1)
    elif args.file:
        if not test_db_connection():
            log.error("Database connection failed. Exiting.")
            sys.exit(1)
        run_single_file_test(args.file)
    else:
        if not test_db_connection():
            log.error("Database connection failed. Exiting.")
            sys.exit(1)
        watcher = ImapClientWatcher()
        watcher.run_polling_loop(once=args.once)


if __name__ == "__main__":
    main()
