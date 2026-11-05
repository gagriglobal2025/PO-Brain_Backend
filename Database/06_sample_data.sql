-- ============================================================================
-- PO-Brain Sample Data
-- Database: hyma_testdb
-- Prefix:   dbo.pobrain_
-- Version:  1.0.0
-- Created:  2026-05-29
-- Description: Generates rich, realistic, and consistent sample data across
--              all 11 transactional, monitoring, logging, and audit tables.
--              Includes fully resolved parent-child workflows, success flows,
--              OCR flows, and realistic parsing/validation failure flows.
-- ============================================================================
-- Execution Order: Run AFTER 05_views_dashboard.sql
-- ============================================================================

USE [hyma_testdb];
GO

PRINT '============================================================================';
PRINT '  Seeding PO-Brain Transactional and Operational Sample Data...';
PRINT '============================================================================';

-- Disable foreign key constraints temporarily to allow safe seeding of specific IDs if needed
-- (Though we insert in perfect dependency order, this guarantees a clean, issue-free load)
EXEC sp_MSforeachtable "ALTER TABLE ? NOCHECK CONSTRAINT ALL";
GO

-- Declare common variables for time calculations
DECLARE @Now DATETIME2(3) = GETUTCDATE();
DECLARE @Email1Time DATETIME2(3) = DATEADD(minute, -120, @Now);
DECLARE @Email2Time DATETIME2(3) = DATEADD(minute, -90, @Now);
DECLARE @Email3Time DATETIME2(3) = DATEADD(minute, -60, @Now);
DECLARE @Email4Time DATETIME2(3) = DATEADD(minute, -30, @Now);
DECLARE @Email5Time DATETIME2(3) = DATEADD(minute, -15, @Now);
GO

-- ============================================================================
-- 1. SEED: dbo.pobrain_emails
-- ============================================================================
PRINT '1. Seeding dbo.pobrain_emails...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_emails)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_emails ON;

    -- Emails map:
    -- ID 1: Sigma-Aldrich - Processed successfully
    -- ID 2: Merck Life - Processed successfully (Required OCR)
    -- ID 3: Unreliable Vendor - Failed on parse (Corrupted PDF)
    -- ID 4: Active Vendor - Processing (Active / Pending parsing)
    -- ID 5: Duplicate Vendor - Skipped (Duplicate attachment/hash detected)

    INSERT INTO dbo.pobrain_emails (
        email_id, mail_uid, email_from, email_to, email_subject, 
        email_received_at, email_body_preview, attachment_count, has_pdf, 
        status_id, retry_count, max_retries, failure_reason, 
        processing_started_at, processing_completed_at, processing_duration_ms, 
        created_at, created_by
    )
    VALUES
    (
        1, 'MSG-UID-10243-SIGMA', 'orders@sigmaaldrich.in', 'po-intake@company.com', 'Purchase Order PO-2026-001 for Chemical Raw Materials',
        DATEADD(minute, -120, GETUTCDATE()), 'Dear PO-Brain team, Please find attached our purchase order PO-2026-001 for Acetonitrile and Ethanol absolute. Please confirm delivery details.',
        1, 1, 3, 0, 3, NULL,
        DATEADD(minute, -119, GETUTCDATE()), DATEADD(minute, -118, GETUTCDATE()), 60000,
        DATEADD(minute, -120, GETUTCDATE()), 'SYSTEM'
    ),
    (
        2, 'MSG-UID-58210-MERCK', 'sales@merck.co.in', 'po-intake@company.com', 'ORDER INQUIRY - PO-2026-002 - URGENT',
        DATEADD(minute, -90, GETUTCDATE()), 'Please find our purchase order PO-2026-002. Note that the scanned copy is attached. We request processing as early as possible.',
        1, 1, 3, 0, 3, NULL,
        DATEADD(minute, -88, GETUTCDATE()), DATEADD(minute, -85, GETUTCDATE()), 180000,
        DATEADD(minute, -90, GETUTCDATE()), 'SYSTEM'
    ),
    (
        3, 'MSG-UID-99321-FAILED', 'procurement@unreliablevendor.com', 'po-intake@company.com', 'New PO attachment',
        DATEADD(minute, -60, GETUTCDATE()), 'PFA my purchase order file. Thanks, John',
        1, 1, 4, 1, 3, 'Failed to parse corrupted_po.pdf. Expected PDF header not found.',
        DATEADD(minute, -59, GETUTCDATE()), DATEADD(minute, -58, GETUTCDATE()), 45000,
        DATEADD(minute, -60, GETUTCDATE()), 'SYSTEM'
    ),
    (
        4, 'MSG-UID-11223-ACTIVE', 'dispatch@tata-chemicals.com', 'po-intake@company.com', 'Purchase Order PO-2026-004 - Soda Ash',
        DATEADD(minute, -30, GETUTCDATE()), 'Dear team, Please process the order PO-2026-004 from Tata Chemicals. Attached is the generated PDF invoice.',
        1, 1, 2, 0, 3, NULL,
        DATEADD(minute, -1, GETUTCDATE()), NULL, NULL,
        DATEADD(minute, -30, GETUTCDATE()), 'SYSTEM'
    ),
    (
        5, 'MSG-UID-88320-DUP', 'sales@merck.co.in', 'po-intake@company.com', 'RE: ORDER INQUIRY - PO-2026-002 - URGENT',
        DATEADD(minute, -15, GETUTCDATE()), 'Resending the previous attachment PO-2026-002 just in case it did not go through.',
        1, 1, 5, 0, 3, 'Duplicate attachment file detected via MD5 hash check.',
        DATEADD(minute, -14, GETUTCDATE()), DATEADD(minute, -14, GETUTCDATE()), 5000,
        DATEADD(minute, -15, GETUTCDATE()), 'SYSTEM'
    );

    SET IDENTITY_INSERT dbo.pobrain_emails OFF;
    PRINT '  → 5 email records seeded successfully';
