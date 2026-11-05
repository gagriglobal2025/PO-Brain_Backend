-- ============================================================================
-- PO-Brain Seed Data
-- Database: hyma_testdb
-- Prefix:   dbo.pobrain_
-- Version:  1.0.0
-- Created:  2026-05-29
-- Description: Lookup table seed data for all reference/master tables
-- ============================================================================
-- Execution Order: Run AFTER 03_indexes.sql
-- ============================================================================

USE [hyma_testdb];
GO

-- ============================================================================
-- 1. SEED: pobrain_lkp_status
--    Centralized status master organized by entity_type
-- ============================================================================
PRINT 'Seeding pobrain_lkp_status...';

-- Only seed if table is empty (safe for re-runs)
IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_lkp_status)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_lkp_status ON;

    INSERT INTO dbo.pobrain_lkp_status (status_id, status_code, status_name, entity_type, is_active)
    VALUES
    -- EMAIL statuses (1-10)
    (1,  'EMAIL_RECEIVED',      'Received',             'EMAIL',        1),
    (2,  'EMAIL_PROCESSING',    'Processing',           'EMAIL',        1),
    (3,  'EMAIL_COMPLETED',     'Completed',            'EMAIL',        1),
    (4,  'EMAIL_FAILED',        'Failed',               'EMAIL',        1),
    (5,  'EMAIL_SKIPPED',       'Skipped',              'EMAIL',        1),
    (6,  'EMAIL_RETRYING',      'Retrying',             'EMAIL',        1),

    -- ATTACHMENT statuses (11-20)
    (11, 'ATTACH_PENDING',      'Pending',              'ATTACHMENT',   1),
    (12, 'ATTACH_PARSING',      'Parsing',              'ATTACHMENT',   1),
    (13, 'ATTACH_PARSED',       'Parsed',               'ATTACHMENT',   1),
    (14, 'ATTACH_PARSE_FAILED', 'Parse Failed',         'ATTACHMENT',   1),
    (15, 'ATTACH_OCR_PENDING',  'OCR Pending',          'ATTACHMENT',   1),
    (16, 'ATTACH_OCR_COMPLETED','OCR Completed',        'ATTACHMENT',   1),
    (17, 'ATTACH_OCR_FAILED',   'OCR Failed',           'ATTACHMENT',   1),

    -- EXTRACTION statuses (21-30)
    (21, 'EXTR_QUEUED',         'Queued',               'EXTRACTION',   1),
    (22, 'EXTR_EXTRACTING',     'Extracting',           'EXTRACTION',   1),
    (23, 'EXTR_EXTRACTED',      'Extracted',            'EXTRACTION',   1),
    (24, 'EXTR_VALIDATED',      'Validated',            'EXTRACTION',   1),
    (25, 'EXTR_VALIDATION_FAIL','Validation Failed',    'EXTRACTION',   1),
    (26, 'EXTR_FAILED',         'Extraction Failed',    'EXTRACTION',   1),

    -- PO statuses (31-40)
    (31, 'PO_ACTIVE',           'Active',               'PO',           1),
    (32, 'PO_DUPLICATE',        'Duplicate',            'PO',           1),
    (33, 'PO_ARCHIVED',         'Archived',             'PO',           1),
    (34, 'PO_PENDING_REVIEW',   'Pending Review',       'PO',           1),

    -- WORKFLOW statuses (41-50)
    (41, 'WF_QUEUED',           'Queued',               'WORKFLOW',     1),
    (42, 'WF_IN_PROGRESS',     'In Progress',          'WORKFLOW',     1),
    (43, 'WF_COMPLETED',       'Completed',            'WORKFLOW',     1),
    (44, 'WF_FAILED',          'Failed',               'WORKFLOW',     1),
    (45, 'WF_TIMED_OUT',       'Timed Out',            'WORKFLOW',     1),
    (46, 'WF_SKIPPED',         'Skipped',              'WORKFLOW',     1);

    SET IDENTITY_INSERT dbo.pobrain_lkp_status OFF;

    PRINT '  → Inserted 28 status records';
