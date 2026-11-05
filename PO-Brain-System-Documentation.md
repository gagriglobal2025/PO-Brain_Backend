# PO-Brain — Complete System Documentation

_Last updated: 2026-06-09_

PO-Brain is an AI-powered Purchase Order (PO) extraction and monitoring system. It polls a
Gmail inbox, extracts structured PO data from email bodies and PDF attachments using OpenAI
GPT-4o, stores it in a normalized SQL Server schema, and surfaces it through a monitoring
dashboard with a .NET API in between.

The repository has **four** independent parts:

| Part | Tech | Folder | Role | Status |
|---|---|---|---|---|
| Extraction pipeline | Python 3.8+, OpenAI GPT-4o, pyodbc | `Extraction_file/` | Core engine — reads mail, extracts, writes DB | ✅ Working / production |
| Database | SQL Server (`hyma_testdb`) | `Database/` | Normalized `pobrain_*` schema (18 tables) | ✅ Built & seeded |
| Backend API | .NET 8 Web API, EF Core 8, Serilog, SignalR | `Backend/` | Serves dashboard data, auth, exports, notifications | 🔄 In progress (most endpoints done) |
| Frontend | React + TypeScript + Vite + shadcn/ui | `Web/PO-Brain/` | Dashboard UI | 🔄 UI built, **not yet bound to API** |

---

## 1. What each piece uses and does

### 1.1 Python Extraction Pipeline (`Extraction_file/`)

The core engine. Three scripts exist; only one is current:

| Script | Version | Target schema | Dedup method | Use |
|---|---|---|---|---|
| `unified_po_extractor.py` | **current / production** | normalized `dbo.pobrain_*` | IMAP flags + DB PO-number check | The one to run |
| `po_extractor.py` | v3 (legacy) | flat `dbo.email_purchase_orders` | IMAP folders + DB check | Older |
| `index.py` | v1 (legacy) | flat `dbo.email_purchase_orders` | local `processed_emails.txt` | Oldest, PDF-focused |

**Tech used and what for:**

| Tech | Purpose |
|---|---|
| `imaplib` | Connect to Gmail over IMAP SSL (port 993), fetch UNSEEN emails |
| `email` + `BeautifulSoup` (`lxml`) | Parse RFC822 emails — plain text and HTML-to-text |
| `pdfplumber` | Native PDF text extraction |
| `pytesseract` + `pdf2image` + `Pillow` | OCR fallback for scanned/image PDFs (optional, needs Tesseract) |
| OpenAI **GPT-4o** (temp 0) | Extract structured PO fields → returns a JSON **array**, one object per line item |
| `pyodbc` (ODBC Driver 17) | Insert into SQL Server |
| `logging` / `colorlog` | Console + rotating file logs, plus writes structured logs to DB |
| `tenacity` | Retry OpenAI calls with exponential backoff |

**Run modes:**
```bash
python unified_po_extractor.py            # continuous polling (forever, ~120s)
python unified_po_extractor.py --once     # single cycle then exit
python unified_po_extractor.py --file x.eml  # test one .eml file
python unified_po_extractor.py --test-db  # verify DB connectivity
python unified_po_extractor.py --debug    # verbose
```

**Important note on credentials:** all credentials (Gmail, OpenAI key, DB) are **hardcoded** in a
`CONFIG` dict at the top of each script. This is a known issue flagged in the PRD — moving to
environment variables is a planned (HIGH priority) improvement.

### 1.2 Database (`Database/`)

SQL Server database **`hyma_testdb`** on `3.109.43.10:8016`. Scripts run in order:

| Script | Purpose |
|---|---|
| `01_create_tables.sql` | All 18 `dbo.pobrain_*` tables |
| `02_foreign_keys.sql` | FK constraints |
| `03_indexes.sql` | Performance indexes |
| `04_seed_data.sql` | Lookup/reference seed data |
| `05_views_dashboard.sql` | Dashboard views |
| `06_sample_data.sql` | Sample rows for dev |
| `07_migration_add_auth_tables.sql` | `pobrain_users`, `pobrain_password_resets` |
| `07_add_notifications_table.sql` | `pobrain_notifications` (added during API work) |
| `08_migration_add_otp_password_reset.sql` | OTP password reset support |
| `09_migration_utc_to_ist.sql` | Converts all `pobrain_*` default constraints from UTC to IST (+5:30) |

> ⚠️ There are **two** files numbered `07_` (`07_migration_add_auth_tables.sql` and
> `07_add_notifications_table.sql`). Harmless but worth renumbering one to `09_` to avoid
> confusion about execution order.

### 1.3 Backend API (`Backend/`)

ASP.NET Core 8 Web API. Uses EF Core 8 (SQL Server), Serilog (console + rolling file
`logs/pobrain-.log`, 30-day retention), SignalR for real-time streaming, JWT auth, Swagger.