END
ELSE
BEGIN
    PRINT '  → dbo.pobrain_emails already has data, skipping';
END;
GO

-- ============================================================================
-- 2. SEED: dbo.pobrain_email_attachments
-- ============================================================================
PRINT '2. Seeding dbo.pobrain_email_attachments...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_email_attachments)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_email_attachments ON;

    INSERT INTO dbo.pobrain_email_attachments (
        attachment_id, email_id, file_name, file_type, file_size_bytes, 
        storage_path, file_hash, status_id, ocr_required, ocr_status_id, 
        page_count, created_at, created_by
    )
    VALUES
    (
        1, 1, 'PO_10243.pdf', 'pdf', 145280, 
        '/storage/po_files/2026/05/29/PO_10243.pdf', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 
        13, 0, NULL, 1, 
        DATEADD(minute, -120, GETUTCDATE()), 'SYSTEM'
    ),
    (
        2, 2, 'PO_A5821_Scanned.pdf', 'pdf', 1240500, 
        '/storage/po_files/2026/05/29/PO_A5821_Scanned.pdf', '8a5da52ed1264c4c8d9cfca3e41c4f74d9cf28e4649b934ca495991b7852b865', 
        16, 1, 16, 2, 
        DATEADD(minute, -90, GETUTCDATE()), 'SYSTEM'
    ),
    (
        3, 3, 'corrupted_po.pdf', 'pdf', 2410, 
        '/storage/po_files/2026/05/29/corrupted_po.pdf', '0f3e41c888d3e41c8f85d34b934c99c4d9cf28e4649b934ca495991b7852b999', 
        14, 0, NULL, NULL, 
        DATEADD(minute, -60, GETUTCDATE()), 'SYSTEM'
    ),
    (
        4, 4, 'PO_9938_Tata.pdf', 'pdf', 382400, 
        '/storage/po_files/2026/05/29/PO_9938_Tata.pdf', '38d9f481c4e743a123fca88c991b78527a41e4649b934ca495991b7852b12345', 
        11, 0, NULL, 3, 
        DATEADD(minute, -30, GETUTCDATE()), 'SYSTEM'
    ),
    (
        5, 5, 'PO_A5821_Scanned.pdf', 'pdf', 1240500, 
        '/storage/po_files/2026/05/29/PO_A5821_Scanned_Dup.pdf', '8a5da52ed1264c4c8d9cfca3e41c4f74d9cf28e4649b934ca495991b7852b865', 
        14, 1, NULL, 2, 
        DATEADD(minute, -15, GETUTCDATE()), 'SYSTEM'
    );

    SET IDENTITY_INSERT dbo.pobrain_email_attachments OFF;
    PRINT '  → 5 email attachment records seeded successfully';
END
ELSE
BEGIN
    PRINT '  → dbo.pobrain_email_attachments already has data, skipping';
END;
GO

