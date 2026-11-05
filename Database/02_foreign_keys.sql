-- ============================================================================
-- PO-Brain Foreign Key Constraints
-- Database: hyma_testdb
-- Prefix:   dbo.pobrain_
-- Version:  1.0.0
-- Created:  2026-05-29
-- Description: All FK constraints linking the pobrain_ tables
-- ============================================================================
-- Execution Order: Run AFTER 01_create_tables.sql
-- ============================================================================

USE [hyma_testdb];
GO

-- ============================================================================
-- EMAILS → STATUS LOOKUP
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_emails_status')
BEGIN
    ALTER TABLE dbo.pobrain_emails
        ADD CONSTRAINT FK_pobrain_emails_status
        FOREIGN KEY (status_id) REFERENCES dbo.pobrain_lkp_status (status_id);
END;
GO

-- ============================================================================
-- EMAIL_ATTACHMENTS → EMAILS, STATUS
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_attachments_email')
BEGIN
    ALTER TABLE dbo.pobrain_email_attachments
        ADD CONSTRAINT FK_pobrain_attachments_email
        FOREIGN KEY (email_id) REFERENCES dbo.pobrain_emails (email_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_attachments_status')
BEGIN
    ALTER TABLE dbo.pobrain_email_attachments
        ADD CONSTRAINT FK_pobrain_attachments_status
        FOREIGN KEY (status_id) REFERENCES dbo.pobrain_lkp_status (status_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_attachments_ocr_status')
BEGIN
    ALTER TABLE dbo.pobrain_email_attachments
        ADD CONSTRAINT FK_pobrain_attachments_ocr_status
        FOREIGN KEY (ocr_status_id) REFERENCES dbo.pobrain_lkp_status (status_id);
END;
GO

-- ============================================================================
-- EXTRACTION_JOBS → ATTACHMENTS, STATUS, ENGINE
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_jobs_attachment')
BEGIN
    ALTER TABLE dbo.pobrain_extraction_jobs
        ADD CONSTRAINT FK_pobrain_jobs_attachment
        FOREIGN KEY (attachment_id) REFERENCES dbo.pobrain_email_attachments (attachment_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_jobs_status')
BEGIN
    ALTER TABLE dbo.pobrain_extraction_jobs
        ADD CONSTRAINT FK_pobrain_jobs_status
        FOREIGN KEY (status_id) REFERENCES dbo.pobrain_lkp_status (status_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_jobs_engine')
BEGIN
    ALTER TABLE dbo.pobrain_extraction_jobs
        ADD CONSTRAINT FK_pobrain_jobs_engine
        FOREIGN KEY (engine_id) REFERENCES dbo.pobrain_lkp_parsing_engine (engine_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_jobs_validation_status')
BEGIN
    ALTER TABLE dbo.pobrain_extraction_jobs
        ADD CONSTRAINT FK_pobrain_jobs_validation_status
        FOREIGN KEY (validation_status_id) REFERENCES dbo.pobrain_lkp_status (status_id);
END;
GO

-- ============================================================================
-- PURCHASE_ORDERS → EXTRACTION_JOBS, EMAILS, STATUS
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_po_extraction_job')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_orders
        ADD CONSTRAINT FK_pobrain_po_extraction_job
        FOREIGN KEY (extraction_job_id) REFERENCES dbo.pobrain_extraction_jobs (job_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_po_email')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_orders
        ADD CONSTRAINT FK_pobrain_po_email
        FOREIGN KEY (email_id) REFERENCES dbo.pobrain_emails (email_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_po_status')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_orders
        ADD CONSTRAINT FK_pobrain_po_status
        FOREIGN KEY (status_id) REFERENCES dbo.pobrain_lkp_status (status_id);
END;
GO

-- ============================================================================
-- PURCHASE_ORDER_LINE_ITEMS → PURCHASE_ORDERS
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_li_purchase_order')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_order_line_items
        ADD CONSTRAINT FK_pobrain_li_purchase_order
        FOREIGN KEY (po_id) REFERENCES dbo.pobrain_purchase_orders (po_id);
END;
GO

-- ============================================================================
-- WORKFLOW_STEPS → EMAILS, STAGE, STATUS
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_wf_email')
BEGIN
    ALTER TABLE dbo.pobrain_workflow_steps
        ADD CONSTRAINT FK_pobrain_wf_email
        FOREIGN KEY (email_id) REFERENCES dbo.pobrain_emails (email_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_wf_stage')
BEGIN
    ALTER TABLE dbo.pobrain_workflow_steps
        ADD CONSTRAINT FK_pobrain_wf_stage
        FOREIGN KEY (stage_id) REFERENCES dbo.pobrain_lkp_processing_stage (stage_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_wf_status')
BEGIN
    ALTER TABLE dbo.pobrain_workflow_steps
        ADD CONSTRAINT FK_pobrain_wf_status
        FOREIGN KEY (status_id) REFERENCES dbo.pobrain_lkp_status (status_id);
END;
GO

-- ============================================================================
-- PROCESSING_LOGS → EMAILS, LOG_LEVEL
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_plog_email')
BEGIN
    ALTER TABLE dbo.pobrain_processing_logs
        ADD CONSTRAINT FK_pobrain_plog_email
        FOREIGN KEY (email_id) REFERENCES dbo.pobrain_emails (email_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_plog_level')
BEGIN
    ALTER TABLE dbo.pobrain_processing_logs
        ADD CONSTRAINT FK_pobrain_plog_level
        FOREIGN KEY (log_level_id) REFERENCES dbo.pobrain_lkp_log_level (log_level_id);
END;
GO

-- ============================================================================
-- ERROR_LOGS → EMAILS, ATTACHMENTS, JOBS, ERROR_CATEGORY
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_err_email')
BEGIN
    ALTER TABLE dbo.pobrain_error_logs
        ADD CONSTRAINT FK_pobrain_err_email
        FOREIGN KEY (email_id) REFERENCES dbo.pobrain_emails (email_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_err_attachment')
BEGIN
    ALTER TABLE dbo.pobrain_error_logs
        ADD CONSTRAINT FK_pobrain_err_attachment
        FOREIGN KEY (attachment_id) REFERENCES dbo.pobrain_email_attachments (attachment_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_err_job')
BEGIN
    ALTER TABLE dbo.pobrain_error_logs
        ADD CONSTRAINT FK_pobrain_err_job
        FOREIGN KEY (job_id) REFERENCES dbo.pobrain_extraction_jobs (job_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_err_category')
BEGIN
    ALTER TABLE dbo.pobrain_error_logs
        ADD CONSTRAINT FK_pobrain_err_category
        FOREIGN KEY (error_category_id) REFERENCES dbo.pobrain_lkp_error_category (error_category_id);
END;
GO

-- ============================================================================
-- FAILED_TRANSACTIONS → EMAILS, EXTRACTION_JOBS, ERROR_CATEGORY
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_ft_email')
BEGIN
    ALTER TABLE dbo.pobrain_failed_transactions
        ADD CONSTRAINT FK_pobrain_ft_email
        FOREIGN KEY (email_id) REFERENCES dbo.pobrain_emails (email_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_ft_extraction_job')
BEGIN
    ALTER TABLE dbo.pobrain_failed_transactions
        ADD CONSTRAINT FK_pobrain_ft_extraction_job
        FOREIGN KEY (extraction_job_id) REFERENCES dbo.pobrain_extraction_jobs (job_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_ft_error_category')
BEGIN
    ALTER TABLE dbo.pobrain_failed_transactions
        ADD CONSTRAINT FK_pobrain_ft_error_category
        FOREIGN KEY (error_category_id) REFERENCES dbo.pobrain_lkp_error_category (error_category_id);
END;
GO

-- ============================================================================
-- USERS — action columns in operational tables
-- ============================================================================

-- resolved_by: a human user who marked an error as resolved
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_err_resolved_by')
BEGIN
    ALTER TABLE dbo.pobrain_error_logs
        ADD CONSTRAINT FK_pobrain_err_resolved_by
        FOREIGN KEY (resolved_by) REFERENCES dbo.pobrain_users (username);
END;
GO

-- reprocessed_by: a human user who triggered reprocessing of a failed transaction
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_ft_reprocessed_by')
BEGIN
    ALTER TABLE dbo.pobrain_failed_transactions
        ADD CONSTRAINT FK_pobrain_ft_reprocessed_by
        FOREIGN KEY (reprocessed_by) REFERENCES dbo.pobrain_users (username);
END;
GO

-- ============================================================================
-- PASSWORD_RESETS → USERS
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_pwr_user')
BEGIN
    ALTER TABLE dbo.pobrain_password_resets
        ADD CONSTRAINT FK_pobrain_pwr_user
        FOREIGN KEY (user_id) REFERENCES dbo.pobrain_users (user_id);
END;
GO

PRINT '============================================================================';
PRINT '  02_foreign_keys.sql — All FK constraints created successfully';
PRINT '  Total: 25 foreign key constraints';
PRINT '============================================================================';
GO
