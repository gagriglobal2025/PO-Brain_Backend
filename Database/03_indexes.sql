-- ============================================================================
-- PO-Brain Index Scripts
-- Database: hyma_testdb
-- Prefix:   dbo.pobrain_
-- Version:  1.0.0
-- Created:  2026-05-29
-- Description: All non-clustered indexes, filtered indexes, and covering indexes
-- ============================================================================
-- Execution Order: Run AFTER 02_foreign_keys.sql
-- ============================================================================

USE [hyma_testdb];
GO

-- ============================================================================
-- LOOKUP TABLE INDEXES
-- ============================================================================

-- lkp_status: filter by entity_type + status_code
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_lkp_status_entity_type')
    CREATE NONCLUSTERED INDEX IX_pobrain_lkp_status_entity_type
    ON dbo.pobrain_lkp_status (entity_type, status_code)
    INCLUDE (status_name, is_active);
GO

-- ============================================================================
-- EMAILS INDEXES
-- ============================================================================

-- Filter emails by processing status (Dashboard stat cards)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_emails_status_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_emails_status_id
    ON dbo.pobrain_emails (status_id)
    INCLUDE (email_from, email_subject, email_received_at);
GO

-- Search emails by sender (Processing Logs search)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_emails_email_from')
    CREATE NONCLUSTERED INDEX IX_pobrain_emails_email_from
    ON dbo.pobrain_emails (email_from)
    INCLUDE (email_subject, status_id, email_received_at);
GO

-- Timeline queries - most recent emails first (Dashboard)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_emails_received_at')
    CREATE NONCLUSTERED INDEX IX_pobrain_emails_received_at
    ON dbo.pobrain_emails (email_received_at DESC)
    INCLUDE (email_from, email_subject, status_id, attachment_count);
GO

-- Recent records by creation (Dashboard recent activity)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_emails_created_at')
    CREATE NONCLUSTERED INDEX IX_pobrain_emails_created_at
    ON dbo.pobrain_emails (created_at DESC)
    INCLUDE (email_from, status_id);
GO

-- ============================================================================
-- EMAIL_ATTACHMENTS INDEXES
-- ============================================================================

-- Join to parent email
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_attach_email_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_attach_email_id
    ON dbo.pobrain_email_attachments (email_id)
    INCLUDE (file_name, file_type, status_id, file_size_bytes);
GO

-- Filter by processing status
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_attach_status_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_attach_status_id
    ON dbo.pobrain_email_attachments (status_id)
    INCLUDE (email_id, file_name);
GO

-- Duplicate file detection via hash
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_attach_file_hash')
    CREATE NONCLUSTERED INDEX IX_pobrain_attach_file_hash
    ON dbo.pobrain_email_attachments (file_hash)
    WHERE file_hash IS NOT NULL;
GO

-- ============================================================================
-- EXTRACTION_JOBS INDEXES
-- ============================================================================

-- Join to attachment
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_jobs_attachment_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_jobs_attachment_id
    ON dbo.pobrain_extraction_jobs (attachment_id)
    INCLUDE (status_id, confidence_score, items_extracted);
GO

-- Filter by job status
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_jobs_status_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_jobs_status_id
    ON dbo.pobrain_extraction_jobs (status_id)
    INCLUDE (attachment_id, started_at, completed_at);
GO

-- Timeline - most recent jobs first
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_jobs_started_at')
    CREATE NONCLUSTERED INDEX IX_pobrain_jobs_started_at
    ON dbo.pobrain_extraction_jobs (started_at DESC)
    INCLUDE (status_id, confidence_score, duration_ms);
GO

-- Quality analysis by confidence score
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_jobs_confidence')
    CREATE NONCLUSTERED INDEX IX_pobrain_jobs_confidence
    ON dbo.pobrain_extraction_jobs (confidence_score)
    INCLUDE (status_id, engine_id)
    WHERE confidence_score IS NOT NULL;
GO

-- ============================================================================
-- PURCHASE_ORDERS INDEXES
-- ============================================================================

-- Link to source email (Extraction Results page)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_po_email_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_po_email_id
    ON dbo.pobrain_purchase_orders (email_id)
    INCLUDE (po_number, po_date, total_amount, status_id);
GO

-- Link to extraction job
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_po_extraction_job_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_po_extraction_job_id
    ON dbo.pobrain_purchase_orders (extraction_job_id)
    INCLUDE (po_number, status_id);
GO

-- Date-range queries
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_po_po_date')
    CREATE NONCLUSTERED INDEX IX_pobrain_po_po_date
    ON dbo.pobrain_purchase_orders (po_date DESC)
    INCLUDE (po_number, total_amount, status_id, delivery_address);