-- ============================================================================
-- 3. SEED: dbo.pobrain_extraction_jobs
-- ============================================================================
PRINT '3. Seeding dbo.pobrain_extraction_jobs...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_extraction_jobs)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_extraction_jobs ON;

    INSERT INTO dbo.pobrain_extraction_jobs (
        job_id, attachment_id, status_id, engine_id, confidence_score, 
        validation_status_id, items_extracted, raw_extraction_json, 
        started_at, completed_at, duration_ms, attempt_number, created_at, created_by
    )
    VALUES
    (
        1, 1, 24, 1, 98.50, 24, 2, 
        N'{"po_number":"PO-2026-001","po_date":"2026-05-28","vendor":"Sigma-Aldrich India","delivery_address":"Narayana Lab, Phase 1, Bangalore","items":[{"product":"Ethanol Absolute AR 500ml","cas":"64-17-5","cat":"1.00983.1000","hsn":"22071011","qty":3,"price":5000.00},{"product":"Acetonitrile HPLC Grade 2.5L","cas":"75-05-8","cat":"1.00030.2500","hsn":"29269000","qty":2,"price":15000.00}]}',
        DATEADD(second, 5, DATEADD(minute, -119, GETUTCDATE())), DATEADD(second, 25, DATEADD(minute, -119, GETUTCDATE())), 20000, 1,
        DATEADD(minute, -119, GETUTCDATE()), 'SYSTEM'
    ),
    (
        2, 2, 24, 3, 94.20, 24, 2, 
        N'{"po_number":"PO-2026-002","po_date":"2026-05-28","vendor":"Merck Life Science","delivery_address":"Narayana Lab, Phase 1, Bangalore","items":[{"product":"Sodium Chloride For Analysis 1kg","cas":"7647-14-5","cat":"1.06404.1000","hsn":"25010020","qty":10,"price":2000.00},{"product":"Methanol Gradient Grade 2.5L","cas":"67-56-1","cat":"1.06007.2500","hsn":"29051100","qty":2,"price":50000.00}]}',
        DATEADD(second, 10, DATEADD(minute, -88, GETUTCDATE())), DATEADD(second, 130, DATEADD(minute, -88, GETUTCDATE())), 120000, 1,
        DATEADD(minute, -88, GETUTCDATE()), 'SYSTEM'
    ),
    (
        3, 3, 26, 1, NULL, 25, 0, 
        NULL,
        DATEADD(second, 2, DATEADD(minute, -59, GETUTCDATE())), DATEADD(second, 10, DATEADD(minute, -59, GETUTCDATE())), 8000, 1,
        DATEADD(minute, -59, GETUTCDATE()), 'SYSTEM'
    );

    SET IDENTITY_INSERT dbo.pobrain_extraction_jobs OFF;
    PRINT '  → 3 extraction jobs seeded successfully';
END
ELSE
BEGIN
    PRINT '  → dbo.pobrain_extraction_jobs already has data, skipping';
END;
GO

-- ============================================================================
-- 4. SEED: dbo.pobrain_purchase_orders
-- ============================================================================
PRINT '4. Seeding dbo.pobrain_purchase_orders...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_purchase_orders)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_purchase_orders ON;

    INSERT INTO dbo.pobrain_purchase_orders (
        po_id, extraction_job_id, email_id, po_number, po_date, 
        vendor_name, vendor_email, delivery_address, gst_number, 
        cgst_number, sgst_number, igst_number, total_quantity, 
        subtotal_amount, total_tax_amount, total_amount, currency_code, 
        status_id, is_duplicate, created_at, created_by
    )
    VALUES
    (
        1, 1, 1, 'PO-2026-001', '2026-05-28', 
        'Sigma-Aldrich India', 'orders@sigmaaldrich.in', 'Narayana Research Lab, Plot 42, Electronic City Phase 1, Bangalore, KA - 560100', '29AAAAA1111A1Z1', 
        'CGST-SIGMA-992', 'SGST-SIGMA-992', NULL, 5.0000, 
        45000.00, 8100.00, 53100.00, 'INR', 
        31, 0, DATEADD(minute, -118, GETUTCDATE()), 'SYSTEM'
    ),
    (
        2, 2, 2, 'PO-2026-002', '2026-05-28', 
        'Merck Life Science', 'sales@merck.co.in', 'Narayana Research Lab, Plot 42, Electronic City Phase 1, Bangalore, KA - 560100', '27BBBBB2222B2Z2', 
        'CGST-MERCK-883', 'SGST-MERCK-883', NULL, 12.0000, 
        120000.00, 21600.00, 141600.00, 'INR', 
        31, 0, DATEADD(minute, -85, GETUTCDATE()), 'SYSTEM'
    );

    SET IDENTITY_INSERT dbo.pobrain_purchase_orders OFF;
    PRINT '  → 2 purchase order headers seeded successfully';