END
ELSE
BEGIN
    PRINT '  → Table already has data, skipping seed';
END;
GO

-- ============================================================================
-- 2. SEED: pobrain_lkp_log_level
--    Log severity levels matching the Processing Logs UI
-- ============================================================================
PRINT 'Seeding pobrain_lkp_log_level...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_lkp_log_level)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_lkp_log_level ON;

    INSERT INTO dbo.pobrain_lkp_log_level (log_level_id, level_code, level_name, severity_order)
    VALUES
    (1, 'DEBUG',    'Debug',        1),
    (2, 'INFO',     'Information',  2),
    (3, 'WARN',     'Warning',      3),
    (4, 'ERROR',    'Error',        4),
    (5, 'FATAL',    'Fatal',        5);

    SET IDENTITY_INSERT dbo.pobrain_lkp_log_level OFF;

    PRINT '  → Inserted 5 log level records';
END
ELSE
BEGIN
    PRINT '  → Table already has data, skipping seed';
END;
GO

-- ============================================================================
-- 3. SEED: pobrain_lkp_processing_stage
--    Pipeline stages in execution order
-- ============================================================================
PRINT 'Seeding pobrain_lkp_processing_stage...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_lkp_processing_stage)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_lkp_processing_stage ON;

    INSERT INTO dbo.pobrain_lkp_processing_stage (stage_id, stage_code, stage_name, stage_order, is_active)
    VALUES
    (1, 'EMAIL_RECEIVE',        'Email Reception',          10,     1),
    (2, 'ATTACHMENT_DETECT',    'Attachment Detection',     20,     1),
    (3, 'PDF_DOWNLOAD',         'PDF Download',             30,     1),
    (4, 'OCR_PROCESS',          'OCR Processing',           40,     1),
    (5, 'DATA_EXTRACTION',      'Data Extraction',          50,     1),
    (6, 'DATA_VALIDATION',      'Data Validation',          60,     1),
    (7, 'DUPLICATE_CHECK',      'Duplicate Check',          70,     1),
    (8, 'SAVE_TO_DB',           'Save to Database',         80,     1),
    (9, 'NOTIFICATION',         'Send Notification',        90,     1),
    (10,'CLEANUP',              'Cleanup & Finalize',       100,    1);

    SET IDENTITY_INSERT dbo.pobrain_lkp_processing_stage OFF;

    PRINT '  → Inserted 10 processing stage records';
END
ELSE
BEGIN
    PRINT '  → Table already has data, skipping seed';
END;
GO

-- ============================================================================
-- 4. SEED: pobrain_lkp_error_category
--    Error classification taxonomy
-- ============================================================================
PRINT 'Seeding pobrain_lkp_error_category...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_lkp_error_category)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_lkp_error_category ON;

    INSERT INTO dbo.pobrain_lkp_error_category (error_category_id, category_code, category_name, is_active)
    VALUES
    (1,  'PARSE_ERROR',             'PDF Parsing Error',                1),
    (2,  'VALIDATION_ERROR',        'Data Validation Error',            1),
    (3,  'DUPLICATE_DETECTION',     'Duplicate PO Detected',            1),
    (4,  'OCR_FAILURE',             'OCR Processing Failure',           1),
    (5,  'NETWORK_ERROR',           'Network / Connectivity Error',     1),
    (6,  'TIMEOUT_ERROR',           'Processing Timeout',               1),
    (7,  'FORMAT_ERROR',            'Invalid File Format',              1),
    (8,  'MISSING_DATA',            'Required Data Missing',            1),
    (9,  'GST_VALIDATION',         'GST Number Validation Failed',     1),
    (10, 'HSN_MISMATCH',           'HSN Code Mismatch',                1),
    (11, 'ADDRESS_PARSE_FAIL',     'Delivery Address Parse Failure',   1),
    (12, 'EMAIL_PARSE_FAIL',       'Email Body Parsing Failed',        1),
    (13, 'AUTHENTICATION_ERROR',   'Mail Server Authentication',       1),
    (14, 'UNKNOWN_ERROR',          'Unknown / Unclassified Error',     1);

    SET IDENTITY_INSERT dbo.pobrain_lkp_error_category OFF;

    PRINT '  → Inserted 14 error category records';
