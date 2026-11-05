"""
=============================================================
  PURCHASE ORDER EXTRACTOR - CONTINUOUS + MULTI-PRODUCT
  Gmail + OpenAI + PDF Parsing + SQL Server
=============================================================

FEATURES:
  - Runs CONTINUOUSLY - polls Gmail every N seconds forever
  - Extracts ALL products/line items from each PDF (not just one)
  - Each product row inserted separately into DB
  - Tracks processed emails in a LOCAL FILE (processed_emails.txt)
    so already-processed emails are NEVER re-read regardless of
    whether the same sender sends again later
  - NO changes required to your existing database table
  - Press Ctrl+C to stop

INSTALL DEPENDENCIES:
---------------------
  pip install openai pdfplumber pytesseract pillow pdf2image pyodbc

Gmail App Password : Gmail -> Google Account -> Security ->
                     2-Step Verification -> App Passwords
Enable IMAP        : Gmail Settings -> Forwarding and POP/IMAP -> Enable IMAP
"""

import imaplib
import email
import os
import json
import logging
import tempfile
import re
import sys
import time
import hashlib
from email.header import decode_header
from datetime import datetime
from pathlib import Path

import pdfplumber
import pyodbc
from openai import OpenAI

try:
    import pytesseract
    from PIL import Image
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# =============================================================
# CONFIGURATION
# =============================================================
CONFIG = {
    "GMAIL_USER":         "deevan9391@gmail.com",
    "GMAIL_APP_PASSWORD": "ofwrpqoqqyigwzgy",

    "OPENAI_API_KEY": os.environ.get(
        "OPENAI_API_KEY",
        "your-openai-api-key-here"
    ),
    "OPENAI_MODEL": "gpt-4o",

    "DB_SERVER":   "198.38.84.193,1234",
    "DB_NAME":     "GG26_GagriLearning",
    "DB_USER":     "gagribde",
    "DB_PASSWORD": "J*rQ6w8M#f5D",
    "DB_TABLE":    "dbo.email_purchase_orders",

    "IMAP_FOLDER": "INBOX",
    "MAX_EMAILS":  20,   # max emails to check per cycle (newest first)

    # ---------------------------------------------------------------
    # LOCAL FILE that stores unique IDs of already-processed emails.
    # Created automatically on first run.
    # Delete this file ONLY if you want to reprocess everything.
    # ---------------------------------------------------------------
    "PROCESSED_IDS_FILE": "processed_emails.txt",

    # Seconds between polling cycles (120 = 2 minutes)
    "POLL_INTERVAL_SECONDS": 120,

    "OUTPUT_FOLDER": "extracted_pos",
    "LOG_FILE":      "po_extractor.log",

    # Windows Tesseract path - uncomment and update if needed:
    # "TESSERACT_PATH": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
}