END
ELSE
BEGIN
    PRINT '  → dbo.pobrain_purchase_orders already has data, skipping';
END;
GO

-- ============================================================================
-- 5. SEED: dbo.pobrain_purchase_order_line_items
-- ============================================================================
PRINT '5. Seeding dbo.pobrain_purchase_order_line_items...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_purchase_order_line_items)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_purchase_order_line_items ON;

    INSERT INTO dbo.pobrain_purchase_order_line_items (
        line_item_id, po_id, line_number, product_name, cas_number, 
        cat_number, hsn_code, quantity, unit_of_measure, unit_price, 
        amount, cgst_rate, cgst_amount, sgst_rate, sgst_amount, 
        igst_rate, igst_amount, created_at
    )
    VALUES
    -- PO-2026-001 Line items
    (
        1, 1, 1, 'Ethanol Absolute AR 500ml', '64-17-5', 
        '1.00983.1000', '22071011', 3.0000, 'Bottles', 5000.0000, 
        15000.00, 9.00, 1350.00, 9.00, 1350.00, 
        NULL, NULL, DATEADD(minute, -118, GETUTCDATE())
    ),
    (
        2, 1, 2, 'Acetonitrile HPLC Grade 2.5L', '75-05-8', 
        '1.00030.2500', '29269000', 2.0000, 'Cans', 15000.0000, 
        30000.00, 9.00, 2700.00, 9.00, 2700.00, 
        NULL, NULL, DATEADD(minute, -118, GETUTCDATE())
    ),
    
    -- PO-2026-002 Line items
    (
        3, 2, 1, 'Sodium Chloride For Analysis 1kg', '7647-14-5', 
        '1.06404.1000', '25010020', 10.0000, 'Packs', 2000.0000, 
        20000.00, 9.00, 1800.00, 9.00, 1800.00, 
        NULL, NULL, DATEADD(minute, -85, GETUTCDATE())
    ),
    (
        4, 2, 2, 'Methanol Gradient Grade 2.5L', '67-56-1', 
        '1.06007.2500', '29051100', 2.0000, 'Cans', 50000.0000, 
        100000.00, 9.00, 9000.00, 9.00, 9000.00, 
        NULL, NULL, DATEADD(minute, -85, GETUTCDATE())
    );

    SET IDENTITY_INSERT dbo.pobrain_purchase_order_line_items OFF;
    PRINT '  → 4 purchase order line items seeded successfully';
END
ELSE
BEGIN
    PRINT '  → dbo.pobrain_purchase_order_line_items already has data, skipping';
END;
GO