END
ELSE
BEGIN
    PRINT '  → Table already has data, skipping seed';
END;
GO

-- ============================================================================
-- 5. SEED: pobrain_lkp_parsing_engine
--    Extraction engine registry
-- ============================================================================
PRINT 'Seeding pobrain_lkp_parsing_engine...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_lkp_parsing_engine)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_lkp_parsing_engine ON;

    INSERT INTO dbo.pobrain_lkp_parsing_engine (engine_id, engine_name, engine_version, is_active)
    VALUES
    (1, 'Custom RegEx Parser',          '1.0.0',    1),
    (2, 'Tesseract OCR',                '5.3.0',    1),
    (3, 'Azure Form Recognizer',        '3.1',      1),
    (4, 'iTextSharp PDF Parser',        '7.2.0',    1),
    (5, 'PdfPig Text Extractor',        '0.1.8',    1);

    SET IDENTITY_INSERT dbo.pobrain_lkp_parsing_engine OFF;

    PRINT '  → Inserted 5 parsing engine records';
END
ELSE
BEGIN
    PRINT '  → Table already has data, skipping seed';
END;
GO

-- ============================================================================
-- 6. SEED: pobrain_users
--    Default application accounts.
--
--    Default passwords (bcrypt cost 12):
--      SYSTEM   → System@1234  (is_active = 0, cannot log in via UI)
--      admin    → Admin@1234
--      operator → Operator@1234
--      viewer   → Viewer@1234
-- ============================================================================
PRINT 'Seeding pobrain_users...';

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_users)
BEGIN
    SET IDENTITY_INSERT dbo.pobrain_users ON;

    INSERT INTO dbo.pobrain_users
        (user_id, username, email, password_hash, full_name, role, is_active, created_by)
    VALUES
    (1, 'SYSTEM',   'system@pobrain.local',   '$2b$12$/ILHSV0d86HvchWBDJAVFOOytjUnyslvWURo/LXfMdk/x45UDhiCm', 'Pipeline Service Account', 'system',   0, 'SYSTEM'),
    (2, 'admin',    'admin@pobrain.local',     '$2b$12$mYFTWc23Nld6dPTljb3SeOzn.5YpEks2QtvWWrygDzbLc7Muk69Ma', 'PO-Brain Administrator',   'admin',    1, 'SYSTEM'),
    (3, 'operator', 'operator@pobrain.local',  '$2b$12$47MQJ0C.xzjrlRNw45byBOrH0zxwT73z8IKnnfwwM6YwFALEBHFFO', 'PO-Brain Operator',        'operator', 1, 'SYSTEM'),
    (4, 'viewer',   'viewer@pobrain.local',    '$2b$12$0E3Xwx4caGVfJ7VboWHHNuHFPsGwTXvfXn57FlKnxFMQBSKMhJviG', 'PO-Brain Viewer',          'viewer',   1, 'SYSTEM');

    SET IDENTITY_INSERT dbo.pobrain_users OFF;

    PRINT '  → 4 default users seeded (update password_hash before production use)';
END
ELSE
BEGIN
    PRINT '  → Table already has data, skipping seed';
END;
GO

PRINT '';
PRINT '============================================================================';
PRINT '  04_seed_data.sql — All lookup data seeded successfully';
PRINT '  Total: 66 seed records across 6 tables';
PRINT '============================================================================';
GO