# =============================================================
# LOGGING
# =============================================================
def setup_logger():
    logger = logging.getLogger("POExtractor")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    fh = logging.FileHandler(CONFIG["LOG_FILE"], encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger

logger = setup_logger()

# =============================================================
# PROCESSED EMAIL TRACKER  (local file - no DB change needed)
# =============================================================

def load_processed_ids():
    """Return set of already-processed email UIDs from local tracking file."""
    path = CONFIG["PROCESSED_IDS_FILE"]
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_processed_id(uid):
    """Append one UID to the local tracking file."""
    path = CONFIG["PROCESSED_IDS_FILE"]
    with open(path, "a", encoding="utf-8") as f:
        f.write(uid + "\n")


def make_email_uid(message_id, efrom, edate, esubj):
    """
    Build a stable unique ID for an email.
    Uses the Message-ID header when present.
    Falls back to an MD5 hash of sender+date+subject so that
    the same physical email is never processed twice even when
    Message-ID header is missing.
    """
    if message_id and message_id.strip():
        return message_id.strip()
    raw = "{}|{}|{}".format(efrom, edate, esubj)
    return "hash:" + hashlib.md5(raw.encode("utf-8")).hexdigest()


# =============================================================
# OPENAI SYSTEM PROMPT
# Returns a JSON ARRAY - one dict per product / line item
# =============================================================
SYSTEM_PROMPT = """You are a senior intelligent document processing AI specialising \
in Purchase Order and Tax Invoice extraction.

Your task: extract ALL products / line items from the PDF and return them \
as a JSON ARRAY. Each element in the array represents ONE product / line-item row.

STRICT RULES:
1. One JSON object per product / line item.
2. If a PDF has 20 line items return an array of 20 objects.
3. Fields shared across all rows (po_number, po_date, delivery_address, \
gst_number, cgst_number, sgst_number, igst_number, email_from, email_date) \
must be REPEATED in EVERY object.
4. Per-row fields (product_name, cas_number, cat_number, hsn_code, \
quantity, amount) must contain the value for THAT specific row only.
5. If a field is not found use null - NEVER guess or invent values.
6. All dates must be in YYYY-MM-DD format.
7. quantity and amount must be numeric only - strip currency symbols and commas.
8. Return ONLY a valid JSON array - no markdown, no ```json fences, \
no explanation text whatsoever.

EMAIL METADATA (same value in every row):
  email_from  : sender email address / name
  email_date  : date the email was sent

PDF FIELD MAPPING:
  po_number        : PO No, P.O. No, Purchase Order No, Order No, PO#
  po_date          : PO Date, Order Date, Purchase Date, Date
  gst_number       : GSTIN, GST No, GST Number, GST Registration No
  cgst_number      : CGST, Central GST
  sgst_number      : SGST, State GST
  igst_number      : IGST, Integrated GST
  product_name     : Item Description, Product Description, \
Material Description, Item Name, Description
  cas_number       : CAS No, CAS Number (chemical identifier - unique per product)
  cat_number       : Cat No, Catalog No, Catalogue No, Product Code, Item Code
  hsn_code         : HSN, HSN Code, SAC Code (may differ per row)
  quantity         : Qty, Quantity, Ordered Qty (value for THIS row)
  amount           : Line Total, Row Total, Unit Price (value for THIS row, \
NOT the grand total)
  delivery_address : Delivery Address, Shipping Address, Ship To, Deliver To

Return ONLY a JSON array in exactly this format:
[
  {
    "po_number": null,
    "po_date": null,
    "delivery_address": null,
    "gst_number": null,
    "cgst_number": null,
    "sgst_number": null,
    "igst_number": null,
    "product_name": null,
    "cas_number": null,
    "cat_number": null,
    "hsn_code": null,
    "quantity": null,
    "amount": null,
    "email_from": null,
    "email_date": null
  }
]"""


# =============================================================
# PDF TEXT EXTRACTION
# =============================================================

def extract_text_native(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text() or ""
                if page_text:
                    text += "\n--- Page {} ---\n{}".format(i, page_text)
                for table in (page.extract_tables() or []):
                    for row in table:
                        if row:
                            text += "\n" + " | ".join(
                                c.strip() if c else "" for c in row
                            )
        logger.debug("Native extraction: {} chars".format(len(text)))
    except Exception as e:
        logger.error("Native PDF extraction error: {}".format(e))
    return text.strip()


def extract_text_ocr(pdf_path):
    if not OCR_AVAILABLE:
        logger.warning("OCR unavailable. pip install pytesseract pdf2image Pillow")
        return ""
    text = ""
    try:
        if "TESSERACT_PATH" in CONFIG:
            pytesseract.pytesseract.tesseract_cmd = str(CONFIG["TESSERACT_PATH"])
        images = convert_from_path(pdf_path, dpi=300)
        for i, img in enumerate(images, 1):
            pg = pytesseract.image_to_string(img, lang="eng")
            if pg.strip():
                text += "\n--- Page {} (OCR) ---\n{}".format(i, pg)
        logger.debug("OCR extraction: {} chars".format(len(text)))
    except Exception as e:
        logger.error("OCR extraction error: {}".format(e))
    return text.strip()


def extract_pdf_text(pdf_path):
    logger.info("  Extracting text: {}".format(os.path.basename(pdf_path)))
    native = extract_text_native(pdf_path)
    if len(native) > 50:
        logger.info("  Native text used ({} chars)".format(len(native)))
        return native
    logger.info("  Native text sparse - trying OCR...")
    ocr = extract_text_ocr(pdf_path)
    if ocr:
        logger.info("  OCR text used ({} chars)".format(len(ocr)))
        return ocr
    logger.warning("  No text could be extracted from PDF.")
    return ""


# =============================================================
# OPENAI EXTRACTION
# Returns LIST of dicts (one per product/line item)
# =============================================================

def extract_via_openai(email_from, email_date, pdf_text):
    client = OpenAI(api_key=CONFIG["OPENAI_API_KEY"])

    user_msg = (
        "EMAIL METADATA\n"
        "From: {}\n"
        "Date: {}\n\n"
        "PDF TEXT:\n"
        "{}\n\n"
        "Extract ALL line items as a JSON ARRAY. "
        "Return ONLY valid JSON. No markdown. No explanation."
    ).format(email_from, email_date, pdf_text)

    logger.info("  Calling OpenAI [{}]...".format(CONFIG["OPENAI_MODEL"]))
    raw = ""
    try:
        response = client.chat.completions.create(
            model=CONFIG["OPENAI_MODEL"],
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0,
            max_tokens=4000,
        )
        raw = (response.choices[0].message.content or "").strip()
        logger.debug("OpenAI raw: {}".format(raw))

        cleaned = re.sub(r"```json|```", "", raw).strip()
        data = json.loads(cleaned)

        # Safety: if model returns a single dict wrap it in a list
        if isinstance(data, dict):
            data = [data]

        logger.info("  OpenAI returned {} product row(s)".format(len(data)))
        return data

    except json.JSONDecodeError as e:
        logger.error("  JSON parse error: {} | Raw: {}".format(e, raw))
        return []
    except Exception as e:
        logger.error("  OpenAI API error: {}".format(e))
        return []


# =============================================================
# DATABASE
# Uses your ORIGINAL table structure - no new columns needed
# =============================================================

def get_db_connection():
    drivers = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "ODBC Driver 13 for SQL Server",
        "SQL Server",
    ]
    last_error = None
    for driver in drivers:
        try:
            conn_str = (
                "DRIVER={" + driver + "};"
                "SERVER=" + CONFIG["DB_SERVER"] + ";"
                "DATABASE=" + CONFIG["DB_NAME"] + ";"
                "UID=" + CONFIG["DB_USER"] + ";"
                "PWD=" + CONFIG["DB_PASSWORD"] + ";"
                "TrustServerCertificate=yes;"
                "Encrypt=yes;"
            )
            conn = pyodbc.connect(conn_str, timeout=30)
            logger.info("  DB connected [{}]".format(driver))
            return conn
        except pyodbc.Error as e:
            last_error = e
            logger.debug("  Driver '{}' failed: {}".format(driver, e))
    raise ConnectionError("Cannot connect to SQL Server: {}".format(last_error))


def safe_date(val):
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
                "%d-%b-%Y", "%d %b %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except ValueError:
            continue
    logger.warning("  Cannot parse date '{}' - storing NULL".format(val))
    return None


def safe_decimal(val):
    if val is None:
        return None
    try:
        cleaned = re.sub(r"[^\d.]", "", str(val))
        return float(cleaned) if cleaned else None
    except Exception:
        return None


def insert_rows_into_db(rows, source_pdf):
    """Insert all product rows for one PDF. Returns count of rows inserted."""
    sql = """
    INSERT INTO dbo.email_purchase_orders (
        po_number, po_date, delivery_address,
        gst_number, cgst_number, sgst_number, igst_number,
        product_name, cas_number, cat_number, hsn_code,
        quantity, amount, email_from, email_date
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    inserted = 0
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        for row in rows:
            params = (
                row.get("po_number"),
                safe_date(row.get("po_date")),
                row.get("delivery_address"),
                row.get("gst_number"),
                row.get("cgst_number"),
                row.get("sgst_number"),
                row.get("igst_number"),
                row.get("product_name"),
                row.get("cas_number"),
                row.get("cat_number"),
                row.get("hsn_code"),
                safe_decimal(row.get("quantity")),
                safe_decimal(row.get("amount")),
                row.get("email_from"),
                safe_date(row.get("email_date")),
            )
            cursor.execute(sql, params)
            inserted += 1
        conn.commit()
        cursor.close()
        logger.info("  {} row(s) inserted for: {}".format(inserted, source_pdf))
    except Exception as e:
        logger.error("  DB insert failed for '{}': {}".format(source_pdf, e))
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        inserted = 0
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return inserted


# =============================================================
# GMAIL
# =============================================================

def decode_header_value(val):
    if not val:
        return ""
    try:
        parts = decode_header(val)
        result = ""
        for chunk, enc in parts:
            if isinstance(chunk, bytes):
                result += chunk.decode(enc or "utf-8", errors="ignore")
            else:
                result += chunk
        return result.strip()
    except Exception:
        return str(val)


def parse_email_date(msg):
    date_str = msg.get("Date", "")
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str).strftime("%Y-%m-%d")
    except Exception:
        return date_str


def fetch_emails(processed_ids):
    """
    Connect to Gmail and return list of NEW emails with PDF attachments.
    - Checks ALL emails in the folder (newest first up to MAX_EMAILS).
    - Any email whose UID is already in processed_ids is skipped.
    - Emails with no PDF attachments are also marked processed so they
      are not checked again in future cycles.
    """
    logger.info("Connecting to Gmail IMAP...")
    results = []
    mail = None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(CONFIG["GMAIL_USER"], CONFIG["GMAIL_APP_PASSWORD"])
        logger.info("Logged in as: {}".format(CONFIG["GMAIL_USER"]))

        status, _ = mail.select(CONFIG["IMAP_FOLDER"])
        if status != "OK":
            logger.error("Cannot select folder: {}".format(
                CONFIG["IMAP_FOLDER"]))
            return results

        # Search ALL mail - we manage "seen/unseen" ourselves via the file
        status, data = mail.search(None, "ALL")
        if status != "OK" or not data[0]:
            logger.info("Folder is empty.")
            return results

        ids = data[0].split()
        logger.info("Total emails in folder: {}".format(len(ids)))

        # Newest first, limited to MAX_EMAILS
        ids = list(reversed(ids))
        if CONFIG["MAX_EMAILS"]:
            ids = ids[:CONFIG["MAX_EMAILS"]]

        new_count = 0
        for eid in ids:
            try:
                # Fetch headers only to build the UID cheaply
                status, hdr_data = mail.fetch(
                    eid,
                    "(BODY[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])"
                )
                if status != "OK" or not hdr_data or not hdr_data[0]:
                    continue

                hdr_raw = hdr_data[0][1]
                if not isinstance(hdr_raw, (bytes, bytearray)):
                    continue
                hdr_msg    = email.message_from_bytes(hdr_raw)
                efrom      = decode_header_value(hdr_msg.get("From", "Unknown"))
                esubj      = decode_header_value(hdr_msg.get("Subject",
                                                              "No Subject"))
                edate      = parse_email_date(hdr_msg)
                message_id = hdr_msg.get("Message-ID", "").strip()
                uid        = make_email_uid(message_id, efrom, edate, esubj)

                if uid in processed_ids:
                    logger.debug("Skipping already-processed email: {}".format(
                        esubj))
                    continue

                new_count += 1
                logger.info("\n  New email found:")
                logger.info("  From   : {}".format(efrom))
                logger.info("  Subject: {}".format(esubj))
                logger.info("  Date   : {}".format(edate))

                # Fetch full message
                status, msg_data = mail.fetch(eid, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue

                msg_raw = msg_data[0][1]
                if not isinstance(msg_raw, (bytes, bytearray)):
                    continue
                msg = email.message_from_bytes(msg_raw)

                # Collect PDF attachments
                pdf_paths = []
                for part in msg.walk():
                    ctype    = part.get_content_type()
                    filename = decode_header_value(part.get_filename() or "")
                    is_pdf   = (
                        ctype in ("application/pdf",
                                  "application/octet-stream")
                        or filename.lower().endswith(".pdf")
                    )
                    if is_pdf and filename:
                        payload = part.get_payload(decode=True)
                        if payload:
                            tmp  = tempfile.mkdtemp()
                            safe = re.sub(r"[^\w\-_\. ]", "_", filename)
                            path = os.path.join(tmp, safe)
                            with open(path, "wb") as fh:
                                fh.write(bytes(payload))
                            pdf_paths.append(path)
                            logger.info("  Saved attachment: {}".format(
                                filename))

                if not pdf_paths:
                    # No PDFs - mark processed so we never check this again
                    logger.info("  No PDF attachments - marking processed.")
                    processed_ids.add(uid)
                    save_processed_id(uid)
                    continue

                results.append({
                    "uid":           uid,
                    "email_from":    efrom,
                    "email_subject": esubj,
                    "email_date":    edate,
                    "pdf_paths":     pdf_paths,
                })

            except Exception as e:
                logger.error("Error reading email id={}: {}".format(
                    eid.decode(), e), exc_info=True)

        if new_count == 0:
            logger.info("No new unprocessed emails found.")

    except imaplib.IMAP4.error as e:
        logger.error("IMAP error: {}".format(e))
        logger.error("Check GMAIL_USER and GMAIL_APP_PASSWORD in CONFIG.")
    except Exception as e:
        logger.error("Unexpected Gmail error: {}".format(e), exc_info=True)
    finally:
        if mail:
            try:
                mail.logout()
            except Exception:
                pass
        logger.info("Disconnected from Gmail.")

    return results


# =============================================================
# JSON BACKUP HELPER
# =============================================================

def save_json_backup(rows, email_subject, uid):
    out = Path(CONFIG["OUTPUT_FOLDER"])
    out.mkdir(parents=True, exist_ok=True)
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_subj = re.sub(r"[^\w\-_]", "_", email_subject)[:40]
    safe_uid  = re.sub(r"[^\w]", "_", uid)[:20]
    fp = out / "PO_{}_{}_{}.json".format(ts, safe_uid, safe_subj)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    logger.info("  JSON backup: {}".format(fp))


def cleanup_temp_files(paths):
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


# =============================================================
# ONE POLLING CYCLE
# =============================================================

def run_cycle(processed_ids):
    """
    Fetch new emails -> extract PDFs -> insert DB rows.
    Updates processed_ids in-place so the caller's copy stays current.
    Returns (total_inserted, total_failed).
    """
    emails = fetch_emails(processed_ids)
    if not emails:
        return 0, 0

    logger.info("\nNew emails with PDFs to process: {}".format(len(emails)))
    total_ok   = 0
    total_fail = 0

    for em in emails:
        uid   = em["uid"]
        efrom = em["email_from"]
        esubj = em["email_subject"]
        edate = em["email_date"]
        paths = em["pdf_paths"]

        logger.info("\n" + "=" * 60)
        logger.info("Email  : {}".format(esubj))
        logger.info("From   : {}".format(efrom))
        logger.info("Date   : {}".format(edate))
        logger.info("PDFs   : {}".format(len(paths)))

        for pdf_path in paths:
            fname = os.path.basename(pdf_path)
            logger.info("\n  Processing: {}".format(fname))
            try:
                # 1. Extract text from PDF
                pdf_text = extract_pdf_text(pdf_path)
                if not pdf_text:
                    logger.warning("  No text extracted - skipping PDF.")
                    total_fail += 1
                    continue

                # 2. Ask OpenAI to extract all product rows
                rows = extract_via_openai(efrom, edate, pdf_text)
                if not rows:
                    logger.error("  No data from OpenAI - skipping.")
                    total_fail += 1
                    continue

                # 3. Log extracted products
                logger.info("  Products found: {}".format(len(rows)))
                for i, row in enumerate(rows, 1):
                    logger.info(
                        "    [{:>2}] {:<40} CAS:{} CAT:{} HSN:{} "
                        "Qty:{} Amt:{}".format(
                            i,
                            str(row.get("product_name") or "N/A")[:40],
                            row.get("cas_number") or "N/A",
                            row.get("cat_number") or "N/A",
                            row.get("hsn_code")   or "N/A",
                            row.get("quantity")   or "N/A",
                            row.get("amount")     or "N/A",
                        )
                    )

                # 4. Save JSON backup
                for row in rows:
                    row["_source_pdf"]   = fname
                    row["_email_subj"]   = esubj
                    row["_processed_at"] = datetime.now().isoformat()
                save_json_backup(rows, esubj, uid)

                # 5. Insert all rows into database
                inserted = insert_rows_into_db(rows, fname)
                if inserted > 0:
                    total_ok += inserted
                else:
                    total_fail += 1

            except Exception as e:
                logger.error(
                    "  Unexpected error [{}]: {}".format(fname, e),
                    exc_info=True
                )
                total_fail += 1

        cleanup_temp_files(paths)

        # Mark email as processed after all its PDFs are handled
        processed_ids.add(uid)
        save_processed_id(uid)
        logger.info("Email marked as processed.")

    return total_ok, total_fail


# =============================================================
# CONTINUOUS LOOP
# =============================================================

def run_continuous():
    logger.info("=" * 60)
    logger.info("  PO EXTRACTOR - CONTINUOUS MODE")
    logger.info("  Poll interval : {} seconds".format(
        CONFIG["POLL_INTERVAL_SECONDS"]))
    logger.info("  Tracking file : {}".format(CONFIG["PROCESSED_IDS_FILE"]))
    logger.info("  Log file      : {}".format(CONFIG["LOG_FILE"]))
    logger.info("  Press Ctrl+C to stop.")
    logger.info("=" * 60)

    # Load IDs of emails already processed in previous runs
    processed_ids = load_processed_ids()
    logger.info("Previously processed emails loaded: {}".format(
        len(processed_ids)))

    cycle = 0
    while True:
        cycle += 1
        logger.info("\n>>> CYCLE #{} - {} <<<".format(
            cycle, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        try:
            ok, fail = run_cycle(processed_ids)
            logger.info(
                "Cycle #{} complete - DB rows inserted: {}  Failed: {}".format(
                    cycle, ok, fail))
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.error(
                "Unhandled error in cycle #{}: {}".format(cycle, e),
                exc_info=True)

        logger.info("Waiting {} seconds before next cycle...".format(
            CONFIG["POLL_INTERVAL_SECONDS"]))
        try:
            time.sleep(CONFIG["POLL_INTERVAL_SECONDS"])
        except KeyboardInterrupt:
            raise


# =============================================================
# ENTRY POINT
# =============================================================

if __name__ == "__main__":
    try:
        if "--once" in sys.argv:
            # Single-cycle mode: python po_extractor.py --once
            logger.info("Single-cycle mode (--once flag detected)")
            processed_ids = load_processed_ids()
            ok, fail = run_cycle(processed_ids)
            logger.info("Done - inserted: {}  failed: {}".format(ok, fail))
        else:
            # Default: run forever polling every POLL_INTERVAL_SECONDS
            run_continuous()
    except KeyboardInterrupt:
        logger.info("\nStopped by user (Ctrl+C). Goodbye.")
        sys.exit(0)