-- ============================================================================
-- 6. SEED: dbo.pobrain_workflow_steps
-- ============================================================================
PRINT '6. Seeding dbo.pobrain_workflow_steps...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_workflow_steps)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_workflow_steps ON;

    INSERT INTO dbo.pobrain_workflow_steps (
        step_id, email_id, stage_id, status_id, service_name, 
        queue_position, started_at, completed_at, duration_ms, remarks, created_at
    )
    VALUES
    -- Email 1 workflow
    (1, 1, 1, 43, 'EmailPollingService', 1, DATEADD(second, 1, DATEADD(minute, -119, GETUTCDATE())), DATEADD(second, 3, DATEADD(minute, -119, GETUTCDATE())), 2000, 'Email received and UID cataloged', DATEADD(minute, -119, GETUTCDATE())),
    (2, 1, 2, 43, 'EmailPollingService', NULL, DATEADD(second, 3, DATEADD(minute, -119, GETUTCDATE())), DATEADD(second, 4, DATEADD(minute, -119, GETUTCDATE())), 1000, 'Attachment PO_10243.pdf detected', DATEADD(minute, -119, GETUTCDATE())),
    (3, 1, 3, 43, 'EmailPollingService', NULL, DATEADD(second, 4, DATEADD(minute, -119, GETUTCDATE())), DATEADD(second, 6, DATEADD(minute, -119, GETUTCDATE())), 2000, 'PDF successfully downloaded to storage', DATEADD(minute, -119, GETUTCDATE())),
    (4, 1, 5, 43, 'ExtractionService', 1, DATEADD(second, 6, DATEADD(minute, -119, GETUTCDATE())), DATEADD(second, 26, DATEADD(minute, -119, GETUTCDATE())), 20000, 'Extracted data successfully using Custom RegEx Engine', DATEADD(minute, -119, GETUTCDATE())),
    (5, 1, 6, 43, 'ExtractionService', NULL, DATEADD(second, 26, DATEADD(minute, -119, GETUTCDATE())), DATEADD(second, 27, DATEADD(minute, -119, GETUTCDATE())), 1000, 'Extraction confidence (98.5%) validation passed', DATEADD(minute, -119, GETUTCDATE())),
    (6, 1, 7, 43, 'DatabaseService', NULL, DATEADD(second, 27, DATEADD(minute, -119, GETUTCDATE())), DATEADD(second, 28, DATEADD(minute, -119, GETUTCDATE())), 1000, 'Duplicate check passed. Unique PO.', DATEADD(minute, -119, GETUTCDATE())),
    (7, 1, 8, 43, 'DatabaseService', NULL, DATEADD(second, 28, DATEADD(minute, -119, GETUTCDATE())), DATEADD(second, 30, DATEADD(minute, -119, GETUTCDATE())), 2000, 'Saved purchase orders & line items to DB', DATEADD(minute, -119, GETUTCDATE())),
    
    -- Email 2 workflow (OCR Flow)
    (8, 2, 1, 43, 'EmailPollingService', 2, DATEADD(second, 1, DATEADD(minute, -88, GETUTCDATE())), DATEADD(second, 3, DATEADD(minute, -88, GETUTCDATE())), 2000, 'Email received and UID cataloged', DATEADD(minute, -88, GETUTCDATE())),
    (9, 2, 2, 43, 'EmailPollingService', NULL, DATEADD(second, 3, DATEADD(minute, -88, GETUTCDATE())), DATEADD(second, 4, DATEADD(minute, -88, GETUTCDATE())), 1000, 'Attachment PO_A5821_Scanned.pdf detected', DATEADD(minute, -88, GETUTCDATE())),
    (10, 2, 3, 43, 'EmailPollingService', NULL, DATEADD(second, 4, DATEADD(minute, -88, GETUTCDATE())), DATEADD(second, 8, DATEADD(minute, -88, GETUTCDATE())), 4000, 'Scanned PDF downloaded (1.24 MB)', DATEADD(minute, -88, GETUTCDATE())),
    (11, 2, 4, 43, 'OCRService', 1, DATEADD(second, 8, DATEADD(minute, -88, GETUTCDATE())), DATEADD(second, 48, DATEADD(minute, -88, GETUTCDATE())), 40000, 'OCR completed. Extracted searchable text overlay', DATEADD(minute, -88, GETUTCDATE())),
    (12, 2, 5, 43, 'ExtractionService', 2, DATEADD(second, 48, DATEADD(minute, -88, GETUTCDATE())), DATEADD(second, 168, DATEADD(minute, -88, GETUTCDATE())), 120000, 'Extracted text successfully using Azure Form Recognizer', DATEADD(minute, -88, GETUTCDATE())),
    (13, 2, 8, 43, 'DatabaseService', NULL, DATEADD(second, 168, DATEADD(minute, -88, GETUTCDATE())), DATEADD(second, 172, DATEADD(minute, -88, GETUTCDATE())), 4000, 'Saved purchase orders & line items to DB', DATEADD(minute, -88, GETUTCDATE())),

    -- Email 3 workflow (Failure Flow)
    (14, 3, 1, 43, 'EmailPollingService', 3, DATEADD(second, 1, DATEADD(minute, -59, GETUTCDATE())), DATEADD(second, 2, DATEADD(minute, -59, GETUTCDATE())), 1000, 'Email received and UID cataloged', DATEADD(minute, -59, GETUTCDATE())),
    (15, 3, 2, 43, 'EmailPollingService', NULL, DATEADD(second, 2, DATEADD(minute, -59, GETUTCDATE())), DATEADD(second, 3, DATEADD(minute, -59, GETUTCDATE())), 1000, 'Corrupted attachment detected', DATEADD(minute, -59, GETUTCDATE())),
    (16, 3, 5, 44, 'ExtractionService', 3, DATEADD(second, 3, DATEADD(minute, -59, GETUTCDATE())), DATEADD(second, 11, DATEADD(minute, -59, GETUTCDATE())), 8000, 'Failed on extraction job. Triggered error logger.', DATEADD(minute, -59, GETUTCDATE())),

    -- Email 4 workflow (Active Flow)
    (17, 4, 1, 43, 'EmailPollingService', 4, DATEADD(second, 1, DATEADD(minute, -29, GETUTCDATE())), DATEADD(second, 2, DATEADD(minute, -29, GETUTCDATE())), 1000, 'Email received and UID cataloged', DATEADD(minute, -29, GETUTCDATE())),
    (18, 4, 2, 42, 'EmailPollingService', NULL, DATEADD(second, 2, DATEADD(minute, -29, GETUTCDATE())), NULL, NULL, 'Currently detecting attachments in background', DATEADD(minute, -29, GETUTCDATE()));

    SET IDENTITY_INSERT dbo.pobrain_workflow_steps OFF;
    PRINT '  → 18 workflow execution steps seeded successfully';