- **Connection target:** `hyma_testdb` on `3.109.43.10,8016` (matches the Python pipeline's DB).
- **CORS allowed origins:** `localhost:3000`, `localhost:5173`, `localhost:8080` — **the deployed
  frontend origin (`hymasynthesis.com`) is NOT in this list yet.**
- **JWT:** 480-minute expiry; accepts token with or without `Bearer ` prefix; SignalR token via
  `access_token` query string.
- **SMTP:** Gmail SMTP configured for OTP / password-reset emails.

### 1.4 Frontend (`Web/PO-Brain/`)

React + TypeScript + Vite, served under base path `/Pobrain/`, dev server on port **8080**.
Uses shadcn/ui components, React Router with `AdminLayout` shell, TanStack Query wired up but
**not yet used**.

> ⚠️ **The frontend currently uses hardcoded mock data on every page.** There is no
> `services/` or `api/` layer, and no `fetch`/`axios` calls anywhere in `src/`. It is **not
> connected to the backend API**. This is the single biggest remaining integration gap.

---

## 2. Data flow — what gets inserted into which table

```
Gmail IMAP (UNSEEN)
  → PO RELEVANCE PRE-FILTER  ── not a PO? → log + move to 'skipped' (no GPT call, no DB record)
  → parse email body (plain + HTML)
  → if PDF: pdfplumber (native) → pytesseract OCR (fallback)
  → OpenAI GPT-4o → JSON array (one object per line item)
  → VALIDATION GATE  ── no real PO number? → skip (never fabricate a placeholder PO)
  → SQL Server inserts (normalized pobrain_* schema)
  → move email to 'processed' or 'failed' IMAP folder
```

> **Two safeguards now protect this flow** (added 2026-06-09) — a relevance pre-filter before
> the GPT call and a validation gate before DB insert. See §2.6.

### 2.1 Insert sequence performed by `unified_po_extractor.py`

| Step | Table | What is written |
|---|---|---|
| 1 | `pobrain_emails` | Master email record: `mail_uid`, from/to, subject, received_at, body preview, attachment count, `has_pdf`, status (`EMAIL_PROCESSING=2`) |
| 2 | `pobrain_email_attachments` | Per-PDF metadata: file name/type/size, OCR flag + status, status (`ATTACH_PARSING=12` → `13`) |
| 3 | `pobrain_extraction_jobs` | One job per attachment/email: status, engine id, `items_extracted`, `raw_extraction_json` (the raw GPT-4o output), timing |
| 4 | `pobrain_purchase_orders` | PO **header**: `po_number`, `po_date`, vendor, delivery address, GST/CGST/SGST/IGST numbers, totals, currency (default INR), `is_duplicate` |
| 5 | `pobrain_purchase_order_line_items` | One row **per product line**: product name, CAS/CAT/HSN, quantity, unit price, amount, per-line GST rates & amounts |
| 6 | `pobrain_audit_logs` | INSERT audit record for the PO (`action_type='INSERT'`, `changed_by='SYSTEM'`) |
| — | `pobrain_workflow_steps` | Stage-by-stage execution tracking per email |
| — | `pobrain_processing_logs` | Structured event log (powers the Processing Logs screen) |

### 2.2 On failure — `handle_pipeline_failure()`

| Table | What is written |
|---|---|
| `pobrain_emails` | `status_id = 4` (FAILED) + `failure_reason` |
| `pobrain_error_logs` | Detailed error: message, stack trace, failed module, severity, category |
| `pobrain_failed_transactions` | User-facing failed record: PO number/date, product, qty, amount, email from/date, `error_reason` (powers the Failed Transactions screen) |

### 2.3 Legacy ERP integration (in `unified_po_extractor.py`)

The unified extractor also has `insert_into_legacy_tables()` which writes the same PO into an
existing ERP/order system: `dbo.tblClientOrder`, `dbo.tblComment`,
`dbo.SAT_WebOrder_Tracking`, with `lookup_customer_by_email()` to resolve the client
(PersonID + CompanyCode + Discount). It is **enabled** (`ENABLE_LEGACY_ERP_INSERT = True`) — see
§2.5 for the fixed schema mapping and §2.9 for the master-data lookup enrichment that now fills
`CatalogNo` / `PackCode` / `CompanyCode` / `Discount` deterministically instead of leaving them NULL.

### 2.4 The 18 database tables by group

**Lookup / reference (5):** `lkp_status`, `lkp_log_level`, `lkp_processing_stage`,
`lkp_error_category`, `lkp_parsing_engine`

**Core transactions (5):** `emails`, `email_attachments`, `extraction_jobs`,
`purchase_orders`, `purchase_order_line_items`

**Monitoring / ops (6):** `workflow_steps`, `processing_logs`, `error_logs`,
`failed_transactions`, `audit_logs`, `system_health_snapshots`

**Auth (2):** `users`, `password_resets` _(+ `notifications` added later = effectively 3)_

### 2.5 Which tables are actually ingested (written to), and by what

"Ingested" = receives row writes at runtime (not just seeded once). This is the precise map of
**who writes what**:

| # | Table | Group | Written by | Write type | Ingested at runtime? |
|---|---|---|---|---|---|
| 1 | `pobrain_emails` | Core | Python pipeline | INSERT + UPDATE (status/timing) | ✅ Yes |
| 2 | `pobrain_email_attachments` | Core | Python pipeline | INSERT + UPDATE (OCR/status) | ✅ Yes (when PDF present) |
| 3 | `pobrain_extraction_jobs` | Core | Python pipeline | INSERT + UPDATE (raw GPT JSON, results) | ✅ Yes |
| 4 | `pobrain_purchase_orders` | Core | Python pipeline | INSERT (PO header) | ✅ Yes (on success) |
| 5 | `pobrain_purchase_order_line_items` | Core | Python pipeline | INSERT (one row per product) | ✅ Yes (on success) |
| 6 | `pobrain_workflow_steps` | Monitoring | Python pipeline | INSERT (per stage) | ✅ Yes |
| 7 | `pobrain_processing_logs` | Monitoring | Python pipeline | INSERT (structured events) | ✅ Yes |
| 8 | `pobrain_error_logs` | Monitoring | Python pipeline | INSERT (on failure) | ✅ Yes (on failure) |
| 9 | `pobrain_failed_transactions` | Monitoring | Python pipeline | INSERT (on failure) | ✅ Yes (on failure) |
| 10 | `pobrain_audit_logs` | Monitoring | Python pipeline | INSERT (PO insert audit) | ✅ Yes |
| 11 | `pobrain_users` | Auth | Backend API | INSERT/UPDATE (register, login timestamps) | ✅ Yes |
| 12 | `pobrain_password_resets` | Auth | Backend API | INSERT/UPDATE (reset/OTP flow) | ✅ Yes |
| 13 | `pobrain_notifications` | Auth/Ops | **Backend API** (`NotificationService.Add` + `SaveChanges`) | INSERT/UPDATE (mark-read) | ✅ Yes |
| 14 | `pobrain_system_health_snapshots` | Monitoring | — (backend only **reads** it) | — | ⚠️ **No writer yet** — seeded/sample data only |
| 15 | `pobrain_lkp_status` | Lookup | `04_seed_data.sql` | seed only | ❌ Reference (not ingested) |
| 16 | `pobrain_lkp_log_level` | Lookup | `04_seed_data.sql` | seed only | ❌ Reference |
| 17 | `pobrain_lkp_processing_stage` | Lookup | `04_seed_data.sql` | seed only | ❌ Reference |
| 18 | `pobrain_lkp_error_category` | Lookup | `04_seed_data.sql` | seed only | ❌ Reference |
| 19 | `pobrain_lkp_parsing_engine` | Lookup | `04_seed_data.sql` | seed only | ❌ Reference |

**Legacy ERP tables** — `insert_into_legacy_tables()` is **called unconditionally on every
successful PO save** (step 5 of `save_parsed_data_to_db`, line 749 — no feature flag). However
it is **best-effort and silently self-skips**, and a live DB check (2026-06-09) confirms it has
**never actually written a row**:

| Table | Exists on `hyma_testdb`? | Rows (pre-existing ERP) | Ingested by pipeline? |
|---|---|---|---|
| `dbo.tblClientOrder` | ✅ Yes | 731,878 | ✅ Yes (one row per line item) |
| `dbo.tblComment` | ✅ Yes | 352,438 | ✅ Yes (when email body has a note) |
| `dbo.SAT_WebOrder_Tracking` | ✅ Yes | 142,177 | ✅ Yes (one row per PO) |
| `dbo.tblRegistration` (PersonID lookup) | ✅ Yes | 6,351 (all have emails) | read-only lookup |

**Status: ✅ FIXED & ENABLED (2026-06-09 broken → fixed). `ENABLE_LEGACY_ERP_INSERT = True`.**

It was originally broken — every insert failed on schema mismatches (the code pushed the string
PO number into the numeric BIGINT `OrderID`, and never supplied the NOT-NULL `WebOrderID`). The
fix, verified end-to-end against the live tables in a rolled-back transaction using a real
registered vendor (`ksivaprasad@caplinpoint.net`, PersonID 16728):

| Field | Before (broken) | After (fixed) |
|---|---|---|
| `OrderID` / `WebOrderID` | string PO `"PO-…"` → `nvarchar→bigint` error | generated numeric order no. (`MAX+1` across order tables) |
| PO reference string | lost in `OrderID` | stored in `POID` (tblClientOrder) and `SONo` (SAT) |
| `WebOrderID` (NOT NULL PK) | not supplied → `Cannot insert NULL` | supplied with the generated order no. |
| `GSTTAX` (int col) | raw decimal | cast to `int` |
| `WebOrderDate` (NOT NULL) | could be NULL | falls back to today (IST) |

Verified result: a 2-line-item PO inserted **2 rows into `tblClientOrder`, 1 into `tblComment`,
1 into `SAT_WebOrder_Tracking`**, with `POID='PO-…'` and a fresh `OrderID` (e.g. 2627100581),
then rolled back — 0 persisted.

**Guard:** the insert still runs only when the PO's `vendor_email` matches `tblRegistration`
(PersonID lookup), so unknown senders are skipped. Set `ENABLE_LEGACY_ERP_INSERT = False` to turn
it off.

> ⚠️ **Order-number generation uses `MAX+1`** (the ERP has no sequence object). This is safe for
> the single-instance pipeline against `hyma_testdb`. If ever pointed at a **production** ERP that
> mints its own order numbers, swap in the ERP's real generator to avoid races/collisions.

**Summary of ingestion:**
- **Python pipeline ingests 10 `pobrain_*` tables** (4 always: emails, jobs, + logs/workflow/audit;
  attachments only with PDFs; PO + line-items on success; error_logs + failed_transactions on failure)
  **plus the 3 legacy ERP tables** (`tblClientOrder`, `tblComment`, `SAT_WebOrder_Tracking`) when the
  vendor email matches `tblRegistration` — fixed & enabled 2026-06-09 (see below).
- **Backend API ingests 3 tables**: `users`, `password_resets`, `notifications`.
- **5 lookup tables** are seed/reference only — never ingested at runtime.
- ⚠️ **`pobrain_system_health_snapshots` has no runtime writer** — the backend only reads it to
  broadcast health %. The live "95.7% / 94.5% / 50%" values come from seeded/sample rows. A
  job that inserts real snapshots (Python pipeline or a backend background service) is missing.

### 2.6 Email-processing safeguards (added 2026-06-09)

Before these safeguards, the pipeline processed **every** unread email and relied entirely on
GPT-4o returning `[]` to avoid junk. A live audit found 73 emails ingested from 37 senders —
~96% newsletters (LinkedIn ×16, Notion, Ollama, Kaggle, Docusign…) — each costing one GPT-4o
call and an `emails` + `extraction_jobs` row. Two safeguards now address this:

**(A) PO relevance pre-filter** — `is_likely_po_email()`, runs in `process_single_email_bytes`
**before** any OpenAI call or DB write:
- An email is processed only if it **has a PDF attachment** OR its **subject/body matches a PO
  keyword** (`purchase order`, `PO No/Number/#`, `PO-<digits>`, `order no/number`, `quotation`,
  `rfq`, `proforma`, `indent`, `delivery order` — word-boundary regex, so "in order to" does
  **not** match).
- A **sender blocklist** (`PO_SENDER_BLOCKLIST`) hard-skips known newsletter domains
  (linkedin.com, notion.so, ollama.com, kaggle.com, docusign.com, adobe.com, …) even if they
  carry a PDF.
- Skipped emails are logged to `pobrain_processing_logs`, marked seen, and moved to a new
  **`skipped`** IMAP folder (`watcher.mark_skipped`). **No GPT call, no `pobrain_*` records.**
- Toggle with `ENABLE_PO_PREFILTER` (default `True`); set `False` for legacy "process-all" behaviour.
- Config lives at the top of `unified_po_extractor.py` (`PO_SENDER_BLOCKLIST`, keyword regex
  `_PO_KEYWORD_RE`) — edit there to tune which senders/keywords qualify.

**(B) Validation gate** — in `save_parsed_data_to_db`, **before** inserting a PO:
- A PO is created **only if it has a real `po_number`**. The old code fabricated a
  `TEMP-PO-<email_id>` placeholder when the number was missing — that path is **removed**.
  Items with no PO number are skipped (counted in `stats["skipped"]`, logged as `WARN`).
- If no valid PO groups remain, the function returns without inserting anything.
- Within a valid PO, **completely empty line rows** (no product AND no quantity AND no amount)
  are skipped instead of inserting a junk `"Unparsed Product"` row. Line numbers stay sequential.
- A genuinely missing product name on an otherwise real line now falls back to
  `"Unspecified Item"` (was `"Unparsed Product"`).

**Net effect:** non-PO mail is dropped early (lower OpenAI cost, cleaner dashboard counts), and
even if GPT returns a non-empty-but-empty-valued array, **no placeholder/junk PO can be created**
— closing the latent bug identified in the audit.

> Helper `_has_value()` (treats `None`/`""`/`"null"`/`"none"`/`"n/a"` as empty) backs the gate.
> New IMAP folder `skipped` joins the existing `processed` and `failed` folders.

### 2.7 End-to-end verification (2026-06-09)

The Python extractor was tested end-to-end against a sample PO email whose vendor email
(`ksivaprasad@caplinpoint.net`) is a real `tblRegistration` record (PersonID 16728). The ERP
insert step ran inside a **rolled-back transaction** so nothing was persisted.

| Step | Function | Result |
|---|---|---|
| 1. Parse | `parse_email_structure()` | ✅ from / subject / body extracted correctly |
| 2. Pre-filter | `is_likely_po_email()` | ✅ passed ("PO keyword matched in subject/body") |
| 3. AI extract | `extract_data_via_openai()` (live GPT-4o) | ✅ returned **2** correct line items (Ethanol, Methanol) with po_number, qty, amount, vendor_email |
| 4. Validation gate | grouping logic | ✅ junk (no po_number) rejected; 2 real items kept |
| 5. PersonID lookup | `lookup_person_id_by_email()` | ✅ returned **16728** |
| 6. Legacy ERP insert | `insert_into_legacy_tables()` | ❌ initially failed (schema mismatch) → ✅ **FIXED & verified** (2/1/1 rows into the 3 ERP tables, rolled back) — see §2.5 |

**Conclusion: the full pipeline works end-to-end** (email → parse → filter → GPT-4o → validated
structured rows → `pobrain_*` schema **and** the 3 legacy ERP tables for registered vendors). The
ERP insert was broken at first audit but has since been fixed and enabled (§2.5).

### 2.8 Timezone — all timestamps are Indian Standard Time (IST, UTC+5:30)

As of 2026-06-09 every timestamp the system records is **IST** (was UTC). IST has no daylight
saving, so a fixed +5:30 offset is used everywhere.

| Layer | Mechanism |
|---|---|
| Python `now()` | `IST = timezone(timedelta(hours=5, minutes=30))` + `now_ist()` helper |
| Python SQL inserts | `DATEADD(MINUTE, 330, GETUTCDATE())` (replaces `GETUTCDATE()`) |
| Python email date | sender's `Date:` header normalised via `.astimezone(IST)` |
| Python logs | `logging.Formatter.converter` forced to IST |
| Backend (.NET) | `AppClock.NowIst` (`DateTime.UtcNow.Add(5:30)`) replaces `DateTime.UtcNow` |
| Database defaults | all `pobrain_*` `DEFAULT` constraints = `DATEADD(MINUTE, 330, GETUTCDATE())` |

**Formats unchanged:** `po_date` is still `YYYY-MM-DD` (date only); all timestamp columns remain
`DATETIME2(3)`; only the *value* shifted from UTC to IST.

> ⚠️ **Existing rows were NOT shifted.** The migration changes defaults + code going forward;
> rows written before 2026-06-09 still hold their original UTC values. Given they are test data
> this was left as-is — run a one-off `UPDATE ... DATEADD(MINUTE,330,col)` per timestamp column if
> a clean historical cut is needed.
>
> ⚠️ `06_sample_data.sql` (demo/seed rows) was intentionally left on `GETUTCDATE()` — it is
> illustrative dev data, not part of the live ingest path.

### 2.9 Master-data lookup enrichment (added 2026-06-16, revised 2026-06-18)

Several ERP `tblClientOrder` columns used to be written `NULL` because the values **are not
printed on a customer PO** — they are Hyma's *internal* master-data codes. GPT cannot read them
off the document (asking it to would make it **invent** wrong codes and corrupt the ERP), so they
are **resolved by deterministic lookup** against existing master tables.

**2026-06-18 revision.** Two corrections were made:
1. **Catalog number goes in the catalog column, not the item-code column.** The Hyma code we
   resolve (e.g. `ASD2431`) is a *catalog number* held in `dbo.tblGroupSubNames.CatalogNo`. It is now
   written to `tblClientOrder.CatalogNo` / `pobrain_purchase_order_line_items.cat_number`.
   `tblClientOrder.ItemCode` is left `NULL` (no reliable distinct master source for it).
2. **PO-Brain line items no longer mirror the pack/item/discount columns.** The columns
   `pack_size`, `pack_code`, `item_code`, `discount` added to `pobrain_purchase_order_line_items`
   by `10_add_master_lookup_fields.sql` were **dropped** by `Database/11_drop_line_item_lookup_fields.sql`.
   These enrichments still flow into the **ERP** `tblClientOrder` (`PackCode`, `PackSize`,
   `Discount`), but PO-Brain keeps only the data the PO actually carries. `company_code` stays on
   `pobrain_purchase_orders`.

**Field → source map** (`unified_po_extractor.py`):

| ERP column (`tblClientOrder`) | PO-Brain column | Source | Method | Safety |
|---|---|---|---|---|
| `CatalogNo` | `..._line_items.cat_number` | `tblGroupSubNames.CatalogNo` | PO-printed catalog validated against master → else **unique** CAS match → else PO value → else NULL | ✅ guarded (ambiguous CAS → NULL) |
| `ItemCode` | — (removed) | *no reliable distinct source* | left NULL (never guessed) | — |
| `CompanyCode` | `pobrain_purchase_orders.company_code` | `tblRegistration.CompanyCode` | same row as the PersonID lookup (by buyer email) | ✅ deterministic; blank → NULL |
| `Discount` / `DiscountPrice` | — (ERP only) | `tblRegistration.Discount` (+ derived `Price × Discount/100`) | customer's default discount | ✅ deterministic |
| `PackCode` | — (ERP only) | `Avra2020_PackingCodes` (190 rows) | **normalized pack-size match** → else NULL | ✅ guarded |
| `PackSize` | — (ERP only) | **the PO itself** | GPT extract (genuinely printed on the PO) | ✅ |
| `WebOrderCustCode` (`SAT_WebOrder_Tracking`) | — | `tblRegistration.CompanyCode` | same lookup | ✅ deterministic |
| `DItemCode` | — | *no master source exists* | left NULL (never guessed) | — |

**Lookup helpers:**
- `lookup_customer_by_email()` — returns `{person_id, company_code, discount}` from
  `tblRegistration` by exact email; blank `CompanyCode` is normalised to `NULL`.
- `resolve_catalog_no(cas, po_catalog_no)` — Hyma catalog number from `tblGroupSubNames`.
  Order: (1) PO-printed catalog validated against the master, (2) CAS only when it maps to a
  **single distinct** `CatalogNo` (CAS is many-to-one there — `73-24-5` → 3 codes,
  `7647-01-0` → 16 — so ambiguous CAS yields NULL), (3) PO-printed value as-is, else NULL.
- `lookup_pack_code()` — `Avra2020_PackingCodes` match on a normalised pack string (lowercased,
  symbols/whitespace stripped), compared against both `PackCode` and `PackDesc`.

**Design principle — never guess.** The guarded lookups fill **only on an exact/normalized/unique
match**; otherwise the column stays `NULL`. A wrong code in the ERP is worse than a NULL.

**Verified (2026-06-18).** `resolve_catalog_no` against the live master:

| `cas` | PO-printed cat | result | note |
|---|---|---|---|
| `38078-09-0` | — | `ASD2431` | unique CAS match |
| `73-24-5` | — | NULL | 3 catalogs for this CAS — ambiguous, not guessed |
| `73-24-5` | `ALA1041` | `ALA1041` | printed value disambiguates + validates |
| — | `ASD2431` | `ASD2431` | valid printed catalog |
| `50-78-2` | — | NULL | CAS absent from master, nothing printed |

---

### 2.10 Line-item financials (added 2026-06-18)

All money fields are computed in **one place** — `compute_line_financials()` in
`unified_po_extractor.py` — and reused by the ERP write (`tblClientOrder`), the PO-Brain write
(`pobrain_purchase_order_line_items` / `_purchase_orders`), **and** the customer acknowledgment
email, so the three can never disagree.

**Sources (confirmed with the business):**
- **discount %** — the value printed on the PO if present, else the customer's default
  (`tblRegistration.Discount`).
- **gst %** — the value printed on the PO if present, else `tblGroupSubNames.GSTPER` (resolved by
  CatalogNo, else a *unique* CAS match; `'18%'`→18). If neither is available but the PO printed
  explicit CGST/SGST/IGST amounts, the rate is backed out from those amounts.

**Formulas** (`discount price = price − discount %`, corrected from the earlier version that stored
the discount *amount*):

```
price           = amount  (or quantity × unit_price)
discount_amount = price × discount% / 100
discount_price  = price − discount_amount            # NET price after discount
gst_amount      = discount_price × gst% / 100        # GST charged on the NET price
line_total      = discount_price + gst_amount
```

**PO-level totals** (`pobrain_purchase_orders`):

| Column | Formula |
|---|---|
| `subtotal_amount` | Σ price (gross) |
| `total_discount_amount` | Σ discount_amount |
| `total_tax_amount` | Σ gst_amount (GST on net) |
| `total_amount` (grand total) | Σ discount_price + Σ gst_amount  (= subtotal − discount + tax) |

**Column mapping**

| Concept | ERP `tblClientOrder` | PO-Brain line item |
|---|---|---|
| discount % | `Discount` (int) | `discount` (int) |
| net price | `DiscountPrice` | `discount_price` |
| gst % | `GSTTAX` (int) | `gst_rate` |
| gst on net | `GstPrice` | `gst_amount` |
| unit / gross | `UnitPrice` / `Price` | `unit_price` / `amount` |
| per-tax amounts | — | `cgst_amount` / `sgst_amount` / `igst_amount` (as printed on PO) |
| per-tax rates | — | `cgst_rate` / `sgst_rate` / `igst_rate` (derived from amount ÷ base) |

Two new GPT fields feed this: `discount` and `gst_rate` (both percentages, only when printed on the
PO). Verified live: a 2000 line at 10% discount + 18% GST → net 1800, GST 324, line total 2124;
GST% for catalog `ASN2749` resolves to 18 from `GSTPER`. All INSERTs execute against the live schema
(rolled-back exec test).

---

## 3. Backend API — endpoints & status

| Controller | Endpoints (high level) | Backing table(s) | Status |
|---|---|---|---|
| `AuthController` | login, password reset / OTP | `pobrain_users`, `pobrain_password_resets` | ✅ Working (login verified in logs) |
| `DashboardController` | stats / summary cards | aggregates across core tables | ✅ Implemented |
| `ExtractionsController` | list + filters + **CSV export** | `purchase_order_line_items` + joins | ✅ Implemented |
| `LogsController` | list + filters + **CSV export** | `processing_logs` | ✅ Implemented |
| `FailedTransactionsController` | list + filters + **CSV export** | `failed_transactions` | ✅ Implemented |
| `NotificationsController` | count, list, create, mark-read | `pobrain_notifications` | ✅ Fixed (see §5) |
| SignalR `HealthStreamHub` | live health % broadcast | `system_health_snapshots` | ✅ Broadcasting |
| SignalR `LogStreamHub` | live log stream | `processing_logs` | ✅ Wired |

**Cross-cutting backend features done:**
- Structured Serilog logging on all new export endpoints (UserId + Action via `LogContext`).
- CSV export with proper escaping (quotes, commas, newlines) across all three screens.
- CORS configured to expose `Content-Disposition`, `Content-Type`, `Content-Length` so the
  browser can read download filenames.
- `HealthBroadcastService` background service pushes health every 30 min / 30 s tick.

---

## 4. Frontend — pages & binding status

| Page | UI built? | Bound to API? |
|---|---|---|
| `Login` | ✅ | ❌ mock |
| `Dashboard` | ✅ (stat cards, health, recent activity) | ❌ hardcoded `stats` array |
| `ExtractionResults` | ✅ | ❌ mock |
| `ProcessingLogs` | ✅ | ❌ mock |
| `FailedTransactions` | ✅ | ❌ mock |
| `DataPreview` | 🔄 in progress / partly commented out | ❌ |

**What's missing on the frontend:**
- No API client / service layer (no `fetch`/`axios`, TanStack Query unused).
- No auth token storage/attach, no SignalR client for live health/logs.
- No wiring of the working CSV-export endpoints to download buttons.
- Deployed origin not yet whitelisted in backend CORS.

---

## 5. Recently completed work (this engagement)

- **CSV export** added end-to-end for Processing Logs, Extractions, and Failed Transactions
  (service + controller + structured logging + CORS header exposure).
- **Notifications API 500 error fixed.** Root cause: EF Core had no table-name/column mapping
  for the `Notification` entity, so it queried a non-existent `Notifications` table. Fixed by:
  - `e.ToTable("pobrain_notifications")` + `HasColumnName()` for all 10 columns in `PoBrainDbContext`.
  - Changing `RelatedErrorId` from `string?` → `int?` in entity + DTO + request (DB column is INT).
  - Creating `07_add_notifications_table.sql`.
  - Verified: `GET /api/notifications/count` and `/api/notifications` now return **200**.
- **Email-processing safeguards** added to `unified_po_extractor.py` (see §2.6): a PO relevance
  **pre-filter** (sender blocklist + PDF/keyword check) that skips non-PO mail before any GPT
  call, and a **validation gate** that refuses to fabricate placeholder/junk POs. Verified: the
  filter correctly classifies all real senders from the live audit (LinkedIn/Notion/Ollama →
  skipped; Merck/Sigma/PDF senders → processed; "in order to" does not false-match). File still
  compiles clean.
- **All timestamps converted UTC → IST (Indian Standard Time, UTC+5:30)** across every layer
  (2026-06-09) — see §2.8:
  - **Python:** added `IST`/`now_ist()`; replaced all `datetime.now(timezone.utc)` → `now_ist()`,
    all SQL `GETUTCDATE()` → `DATEADD(MINUTE, 330, GETUTCDATE())`, email date normalised to IST,
    and log timestamps forced to IST.
  - **Backend (.NET):** added `AppClock.NowIst`; replaced all `DateTime.UtcNow` → `AppClock.NowIst`
    (AuthService, NotificationService, 3 export controllers). Builds clean (0 warnings).
  - **Database:** ran `09_migration_utc_to_ist.sql` against the live DB — **17 `pobrain_*` default
    constraints converted** from `GETUTCDATE()` to IST (0 UTC remaining); updated the schema
    scripts (`01_create_tables.sql`, `07_*`, `08_*`) for fresh deploys. Verified Python and DB
    now produce identical IST (exactly +5:30).
- **`failed_transactions` ingestion verified working** (not a bug). Diagnostic: 1 failed email →
  1 `failed_transactions` row → 0 failed emails missing a row. The table only fills on a genuine
  processing exception; successful POs and pre-filter skips correctly do not write to it.
- **Vendor extraction corrected** — `vendor_name`/`vendor_email` now capture the **customer/buyer**
  who issued the PO (e.g. FDC, Dr. Reddy's, Laxai), never Hyma Synthesis (the supplier/ourselves).
  Prompt rule rewritten; verified on the sample POs.
- **Master-data lookup enrichment (2026-06-16)** — ERP codes that aren't on the PO
  (`CatalogNo`, `PackCode`, `CompanyCode`, `Discount`, `WebOrderCustCode`) are filled by
  **deterministic lookup** from `tblGroupSubNames` / `Avra2020_PackingCodes` / `tblRegistration`
  instead of being NULL or GPT-guessed. Guarded (exact/unique-match-only → else NULL),
  blank `CompanyCode` normalised to NULL. See §2.9.
- **Catalog/column corrections (2026-06-18)** — the resolved Hyma catalog number now lands in
  `CatalogNo` / `cat_number` (was wrongly in `ItemCode`); resolution source switched to
  `tblGroupSubNames` with an ambiguous-CAS guard; `ItemCode` left NULL. The PO-Brain line-item
  mirror columns `pack_size`/`pack_code`/`item_code`/`discount` were dropped
  (`11_drop_line_item_lookup_fields.sql`) — those enrichments persist in the ERP only.
- **Per-branch IMAP dedup fix (2026-06-18)** — `pobrain_emails.mail_uid` is now namespaced by
  branch (`hyderabad:<uid>` / `bangalore:<uid>`). IMAP UIDs are per-mailbox, so the old bare-UID
  key caused a Hyderabad email to be wrongly skipped as a "duplicate" of Bangalore's same-numbered
  UID (and vice-versa). This is why mail from `ggitggitggit@gmail.com` (Hyderabad) was being missed.
- **Line-item financials (2026-06-18)** — discount / GST / net-price / grand-total are now computed
  by one shared `compute_line_financials()` used by ERP + PO-Brain + the ack email. Corrected
  `discount_price` to the **net** price (`price − discount%`), GST now charged on the **net**,
  `total_amount = Σ net + Σ GST`, and `cgst/sgst/igst_rate`, `discount`, `discount_price`, `gst_rate`,
  `gst_amount`, `total_discount_amount` are now populated. discount% and GST% come from the PO if
  printed, else customer master / `tblGroupSubNames.GSTPER`. New GPT fields: `discount`, `gst_rate`.
  See §2.10.
- **Lock-up / idle-in-transaction fix (2026-07-08)** — a `SELECT` on `pobrain_emails` (and earlier
  `pobrain_notifications`) could hang indefinitely because the pipeline ran `log_to_db()` (opens its
  own connection → `pobrain_processing_logs`, FK to `pobrain_emails`) and the SMTP acknowledgment
  email **inside** the open data transaction, self-blocking and leaving a connection idle-in-
  transaction holding exclusive locks. Fixes: (1) `_db_conn()` now sets `SET LOCK_TIMEOUT 15000` so a
  blocked statement fails fast and releases; (2) `save_parsed_data_to_db` defers all `log_to_db`
  writes and the ack email to **after** the transaction commits (`compute_line_financials` results are
  precomputed and passed to the email, which no longer needs a DB cursor). Lock-hold windows are now
  sub-second.

---

## 6. Pending / outstanding work (all parts)

### 🔴 High priority
1. **Bind the frontend to the backend API** — build an API client/service layer, replace all
   mock data on Dashboard, ExtractionResults, ProcessingLogs, FailedTransactions, Login.
2. **Wire CSV-export buttons** in the UI to the existing export endpoints.
3. **Auth integration** — store JWT, attach to requests, protect routes against the real API.
4. **Move credentials to environment variables** — Python `CONFIG` dicts and backend
   `appsettings.json` currently hold secrets (Gmail, OpenAI, DB, SMTP, JWT key) in plaintext.
5. ✅ **DONE — Swagger sub-path fix** (2026-06-09): `Program.cs` now uses the relative
   `SwaggerEndpoint("v1/swagger.json", …)` so the spec loads under `/coreapiv1pob/swagger/`.
   Backend rebuilt clean. API restart + redeploy required to take effect.
6. ✅ **DONE — deployed frontend origin added to backend CORS** (`https://gagriglobal.com` added
   to `appsettings.json` `CorsSettings:AllowedOrigins`, 2026-06-09). API restart required to take
   effect. (Note: CORS origins are scheme+host only — the `/Pobrain/` path is not part of the origin.)
7. ✅ **DONE (fixed & enabled) — legacy ERP insert path repaired** (`ENABLE_LEGACY_ERP_INSERT = True`,
   2026-06-09). Schema-mismatch bugs fixed (numeric `OrderID`/`WebOrderID` via MAX+1, PO string →
   `POID`/`SONo`); verified end-to-end (2/1/1 rows into the 3 ERP tables, rolled back). See §2.5.
   **Caveat for production:** swap the `MAX+1` order-number generation for the ERP's real generator
   if ever pointed at a live ERP that mints its own order numbers.

### 🟡 Medium priority
8. **SignalR client** in the frontend for live health % and live log streaming.
9. `DataPreview` page — finish and enable.
10. Fix duplicate `07_` SQL script numbering.
11. Resolve the EF Core warning: `decimal property 'HealthPct'` needs explicit
    `HasPrecision`/`HasColumnType` (currently silent-truncation risk).
12b. **`pobrain_system_health_snapshots` has no runtime writer** — add a job (Python pipeline or
    backend background service) that inserts real health snapshots; today the dashboard shows
    seeded/sample numbers.
12. Backend has **no test project**; frontend has Vitest configured but minimal tests.

### 🟢 Low priority
13. Charts/analytics for PO trends.
14. Support for more mail providers (Outlook/Yahoo).
15. Docker containerization.
16. PDF attachment preview in the dashboard.

---

## 7. Completed vs. not — at a glance

| Area | Completed | Not done / pending |
|---|---|---|
| **Python extraction** | IMAP poll, body+HTML parse, PDF native+OCR, GPT-4o extraction (verified end-to-end 2026-06-09 & 2026-06-16), multi-line items, dedup, normalized inserts, failure handling, audit + workflow + logs, JSON backup, rotating logs, **PO relevance pre-filter + validation gate (no junk POs)**, **legacy ERP insert fixed & enabled**, **correct customer/buyer vendor extraction**, **master-data lookup enrichment (ItemCode/PackCode/CompanyCode/Discount + PackSize) §2.9**, **all timestamps IST** | Env-var secrets; ERP order-number generator for production (MAX+1 ok for test DB); `PackCode` low hit-rate on compound packs |
| **Database** | All 18 tables (+5 PO-Brain master-lookup columns via `10_*`), FKs, indexes, views, seed + sample data, auth + notifications tables, **default constraints converted UTC→IST (live + scripts)** | Duplicate `07_` numbering; HealthPct precision; existing rows still UTC (§2.8) |
| **Backend API** | Auth/login, dashboard, extractions, logs, failed-tx, CSV export ×3, notifications, SignalR health+logs, Serilog, JWT, **Swagger sub-path fixed**, **deployed CORS origin added**, **timestamps IST (`AppClock`)** | Tests; secrets to env |
| **Frontend** | All page UIs, layout/sidebar/topbar, routing, shadcn components | **API binding (all pages on mock data)**, auth flow, SignalR client, export buttons, DataPreview |
| **Deployment** | API under `/coreapiv1pob/`; frontend at `gagriglobal.com/Pobrain/`; CORS origin added; **Swagger sub-path fixed** | API restart/redeploy to apply fixes; frontend↔API integration |

---

## 8. Known deployment issue (✅ RESOLVED 2026-06-09)

**Swagger UI failed to render on the server** (`/coreapiv1pob/swagger`) with "does not specify a
valid version field". Cause: `SwaggerEndpoint("/swagger/v1/swagger.json", …)` used an absolute
path that ignored the `/coreapiv1pob` sub-path, so the browser fetched an HTML error page instead
of the spec. **Fixed** in `Backend/Program.cs` by switching to the **relative** path
`SwaggerEndpoint("v1/swagger.json", …)`, which resolves correctly both locally and behind the
sub-path. Backend rebuilt clean.

> **Deploy step:** rebuild + redeploy the API (and restart it) for the Swagger fix and the new
> CORS origin to take effect on the server. If the reverse proxy *strips* the `/coreapiv1pob`
> prefix before forwarding, also add `app.UsePathBase("/coreapiv1pob")` near the top of the
> pipeline — otherwise no further change is needed.