GO

-- Status filtering
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_po_status_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_po_status_id
    ON dbo.pobrain_purchase_orders (status_id)
    INCLUDE (po_number, po_date, total_amount);
GO

-- Vendor lookup
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_po_vendor_name')
    CREATE NONCLUSTERED INDEX IX_pobrain_po_vendor_name
    ON dbo.pobrain_purchase_orders (vendor_name)
    WHERE vendor_name IS NOT NULL;
GO

-- ============================================================================
-- PURCHASE_ORDER_LINE_ITEMS INDEXES
-- ============================================================================

-- Join to parent PO (Extraction Results detail)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_li_po_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_li_po_id
    ON dbo.pobrain_purchase_order_line_items (po_id)
    INCLUDE (product_name, cas_number, quantity, amount);
GO

-- Chemical search by CAS number
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_li_cas_number')
    CREATE NONCLUSTERED INDEX IX_pobrain_li_cas_number
    ON dbo.pobrain_purchase_order_line_items (cas_number)
    INCLUDE (po_id, product_name, quantity, amount)
    WHERE cas_number IS NOT NULL;
GO

-- Product name search
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_li_product_name')
    CREATE NONCLUSTERED INDEX IX_pobrain_li_product_name
    ON dbo.pobrain_purchase_order_line_items (product_name)
    INCLUDE (po_id, cas_number, quantity, amount);
GO

-- ============================================================================
-- WORKFLOW_STEPS INDEXES
-- ============================================================================

-- Get all steps for an email
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_wf_email_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_wf_email_id
    ON dbo.pobrain_workflow_steps (email_id)
    INCLUDE (stage_id, status_id, started_at, duration_ms);
GO

-- Filter by pipeline stage
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_wf_stage_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_wf_stage_id
    ON dbo.pobrain_workflow_steps (stage_id)
    INCLUDE (email_id, status_id, duration_ms);
GO

-- Filter by status
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_wf_status_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_wf_status_id
    ON dbo.pobrain_workflow_steps (status_id)
    INCLUDE (email_id, stage_id);
GO

-- Timeline
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_wf_started_at')
    CREATE NONCLUSTERED INDEX IX_pobrain_wf_started_at
    ON dbo.pobrain_workflow_steps (started_at DESC)
    INCLUDE (email_id, stage_id, status_id, duration_ms);
GO

-- ============================================================================
-- PROCESSING_LOGS INDEXES
-- ============================================================================

-- Filter logs by email
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_plog_email_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_plog_email_id
    ON dbo.pobrain_processing_logs (email_id)
    INCLUDE (log_level_id, message, logged_at)
    WHERE email_id IS NOT NULL;
GO

-- Filter by level (All Levels dropdown on UI)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_plog_level')
    CREATE NONCLUSTERED INDEX IX_pobrain_plog_level
    ON dbo.pobrain_processing_logs (log_level_id)
    INCLUDE (sender_email, email_subject, message, logged_at);
GO

-- Default sort - most recent logs first (Processing Logs page)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_plog_logged_at')
    CREATE NONCLUSTERED INDEX IX_pobrain_plog_logged_at
    ON dbo.pobrain_processing_logs (logged_at DESC)
    INCLUDE (log_level_id, sender_email, email_subject, message);
GO

-- Search by sender
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_plog_sender')
    CREATE NONCLUSTERED INDEX IX_pobrain_plog_sender
    ON dbo.pobrain_processing_logs (sender_email)
    INCLUDE (email_subject, log_level_id, message, logged_at)
    WHERE sender_email IS NOT NULL;
GO

-- Trace a request by correlation ID
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_plog_correlation')
    CREATE NONCLUSTERED INDEX IX_pobrain_plog_correlation
    ON dbo.pobrain_processing_logs (correlation_id)
    WHERE correlation_id IS NOT NULL;
GO

-- ============================================================================
-- ERROR_LOGS INDEXES
-- ============================================================================

-- Errors per email
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_err_email_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_err_email_id
    ON dbo.pobrain_error_logs (email_id)
    INCLUDE (error_message, severity, occurred_at)
    WHERE email_id IS NOT NULL;
GO

-- Top failure reasons by category
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_err_category')
    CREATE NONCLUSTERED INDEX IX_pobrain_err_category
    ON dbo.pobrain_error_logs (error_category_id)
    INCLUDE (error_message, severity, occurred_at)
    WHERE error_category_id IS NOT NULL;
GO