END
ELSE
BEGIN
    PRINT '  → dbo.pobrain_workflow_steps already has data, skipping';
END;
GO

-- ============================================================================
-- 7. SEED: dbo.pobrain_processing_logs
-- ============================================================================
PRINT '7. Seeding dbo.pobrain_processing_logs...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_processing_logs)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_processing_logs ON;

    INSERT INTO dbo.pobrain_processing_logs (
        log_id, email_id, log_level_id, sender_email, email_subject, 
        message, module_name, correlation_id, logged_at
    )
    VALUES
    -- Email 1 Log Stream
    (1, 1, 2, 'orders@sigmaaldrich.in', 'Purchase Order PO-2026-001', 'Incoming email detected. Message UID: MSG-UID-10243-SIGMA', 'EmailPollingService', 'CORR-SIGMA-10243', DATEADD(second, 1, DATEADD(minute, -119, GETUTCDATE()))),
    (2, 1, 2, 'orders@sigmaaldrich.in', 'Purchase Order PO-2026-001', 'Successfully fetched 1 PDF attachment: PO_10243.pdf (145.28 KB)', 'EmailPollingService', 'CORR-SIGMA-10243', DATEADD(second, 3, DATEADD(minute, -119, GETUTCDATE()))),
    (3, 1, 1, 'orders@sigmaaldrich.in', 'Purchase Order PO-2026-001', 'Calculating PDF MD5 checksum. Hash = e3b0c442...', 'ExtractionService', 'CORR-SIGMA-10243', DATEADD(second, 6, DATEADD(minute, -119, GETUTCDATE()))),
    (4, 1, 2, 'orders@sigmaaldrich.in', 'Purchase Order PO-2026-001', 'PDF is native text-based. Skipping OCR pipeline.', 'ExtractionService', 'CORR-SIGMA-10243', DATEADD(second, 7, DATEADD(minute, -119, GETUTCDATE()))),
    (5, 1, 2, 'orders@sigmaaldrich.in', 'Purchase Order PO-2026-001', 'Successfully parsed 2 line-items using Custom RegEx Engine with confidence score: 98.50%', 'ExtractionService', 'CORR-SIGMA-10243', DATEADD(second, 26, DATEADD(minute, -119, GETUTCDATE()))),
    (6, 1, 2, 'orders@sigmaaldrich.in', 'Purchase Order PO-2026-001', 'GSTIN (29AAAAA1111A1Z1) format check: PASSED', 'DatabaseService', 'CORR-SIGMA-10243', DATEADD(second, 27, DATEADD(minute, -119, GETUTCDATE()))),
    (7, 1, 2, 'orders@sigmaaldrich.in', 'Purchase Order PO-2026-001', 'Database transaction successfully saved PO: PO-2026-001', 'DatabaseService', 'CORR-SIGMA-10243', DATEADD(second, 30, DATEADD(minute, -119, GETUTCDATE()))),
    
    -- Email 2 Log Stream
    (8, 2, 2, 'sales@merck.co.in', 'ORDER INQUIRY - PO-2026-002 - URGENT', 'Incoming email detected. Message UID: MSG-UID-58210-MERCK', 'EmailPollingService', 'CORR-MERCK-58210', DATEADD(second, 1, DATEADD(minute, -88, GETUTCDATE()))),
    (9, 2, 3, 'sales@merck.co.in', 'ORDER INQUIRY - PO-2026-002 - URGENT', 'Attachment file is large (1.24 MB). Scanned PDF detected. Routing to OCR...', 'EmailPollingService', 'CORR-MERCK-58210', DATEADD(second, 4, DATEADD(minute, -88, GETUTCDATE()))),
    (10, 2, 2, 'sales@merck.co.in', 'ORDER INQUIRY - PO-2026-002 - URGENT', 'Tesseract OCR pipeline finished processing 2 pages in 40.0 seconds', 'OCRService', 'CORR-MERCK-58210', DATEADD(second, 48, DATEADD(minute, -88, GETUTCDATE()))),
    (11, 2, 2, 'sales@merck.co.in', 'ORDER INQUIRY - PO-2026-002 - URGENT', 'Form Recognizer model (v3.1) returned successful output. Confidence: 94.20%', 'ExtractionService', 'CORR-MERCK-58210', DATEADD(second, 168, DATEADD(minute, -88, GETUTCDATE()))),
    (12, 2, 2, 'sales@merck.co.in', 'ORDER INQUIRY - PO-2026-002 - URGENT', 'Database transaction successfully saved PO: PO-2026-002', 'DatabaseService', 'CORR-MERCK-58210', DATEADD(second, 172, DATEADD(minute, -88, GETUTCDATE()))),

    -- Email 3 Log Stream (Errors)
    (13, 3, 2, 'procurement@unreliablevendor.com', 'New PO attachment', 'Incoming email detected. Message UID: MSG-UID-99321-FAILED', 'EmailPollingService', 'CORR-FAIL-99321', DATEADD(second, 1, DATEADD(minute, -59, GETUTCDATE()))),
    (14, 3, 3, 'procurement@unreliablevendor.com', 'New PO attachment', 'Attachment file is extremely small (2.41 KB). Suspected corruption.', 'EmailPollingService', 'CORR-FAIL-99321', DATEADD(second, 3, DATEADD(minute, -59, GETUTCDATE()))),
    (15, 3, 4, 'procurement@unreliablevendor.com', 'New PO attachment', 'ERROR: PDF parsing failed. Expected PDF header not found. Stream aborted.', 'ExtractionService', 'CORR-FAIL-99321', DATEADD(second, 11, DATEADD(minute, -59, GETUTCDATE()))),

    -- System health monitoring logs
    (16, NULL, 2, NULL, NULL, 'Routine hourly health check executed. Health snapshot recorded.', 'HealthMonitorService', 'CORR-SYS-HEALTH', DATEADD(minute, -10, GETUTCDATE()));

    SET IDENTITY_INSERT dbo.pobrain_processing_logs OFF;
    PRINT '  → 16 processing log records seeded successfully';
