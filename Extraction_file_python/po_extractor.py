"""
╔══════════════════════════════════════════════════════════════════════════════╗
║      PO EXTRACTOR  v3  –  HANDLES ANY EMAIL FORMAT  –  OPENAI + MSSQL      ║
║                                                                              ║
║  Database : GG26_GagriLearning                                               ║
║  Table    : dbo.email_purchase_orders                                        ║
║  AI       : OpenAI GPT-4o                                                    ║
║                                                                              ║
║  FORMATS SUPPORTED:                                                          ║
║    ✅ Formal structured PO tables                                            ║
║    ✅ Conversational / paragraph style emails                                ║
║    ✅ Bullet point style                                                      ║
║    ✅ Mixed / partial PO data                                                ║
║    ✅ HTML emails                                                             ║
║    ✅ Multiple POs in one email                                               ║
║                                                                              ║
║  Usage:                                                                      ║
║    python po_extractor.py              → Live IMAP polling                   ║
║    python po_extractor.py --file x.eml → Test a single .eml file            ║
║    python po_extractor.py --test-db    → Test DB connection only             ║
║    python po_extractor.py --debug      → Verbose debug logging               ║
╚══════════════════════════════════════════════════════════════════════════════╝

INSTALL:
  pip install openai pyodbc beautifulsoup4 lxml tenacity colorlog
"""

import argparse
import email as email_lib
import imaplib
import json
import logging
import os
import re
import sys
import time
import traceback
from contextlib import contextmanager
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from logging.handlers import RotatingFileHandler
from typing import Iterator, List, Optional, Tuple

import pyodbc
import colorlog
from bs4 import BeautifulSoup
from openai import OpenAI, APIConnectionError, RateLimitError, APIStatusError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


# ═════════════════════════════════════════════════════════════════════════════
#  §1  CONFIGURATION
# ═════════════════════════════════════════════════════════════════════════════

OPENAI_API_KEY = os.environ.get(
    "OPENAI_API_KEY",
    "your-openai-api-key-here"
)
OPENAI_MODEL   = "gpt-4o"

IMAP_HOST             = "imap.gmail.com"
IMAP_PORT             = 993
IMAP_USE_SSL          = True
IMAP_USERNAME         = "deevan9391@gmail.com"
IMAP_PASSWORD         = "ofwrpqoqqyigwzgy"
IMAP_MAILBOX          = "INBOX"
IMAP_POLL_INTERVAL    = 60
IMAP_PROCESSED_FOLDER = "processed"
IMAP_FAILED_FOLDER    = "failed"

MSSQL_SERVER   = "198.38.84.193,1234"
MSSQL_DATABASE = "GG26_GagriLearning"
MSSQL_USERNAME = "gagribde"
MSSQL_PASSWORD = "J*rQ6w8M#f5D"
MSSQL_DRIVER   = "ODBC Driver 17 for SQL Server"

LOG_LEVEL = "INFO"


# ═════════════════════════════════════════════════════════════════════════════
#  §2  LOGGER
# ═════════════════════════════════════════════════════════════════════════════