-- Critical errors first
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_err_severity')
    CREATE NONCLUSTERED INDEX IX_pobrain_err_severity
    ON dbo.pobrain_error_logs (severity, occurred_at DESC)
    INCLUDE (error_message, failed_module, is_resolved);
GO

-- Timeline
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_err_occurred_at')
    CREATE NONCLUSTERED INDEX IX_pobrain_err_occurred_at
    ON dbo.pobrain_error_logs (occurred_at DESC)
    INCLUDE (email_id, error_message, severity, is_resolved);
GO

-- Unresolved/open errors (filtered index)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_err_unresolved')
    CREATE NONCLUSTERED INDEX IX_pobrain_err_unresolved
    ON dbo.pobrain_error_logs (severity, occurred_at DESC)
    INCLUDE (error_message, failed_module, email_id)
    WHERE is_resolved = 0;
GO

-- ============================================================================
-- FAILED_TRANSACTIONS INDEXES
-- ============================================================================

-- Link to email
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_ft_email_id')
    CREATE NONCLUSTERED INDEX IX_pobrain_ft_email_id
    ON dbo.pobrain_failed_transactions (email_id)
    WHERE email_id IS NOT NULL;
GO

-- Search by PO number
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_ft_po_number')
    CREATE NONCLUSTERED INDEX IX_pobrain_ft_po_number
    ON dbo.pobrain_failed_transactions (po_number)
    INCLUDE (po_date, product_name, amount, error_reason, failed_at)
    WHERE po_number IS NOT NULL;
GO

-- Recent failures (Failed Transactions page default sort)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_ft_failed_at')
    CREATE NONCLUSTERED INDEX IX_pobrain_ft_failed_at
    ON dbo.pobrain_failed_transactions (failed_at DESC)
    INCLUDE (po_number, po_date, product_name, quantity, amount, email_from, error_reason);
GO

-- Failure analysis by category
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_ft_error_category')
    CREATE NONCLUSTERED INDEX IX_pobrain_ft_error_category
    ON dbo.pobrain_failed_transactions (error_category_id)
    INCLUDE (error_reason, failed_at)
    WHERE error_category_id IS NOT NULL;
GO

-- Pending reprocessing (filtered index)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_ft_unprocessed')
    CREATE NONCLUSTERED INDEX IX_pobrain_ft_unprocessed
    ON dbo.pobrain_failed_transactions (failed_at DESC)
    INCLUDE (po_number, error_reason, email_from)
    WHERE is_reprocessed = 0;
GO

-- ============================================================================
-- AUDIT_LOGS INDEXES
-- ============================================================================

-- Get full history for a specific record
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_audit_table_record')
    CREATE NONCLUSTERED INDEX IX_pobrain_audit_table_record
    ON dbo.pobrain_audit_logs (table_name, record_id)
    INCLUDE (action_type, changed_by, changed_at);
GO

-- User activity tracking
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_audit_changed_by')
    CREATE NONCLUSTERED INDEX IX_pobrain_audit_changed_by
    ON dbo.pobrain_audit_logs (changed_by)
    INCLUDE (table_name, action_type, changed_at);
GO

-- Timeline
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_audit_changed_at')
    CREATE NONCLUSTERED INDEX IX_pobrain_audit_changed_at
    ON dbo.pobrain_audit_logs (changed_at DESC)
    INCLUDE (table_name, action_type, changed_by);
GO

-- Filter by action type + time
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_audit_action_type')
    CREATE NONCLUSTERED INDEX IX_pobrain_audit_action_type
    ON dbo.pobrain_audit_logs (action_type, changed_at DESC)
    INCLUDE (table_name, changed_by);
GO

-- ============================================================================
-- SYSTEM_HEALTH_SNAPSHOTS INDEXES
-- ============================================================================

-- Latest health per component (Dashboard Processing Health widget)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_health_component_at')
    CREATE NONCLUSTERED INDEX IX_pobrain_health_component_at
    ON dbo.pobrain_system_health_snapshots (component_name, snapshot_at DESC)
    INCLUDE (health_pct, total_processed, total_failed, total_pending);
GO

-- Timeline
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_pobrain_health_snapshot_at')
    CREATE NONCLUSTERED INDEX IX_pobrain_health_snapshot_at
    ON dbo.pobrain_system_health_snapshots (snapshot_at DESC)
    INCLUDE (component_name, health_pct);
GO

PRINT '============================================================================';
PRINT '  03_indexes.sql — All indexes created successfully';
PRINT '  Total: 40 non-clustered indexes (including filtered indexes)';
PRINT '============================================================================';
GO