END
ELSE
BEGIN
    PRINT '  → dbo.pobrain_processing_logs already has data, skipping';
END;
GO

-- ============================================================================
-- 8. SEED: dbo.pobrain_error_logs
-- ============================================================================
PRINT '8. Seeding dbo.pobrain_error_logs...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_error_logs)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_error_logs ON;

    INSERT INTO dbo.pobrain_error_logs (
        error_id, email_id, attachment_id, job_id, error_category_id, 
        error_code, error_message, stack_trace, failed_module, severity, 
        retry_attempt, is_resolved, resolved_by, resolution_notes, occurred_at, resolved_at
    )
    VALUES
    (
        1, 3, 3, 3, 1, 
        'PDF_HEADER_MISSING', 'Failed to parse corrupted_po.pdf. Expected PDF header not found.', 
        N'at PO_Brain.Extraction.PdfPigParser.ExtractText(Stream pdfStream) in e:\sources\PdfPigParser.cs:line 45\r\nat PO_Brain.Extraction.ExtractionService.ProcessAttachment(Int64 attachmentId) in e:\sources\ExtractionService.cs:line 102\r\nat PO_Brain.API.EmailProcessingService.ProcessEmail(Int64 emailId) in e:\sources\EmailProcessingService.cs:line 28', 
        'ExtractionService', 2, 
        1, 0, NULL, NULL, 
        DATEADD(minute, -58, GETUTCDATE()), NULL
    );

    SET IDENTITY_INSERT dbo.pobrain_error_logs OFF;
    PRINT '  → 1 error log records seeded successfully';
END
ELSE
BEGIN
    PRINT '  → dbo.pobrain_error_logs already has data, skipping';
END;
GO