def _setup_logger(level: str = LOG_LEVEL) -> logging.Logger:
    logger = logging.getLogger("po_extractor")
    if logger.handlers:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    console_fmt = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)-8s]%(reset)s %(message)s",
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

    os.makedirs("logs", exist_ok=True)
    fh = RotatingFileHandler(
        "logs/po_extractor.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)
    return logger


log = _setup_logger()


# ═════════════════════════════════════════════════════════════════════════════
#  §3  EMAIL PARSER
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
        text = soup.get_text(separator="\n")
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


def parse_email_bytes(raw_bytes: bytes) -> dict:
    """Parse raw RFC822 bytes → { from, date, subject, body }"""
    msg = email_lib.message_from_bytes(raw_bytes)

    sender  = _decode_hdr(msg.get("From",    "") or "")
    subject = _decode_hdr(msg.get("Subject", "") or "")

    raw_date   = msg.get("Date", "") or ""
    email_date = None
    try:
        email_date = parsedate_to_datetime(raw_date).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    plain_parts: List[str] = []
    html_parts:  List[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            ct          = part.get_content_type()
            disposition = part.get("Content-Disposition", "") or ""
            if "attachment" in disposition.lower():
                continue
            payload = _decode_part(part)
            if not payload:
                continue
            if ct == "text/plain":
                plain_parts.append(payload)
            elif ct == "text/html":
                html_parts.append(payload)
    else:
        payload = _decode_part(msg)
        if payload:
            if msg.get_content_type() == "text/plain":
                plain_parts.append(payload)
            else:
                html_parts.append(payload)

    if plain_parts:
        body = "\n\n".join(plain_parts).strip()
    elif html_parts:
        body = _html_to_text("\n".join(html_parts))
    else:
        body = ""

    log.debug(f"Parsed | From={sender} | Date={email_date} | Subject={subject}")
    log.debug(f"Body ({len(body)} chars):\n{body[:600]}")

    return {
        "from":    sender,
        "date":    email_date,
        "subject": subject,
        "body":    body,
    }


# ═════════════════════════════════════════════════════════════════════════════
#  §4  OPENAI EXTRACTOR
#  KEY FIX: Prompt now handles ANY email format — conversational, table,
#  bullet points, partial data, informal text, mixed styles.
# ═════════════════════════════════════════════════════════════════════════════


_SYSTEM_PROMPT = """You are an expert Purchase Order data extraction AI...Your job is to find and extract Purchase Order (PO) information from emails — regardless of how the email is written.

IMPORTANT: Emails can be written in ANY style:
- Formal structured tables with rows and columns
- Casual conversational paragraphs ("Please find below the PO details...")
- Bullet point lists
- Simple plain text sentences ("PO Number is PO-2026-015, Chemical: Diesel")
- Mixed formats or incomplete information
- Forwarded emails with nested content
- Replies with PO data scattered throughout

YOUR TASK:
Read the entire email carefully. Find ANY mention of Purchase Order data anywhere in the text.
Extract every piece of PO-related information you can find.
If only SOME fields are present, extract what is there and set missing fields to null.

FIELDS TO EXTRACT (extract whatever is present, even if only 1-2 fields):

- po_number    → Any value labeled: PO Number, PO No, P.O. No, Purchase Order No, Order No, PO#, PO-XXXX, or any alphanumeric that looks like a PO reference
- po_date      → Any date labeled: PO Date, Order Date, Date → format as YYYY-MM-DD
- delivery_address → Any address labeled: Delivery Address, Ship To, Deliver To, Address,Shipping Address
- gst_number   → GSTIN, GST No, GST Registration No

GST TAX RULE (VERY IMPORTANT):
Extract ONLY the GST TAX AMOUNT.
IGNORE percentage values like 5%, 9%, 18%.

Examples:
"SGST 9% ₹450" → sgst_number = 450
"CGST @ 18% 1200" → cgst_number = 1200
"IGST 5%: Rs.300" → igst_number = 300
If only percentage exists and NO amount → set value to null.

- cgst_number  → CGST tax amount ONLY (numeric value, no %, no currency symbol)
- sgst_number  → SGST tax amount ONLY (numeric value, no %, no currency symbol)
- igst_number  → IGST tax amount ONLY (numeric value, no %, no currency symbol)

- product_name → Chemical Name, Product, Item, Material, Description, Product Description, Item Description
- cas_number   → CAS No, CAS Number, CAS# — format like 68334-30-5
- cat_number   → Cat No, Catalog No, Item Code, Product Code, SKU
- hsn_code     → HSN, HSN Code, SAC Code
- quantity     → Qty, Quantity, Amount Ordered — numeric value only (no units)
- amount       → Price, Total, Line Total, Cost, Order Value, Unit Price — numeric only (no currency symbols)
- email_from   → The sender's email address from the "From" metadata
- email_date   → The email's sent date from metadata → format as YYYY-MM-DD

CRITICAL RULES:
1. Extract data from ANY format — do not require structured tables
2. ONE JSON object per product/item line
3. If multiple POs exist, create separate objects for each
4. If multiple items exist under one PO, create one object per item (repeat PO-level fields)
5. If a field is NOT found anywhere in the email, set it to null
6. NEVER invent or guess data that is not in the email
7. quantity → number only (50, not "50 kg" or "50 liters")
8. amount → number only (12500.00, not "INR 12,500" or "$500")
9. GST fields → numeric only (450, not "₹450" or "9%")
10. po_date and email_date → YYYY-MM-DD format only
11. Return ONLY a valid JSON array — no explanation, no markdown, no code fences

EXAMPLES OF WHAT YOU MUST EXTRACT:

Example 1 — Conversational email:
"Please find the required details below for Diesel:
Purchase Order (PO) Number: PO-2026-015
Chemical Name: Diesel Fuel (Automotive Diesel Oil)
CAS Number: 68334-30-5"
→ Extract: po_number="PO-2026-015", product_name="Diesel Fuel (Automotive Diesel Oil)", cas_number="68334-30-5"

Example 2 — Informal:
"Hi, sending PO-123 for 50 units of Acetone at Rs.500 each."
→ Extract: po_number="PO-123", product_name="Acetone", quantity=50, amount=500

Example 3 — Table format:
"| Item | Sodium Chloride | CAS | 7647-14-5 | Qty | 100 |"
→ Extract: product_name="Sodium Chloride", cas_number="7647-14-5", quantity=100

OUTPUT FORMAT — one object per line item:
[
  {
    "po_number": "PO-2026-015",
    "po_date": null,
    "delivery_address": null,
    "gst_number": null,
    "cgst_number": null,
    "sgst_number": null,
    "igst_number": null,
    "product_name": "Diesel Fuel (Automotive Diesel Oil)",
    "cas_number": "68334-30-5",
    "cat_number": null,
    "hsn_code": null,
    "quantity": null,
    "amount": null,
    "email_from": "sender@example.com",
    "email_date": "2026-02-24"
  }
]

Return ONLY the JSON array. Nothing else.
"""

def _build_prompt(email_data: dict) -> str:
    body = email_data.get("body", "")
    subject = email_data.get("subject", "")

    return (
        f"EMAIL METADATA:\n"
        f"From: {email_data.get('from', '')}\n"
        f"Date: {email_data.get('date', '')}\n"
        f"Subject: {subject}\n\n"
        f"EMAIL BODY:\n"
        f"{body}\n\n"
        f"---\n"
        f"TASK: Extract ALL Purchase Order information from this email.\n"
        f"The email may be written in any style (formal, conversational, bullet points, etc).\n"
        f"Find any mention of PO number, product/chemical name, CAS number, quantity, amount, or any other PO-related field.\n"
        f"Even if only 1 or 2 fields are present, still create a JSON object with those fields populated and the rest as null.\n"
        f"Return ONLY a valid JSON array."
    )


def _clean_json_response(raw: str) -> str:
    """Strip markdown and extract just the JSON array."""
    raw = raw.strip()
    # Remove ```json ... ``` fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```\s*$", "", raw)
    raw = raw.strip()
    # Extract array boundaries
    start = raw.find("[")
    end   = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        return raw[start:end + 1].strip()
    return raw


def _normalize_items(items: list, email_data: dict) -> List[dict]:
    """
    Validate items, fill missing keys with None,
    coerce numerics, backfill email metadata.
    """
    required_keys = [
        "po_number", "po_date", "delivery_address",
        "gst_number", "cgst_number", "sgst_number", "igst_number",
        "product_name", "cas_number", "cat_number", "hsn_code",
        "quantity", "amount", "email_from", "email_date",
    ]

    meta_from      = email_data.get("from", "") or ""
    meta_date      = email_data.get("date", "") or ""
    meta_date_only = meta_date[:10] if len(meta_date) >= 10 else meta_date

    result = []
    for item in items:
        if not isinstance(item, dict):
            log.warning(f"Non-dict item skipped: {item}")
            continue

        clean = {}
        for k in required_keys:
            val = item.get(k, None)

            # Normalize null-like strings
            if isinstance(val, str) and val.strip().lower() in (
                "null", "none", "n/a", "na", "not available",
                "not found", "unknown", "", "-"
            ):
                val = None

            # Backfill email metadata from parsed headers
            if k == "email_from" and not val:
                val = meta_from or None
            if k == "email_date" and not val:
                val = meta_date_only or None

            # Coerce numeric fields
            if k in ("quantity", "amount") and val is not None:
                try:
                    val = float(
                        str(val)
                        .replace(",", "")
                        .replace("₹", "").replace("$", "")
                        .replace("£", "").replace("€", "")
                        .replace("INR", "").replace("USD", "")
                        .replace("Rs", "").replace("rs", "")
                        .strip()
                    )
                except (ValueError, TypeError):
                    log.warning(f"Cannot convert {k}='{val}' to float → None")
                    val = None

            clean[k] = val

        result.append(clean)
        log.debug(
            f"Item: PO={clean.get('po_number')} | "
            f"Product={clean.get('product_name')} | "
            f"CAS={clean.get('cas_number')}"
        )

    return result


@retry(
    retry=retry_if_exception_type((APIConnectionError, RateLimitError)),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _call_openai(client: OpenAI, prompt: str) -> str:
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
    )
    content = response.choices[0].message.content or ""
    log.debug(f"OpenAI raw response:\n{content}")
    return content


def extract_po_from_email(email_data: dict) -> List[dict]:
    """Extract PO line items from any style of email via OpenAI."""
    client  = OpenAI(api_key=OPENAI_API_KEY)
    prompt  = _build_prompt(email_data)
    subject = email_data.get("subject", "(no subject)")
    body    = email_data.get("body", "")

    log.info(f"  Sending to OpenAI ({OPENAI_MODEL})...")
    log.debug(f"  Body being sent ({len(body)} chars):\n{body[:800]}")

    try:
        raw = _call_openai(client, prompt)
    except (APIConnectionError, RateLimitError) as exc:
        log.error(f"  OpenAI connection/rate error: {exc}")
        raise
    except APIStatusError as exc:
        log.error(f"  OpenAI error {exc.status_code}: {exc.message}")
        raise

    cleaned = _clean_json_response(raw)
    log.debug(f"  Cleaned JSON:\n{cleaned}")

    if not cleaned or cleaned in ("[]", "[ ]"):
        log.warning(f"  OpenAI returned [] for: '{subject}'")
        log.warning(f"  Email body that was sent:\n  {body[:400]}")
        return []

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.error(f"  JSON parse FAILED: {exc}")
        log.error(f"  Raw OpenAI output:\n{raw}")
        raise ValueError(f"Invalid JSON from OpenAI: {exc}") from exc

    if isinstance(parsed, dict):
        parsed = [parsed]
    elif not isinstance(parsed, list):
        log.error(f"  Unexpected OpenAI return type: {type(parsed)}")
        return []

    items = _normalize_items(parsed, email_data)
    log.info(f"  ✓ {len(items)} PO line item(s) extracted")
    return items


# ═════════════════════════════════════════════════════════════════════════════
#  §5  DATABASE
# ═════════════════════════════════════════════════════════════════════════════

def _conn_str() -> str:
    # MSSQL_SERVER already contains port as "host,port" — do NOT append extra port
    return (
        f"DRIVER={{{MSSQL_DRIVER}}};"
        f"SERVER={MSSQL_SERVER};"
        f"DATABASE={MSSQL_DATABASE};"
        f"UID={MSSQL_USERNAME};"
        f"PWD={MSSQL_PASSWORD};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=yes;"
    )


_INSERT_SQL = """
INSERT INTO dbo.email_purchase_orders (
    po_number,
    po_date,
    delivery_address,
    gst_number,
    cgst_number,
    sgst_number,
    igst_number,
    product_name,
    cas_number,
    cat_number,
    hsn_code,
    quantity,
    amount,
    email_from,
    email_date
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_DUP_WITH_PO = """
SELECT COUNT(1) FROM dbo.email_purchase_orders
WHERE po_number    = ?
  AND product_name = ?
  AND email_from   = ?
  AND CAST(email_date AS DATE) = CAST(? AS DATE)
"""

_DUP_NULL_PO = """
SELECT COUNT(1) FROM dbo.email_purchase_orders
WHERE po_number    IS NULL
  AND product_name = ?
  AND email_from   = ?
  AND CAST(email_date AS DATE) = CAST(? AS DATE)
"""


@contextmanager
def _db_conn():
    conn = pyodbc.connect(_conn_str(), timeout=30)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_db_connection() -> bool:
    try:
        with _db_conn() as conn:
            cursor = conn.execute("SELECT COUNT(1) FROM dbo.email_purchase_orders")
            count = cursor.fetchone()[0]
        log.info(f"✓ DB connected — dbo.email_purchase_orders has {count} row(s).")
        return True
    except pyodbc.Error as exc:
        log.error(f"✗ DB FAILED: {exc}")
        return False


def _is_duplicate(conn, item: dict) -> bool:
    po  = _s(item.get("po_number"))
    prd = _s(item.get("product_name"))
    frm = _s(item.get("email_from"))
    dt  = _dt(item.get("email_date"))

    if not prd and not frm:
        return False
    try:
        if po is None:
            cur = conn.execute(_DUP_NULL_PO, prd, frm, dt)
        else:
            cur = conn.execute(_DUP_WITH_PO, po, prd, frm, dt)
        row = cur.fetchone()
        return bool(row and row[0] > 0)
    except pyodbc.Error as exc:
        log.warning(f"  Duplicate check error (inserting anyway): {exc}")
        return False


def insert_items(items: List[dict]) -> dict:
    """Insert items into dbo.email_purchase_orders. Returns stats dict."""
    stats = {"inserted": 0, "skipped": 0, "errors": 0}
    if not items:
        return stats

    with _db_conn() as conn:
        for item in items:
            po_val  = item.get("po_number",   "N/A")
            prd_val = item.get("product_name", "N/A")
            try:
                if _is_duplicate(conn, item):
                    log.info(f"  ⟳ SKIP duplicate: PO={po_val} | Product={prd_val}")
                    stats["skipped"] += 1
                    continue

                conn.execute(
                    _INSERT_SQL,
                    _s(item.get("po_number")),
                    _d(item.get("po_date")),
                    _s(item.get("delivery_address")),
                    _s(item.get("gst_number")),
                    _s(item.get("cgst_number")),
                    _s(item.get("sgst_number")),
                    _s(item.get("igst_number")),
                    _s(item.get("product_name")),
                    _s(item.get("cas_number")),
                    _s(item.get("cat_number")),
                    _s(item.get("hsn_code")),
                    _n(item.get("quantity")),
                    _n(item.get("amount")),
                    _s(item.get("email_from")),
                    _dt(item.get("email_date")),
                )
                log.info(
                    f"  ✓ INSERTED: PO={po_val} | Product={prd_val} | "
                    f"CAS={item.get('cas_number')} | Qty={item.get('quantity')} | "
                    f"Amount={item.get('amount')}"
                )
                stats["inserted"] += 1

            except pyodbc.Error as exc:
                log.error(f"  ✗ DB ERROR: PO={po_val} | Product={prd_val} | {exc}")
                stats["errors"] += 1

    return stats


# ── Type helpers ───────────────────────────────────────────────────────────────

def _s(val) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return None if s.lower() in ("null", "none", "n/a", "na", "") else s


def _d(val) -> Optional[str]:
    """Convert any date format → YYYY-MM-DD string."""
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in ("null", "none", ""):
        return None
    # YYYY-MM-DD already
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    # dd/mm/yyyy or dd-mm-yyyy (numeric)
    m = re.match(r"^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})$", s)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    # dd-Mon-yyyy  e.g. 24-Feb-2025
    m = re.match(r"^(\d{1,2})[/\-\s](\w{3,9})[/\-\s](\d{4})$", s, re.IGNORECASE)
    if m:
        months = {
            "jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06",
            "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12",
        }
        mon = months.get(m.group(2).lower()[:3])
        if mon:
            return f"{m.group(3)}-{mon}-{m.group(1).zfill(2)}"
    log.warning(f"  Cannot parse date '{s}' — sending as-is")
    return s


def _dt(val) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return None if s.lower() in ("null", "none", "") else s


def _n(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = (
        str(val)
        .replace(",", "").replace("₹", "").replace("$", "")
        .replace("£", "").replace("€", "").replace("INR", "")
        .replace("USD", "").replace("Rs.", "").replace("Rs", "")
        .strip()
    )
    if not cleaned or cleaned.lower() in ("null", "none", "n/a"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


# ═════════════════════════════════════════════════════════════════════════════
#  §6  IMAP WATCHER
# ═════════════════════════════════════════════════════════════════════════════

class ImapWatcher:

    def __init__(self):
        self._conn: Optional[imaplib.IMAP4_SSL | imaplib.IMAP4] = None

    def connect(self) -> None:
        log.info(f"Connecting to IMAP {IMAP_HOST}:{IMAP_PORT} as {IMAP_USERNAME}")
        try:
            if IMAP_USE_SSL:
                self._conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            else:
                self._conn = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
            self._conn.login(IMAP_USERNAME, IMAP_PASSWORD)
            log.info("✓ IMAP login successful.")
            self._select(IMAP_MAILBOX)
        except imaplib.IMAP4.error as exc:
            log.error(f"✗ IMAP login failed: {exc}")
            raise

    def disconnect(self) -> None:
        if self._conn:
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None
        log.info("IMAP disconnected.")

    def _select(self, mailbox: str) -> None:
        status, data = self._conn.select(f'"{mailbox}"')
        if status != "OK":
            status, data = self._conn.select(mailbox)
            if status != "OK":
                raise ConnectionError(f"Cannot select mailbox '{mailbox}': {data}")

    def _ensure_folder(self, folder: str) -> None:
        status, _ = self._conn.select(folder)
        if status != "OK":
            self._conn.create(folder)
            log.info(f"Created IMAP folder: '{folder}'")
        self._select(IMAP_MAILBOX)

    def fetch_unseen(self) -> Iterator[Tuple[bytes, str]]:
        """Fetch UNSEEN emails using PEEK (does not auto-mark as read)."""
        try:
            self._select(IMAP_MAILBOX)
            status, data = self._conn.uid("search", None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                log.debug("No unseen emails.")
                return

            uids = data[0].split()
            log.info(f"Found {len(uids)} unseen email(s).")

            for uid in uids:
                uid_str = uid.decode()
                try:
                    status, msg_data = self._conn.uid("fetch", uid_str, "(BODY.PEEK[])")
                    if status != "OK" or not msg_data or msg_data[0] is None:
                        log.warning(f"Could not fetch UID {uid_str}.")
                        continue
                    log.debug(f"Fetched UID={uid_str} ({len(msg_data[0][1])} bytes)")
                    yield msg_data[0][1], uid_str
                except Exception as exc:
                    log.error(f"Fetch error UID {uid_str}: {exc}")

        except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError) as exc:
            log.warning(f"IMAP dropped ({exc}). Reconnecting...")
            self.connect()

    def mark_seen(self, uid: str) -> None:
        try:
            self._conn.uid("store", uid, "+FLAGS", r"(\Seen)")
        except Exception as exc:
            log.warning(f"Could not mark UID {uid} as seen: {exc}")

    def mark_processed(self, uid: str) -> None:
        self.mark_seen(uid)
        self._move(uid, IMAP_PROCESSED_FOLDER)

    def mark_failed(self, uid: str) -> None:
        self.mark_seen(uid)
        self._move(uid, IMAP_FAILED_FOLDER)

    def _move(self, uid: str, folder: str) -> None:
        try:
            self._ensure_folder(folder)
            self._conn.uid("copy", uid, folder)
            self._conn.uid("store", uid, "+FLAGS", r"(\Deleted)")
            self._conn.expunge()
            log.debug(f"Moved UID {uid} → '{folder}'")
        except Exception as exc:
            log.error(f"Move error UID {uid} → '{folder}': {exc}")

    def poll_forever(self, callback) -> None:
        self.connect()
        log.info(f"Polling '{IMAP_MAILBOX}' every {IMAP_POLL_INTERVAL}s...")
        while True:
            try:
                for raw_bytes, uid in self.fetch_unseen():
                    callback(raw_bytes, uid)
            except KeyboardInterrupt:
                log.info("Ctrl+C — stopping.")
                break
            except Exception as exc:
                log.error(f"Poll error: {exc}")
                log.debug(traceback.format_exc())
            time.sleep(IMAP_POLL_INTERVAL)
        self.disconnect()


# ═════════════════════════════════════════════════════════════════════════════
#  §7  PIPELINE
# ═════════════════════════════════════════════════════════════════════════════

def process_email(
    raw_bytes: bytes,
    uid: Optional[str],
    watcher: Optional[ImapWatcher],
) -> bool:
    """parse → extract → insert → move. Returns True on success."""
    try:
        email_data = parse_email_bytes(raw_bytes)
        subject    = email_data.get("subject", "(no subject)")
        sender     = email_data.get("from",    "unknown")

        log.info("─" * 60)
        log.info(f"▶ EMAIL  : {subject}")
        log.info(f"  FROM   : {sender}")
        log.info(f"  DATE   : {email_data.get('date', '')}")
        log.info("─" * 60)

        items = extract_po_from_email(email_data)

        if not items:
            log.warning("  No PO data extracted — check email body above in DEBUG mode.")
            if watcher and uid:
                watcher.mark_processed(uid)
            return True

        log.info(f"  Inserting {len(items)} item(s) into DB...")
        stats = insert_items(items)
        log.info(
            f"  RESULT: inserted={stats['inserted']} | "
            f"skipped={stats['skipped']} | errors={stats['errors']}"
        )

        if watcher and uid:
            watcher.mark_processed(uid)
        return True

    except Exception as exc:
        log.error(f"  ✗ PIPELINE FAILED (UID={uid}): {exc}")
        log.debug(traceback.format_exc())
        if watcher and uid:
            watcher.mark_failed(uid)
        return False


# ═════════════════════════════════════════════════════════════════════════════
#  §8  RUN MODES
# ═════════════════════════════════════════════════════════════════════════════

def run_imap_loop() -> None:
    log.info("=" * 60)
    log.info("  PO EXTRACTOR v3 — IMAP Polling Mode")
    log.info("=" * 60)
    if not test_db_connection():
        log.error("DB connection failed. Exiting.")
        sys.exit(1)

    watcher = ImapWatcher()

    def handle(raw_bytes: bytes, uid: str):
        process_email(raw_bytes, uid, watcher)

    watcher.poll_forever(handle)


def run_file_mode(path: str) -> None:
    log.info("=" * 60)
    log.info(f"  PO EXTRACTOR v3 — File Test Mode: {path}")
    log.info("=" * 60)

    try:
        with open(path, "rb") as f:
            raw_bytes = f.read()
    except FileNotFoundError:
        log.error(f"File not found: '{path}'")
        sys.exit(1)

    email_data = parse_email_bytes(raw_bytes)
    items      = extract_po_from_email(email_data)

    sep = "═" * 72
    print(f"\n{sep}")
    print(f"  Subject : {email_data.get('subject', '')}")
    print(f"  From    : {email_data.get('from', '')}")
    print(f"  Date    : {email_data.get('date', '')}")
    print(f"  Items   : {len(items)} PO line item(s) extracted")
    print(sep)
    if items:
        print(json.dumps(items, indent=2, ensure_ascii=False))
    else:
        print("  [No PO data extracted]")
        print(f"\n  Email body that was processed:\n  {email_data.get('body','')[:500]}")
    print(sep)

    if not items:
        print("\n  Tip: Run with --debug to see exactly what was sent to OpenAI.")
        return

    answer = input(
        f"\n  {len(items)} item(s) ready. "
        f"Insert into dbo.email_purchase_orders? [y/N]: "
    ).strip().lower()

    if answer == "y":
        if not test_db_connection():
            log.error("DB connection failed.")
            sys.exit(1)
        stats = insert_items(items)
        print(
            f"\n  ✅ Done → inserted={stats['inserted']} | "
            f"skipped={stats['skipped']} | errors={stats['errors']}"
        )
    else:
        print("  DB insert skipped.")


def run_db_test() -> None:
    print(f"\n  Testing: {MSSQL_DATABASE} at {MSSQL_SERVER}")
    if test_db_connection():
        print("  ✅ Connection OK")
    else:
        print("  ❌ Connection FAILED")
        sys.exit(1)


# ═════════════════════════════════════════════════════════════════════════════
#  §9  ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="po_extractor",
        description="PO Extractor v3 — handles ANY email format → dbo.email_purchase_orders",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python po_extractor.py                   # Live IMAP polling
  python po_extractor.py --file po.eml     # Test .eml file
  python po_extractor.py --test-db         # Test DB only
  python po_extractor.py --debug           # Verbose output
  python po_extractor.py --debug --file x.eml
        """,
    )
    parser.add_argument("--file", "-f", metavar="EMAIL.eml",
                        help="Process a single .eml file")
    parser.add_argument("--test-db", action="store_true",
                        help="Test DB connection and exit")
    parser.add_argument("--debug", action="store_true",
                        help="Enable DEBUG logging")
    args = parser.parse_args()

    if args.debug:
        _setup_logger("DEBUG")
        log.debug("DEBUG mode ON")

    if args.test_db:
        run_db_test()
    elif args.file:
        run_file_mode(args.file)
    else:
        run_imap_loop()


if __name__ == "__main__":
    main()