-- ============================================================================
-- 9. SEED: dbo.pobrain_failed_transactions
-- ============================================================================
PRINT '9. Seeding dbo.pobrain_failed_transactions...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_failed_transactions)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_failed_transactions ON;

    INSERT INTO dbo.pobrain_failed_transactions (
        failed_id, email_id, extraction_job_id, po_number, po_date, 
        product_name, quantity, amount, email_from, email_date, 
        error_reason, error_category_id, is_reprocessed, reprocessed_by, 
        failed_at, reprocessed_at, created_at
    )
    VALUES
    (
        1, 3, 3, 'UNKNOWN', NULL, 
        'CHEMICAL RAW MATERIALS (SUSPECTED)', NULL, NULL, 'procurement@unreliablevendor.com', DATEADD(minute, -60, GETUTCDATE()), 
        'Failed to parse corrupted_po.pdf. Expected PDF header not found.', 1, 0, NULL, 
        DATEADD(minute, -58, GETUTCDATE()), NULL, DATEADD(minute, -58, GETUTCDATE())
    );

    SET IDENTITY_INSERT dbo.pobrain_failed_transactions OFF;
    PRINT '  → 1 failed transaction record seeded successfully';
END
ELSE
BEGIN
    PRINT '  → dbo.pobrain_failed_transactions already has data, skipping';
END;
GO

-- ============================================================================
-- 10. SEED: dbo.pobrain_audit_logs
-- ============================================================================
PRINT '10. Seeding dbo.pobrain_audit_logs...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_audit_logs)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_audit_logs ON;

    INSERT INTO dbo.pobrain_audit_logs (
        audit_id, table_name, record_id, action_type, changed_by, 
        old_values, new_values, ip_address, user_agent, correlation_id, changed_at
    )
    VALUES
    (
        1, 'pobrain_purchase_orders', 1, 'INSERT', 'SYSTEM', 
        NULL, N'{"po_id":1,"po_number":"PO-2026-001","vendor_name":"Sigma-Aldrich India","total_amount":53100.00,"status_id":31}', 
        '127.0.0.1', 'PO-Brain Backend Service Worker', 'CORR-SIGMA-10243', DATEADD(minute, -118, GETUTCDATE())
    ),
    (
        2, 'pobrain_purchase_orders', 2, 'INSERT', 'SYSTEM', 
        NULL, N'{"po_id":2,"po_number":"PO-2026-002","vendor_name":"Merck Life Science","total_amount":141600.00,"status_id":31}', 
        '127.0.0.1', 'PO-Brain Backend Service Worker', 'CORR-MERCK-58210', DATEADD(minute, -85, GETUTCDATE())
    );

    SET IDENTITY_INSERT dbo.pobrain_audit_logs OFF;
    PRINT '  → 2 audit log records seeded successfully';
END
ELSE
BEGIN
    PRINT '  → dbo.pobrain_audit_logs already has data, skipping';
END;
GO

-- ============================================================================
-- 11. SEED: dbo.pobrain_system_health_snapshots
-- ============================================================================
PRINT '11. Seeding dbo.pobrain_system_health_snapshots...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_system_health_snapshots)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_system_health_snapshots ON;

    INSERT INTO dbo.pobrain_system_health_snapshots (
        snapshot_id, component_name, health_pct, total_processed, 
        total_failed, total_pending, avg_processing_ms, snapshot_period, snapshot_at
    )
    VALUES
    -- Captures health snapshots over past 24 hours
    (1, 'Email Parser',       98.50, 152, 2, 0, 1500,  '24h', DATEADD(minute, -60, GETUTCDATE())),
    (2, 'OCR Pipeline',       88.20, 34,  4, 0, 42000, '24h', DATEADD(minute, -60, GETUTCDATE())),
    (3, 'Extraction Engine',  96.40, 148, 5, 0, 12000, '24h', DATEADD(minute, -60, GETUTCDATE())),
    
    -- Latest snapshots (10 minutes ago)
    (4, 'Email Parser',       99.20, 160, 1, 1, 1420,  '24h', DATEADD(minute, -10, GETUTCDATE())),
    (5, 'OCR Pipeline',       92.00, 38,  3, 0, 38500, '24h', DATEADD(minute, -10, GETUTCDATE())),
    (6, 'Extraction Engine',  97.10, 156, 4, 0, 10500, '24h', DATEADD(minute, -10, GETUTCDATE()));

    SET IDENTITY_INSERT dbo.pobrain_system_health_snapshots OFF;
    PRINT '  → 6 system health snapshot records seeded successfully';
END
ELSE
BEGIN
    PRINT '  → dbo.pobrain_system_health_snapshots already has data, skipping';
END;
GO

-- Re-enable foreign key constraints
EXEC sp_MSforeachtable "ALTER TABLE ? CHECK CONSTRAINT ALL";
GO

PRINT '';
PRINT '============================================================================';
PRINT '  06_sample_data.sql — Rich sample data seeded successfully';
PRINT '  Database: hyma_testdb | Prefix: dbo.pobrain_';
PRINT '============================================================================';
GO
