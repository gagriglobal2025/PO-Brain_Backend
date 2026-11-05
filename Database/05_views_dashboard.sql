-- ============================================================================
-- PO-Brain Dashboard & Page Views
-- Database: hyma_testdb
-- Prefix:   dbo.pobrain_
-- Version:  1.0.0
-- Created:  2026-05-29
-- Description: All consolidated views to power the PO-Brain UI screens:
--              1. Dashboard Stats
--              2. Recent Extractions
--              3. Processing Health snaps
--              4. Extraction Results
--              5. Failed Transactions
--              6. Processing Logs
-- ============================================================================
-- Execution Order: Run AFTER 04_seed_data.sql
-- ============================================================================

USE [hyma_testdb];
GO

-- ============================================================================
-- VIEW 1: dbo.pobrain_vw_dashboard_stats
--         Powers the 4 KPI stat cards + success rate at the top of the dashboard.
-- ============================================================================
IF EXISTS (SELECT * FROM sys.views WHERE object_id = OBJECT_ID(N'dbo.pobrain_vw_dashboard_stats'))
    DROP VIEW dbo.pobrain_vw_dashboard_stats;
GO

CREATE VIEW dbo.pobrain_vw_dashboard_stats AS
SELECT 
    COUNT(e.email_id) AS TotalEmails,
    SUM(CASE WHEN s.status_code = 'EMAIL_COMPLETED' THEN 1 ELSE 0 END) AS Processed,
    SUM(CASE WHEN s.status_code = 'EMAIL_FAILED' THEN 1 ELSE 0 END) AS Failed,
    SUM(CASE WHEN s.status_code IN ('EMAIL_RECEIVED', 'EMAIL_PROCESSING', 'EMAIL_RETRYING') THEN 1 ELSE 0 END) AS Pending,
    CAST(
        CASE 
            WHEN COUNT(e.email_id) = 0 THEN 0.00
            ELSE (SUM(CASE WHEN s.status_code = 'EMAIL_COMPLETED' THEN 1 ELSE 0 END) * 100.0) / COUNT(e.email_id)
        END 
        AS DECIMAL(5,2)
    ) AS SuccessRate
FROM dbo.pobrain_emails e
JOIN dbo.pobrain_lkp_status s ON e.status_id = s.status_id;
GO

-- ============================================================================
-- VIEW 2: dbo.pobrain_vw_recent_extractions
--         Powers the "Recent Extractions" widget on the Dashboard.
-- ============================================================================
IF EXISTS (SELECT * FROM sys.views WHERE object_id = OBJECT_ID(N'dbo.pobrain_vw_recent_extractions'))
    DROP VIEW dbo.pobrain_vw_recent_extractions;
GO

CREATE VIEW dbo.pobrain_vw_recent_extractions AS
SELECT 
    po.po_id,
    po.po_number,
    po.po_date,
    po.vendor_name,
    po.total_amount,
    e.email_from,
    s.status_name AS status_display_name,
    s.status_code,
    po.created_at
FROM dbo.pobrain_purchase_orders po
JOIN dbo.pobrain_emails e ON po.email_id = e.email_id
JOIN dbo.pobrain_lkp_status s ON po.status_id = s.status_id;
GO

-- ============================================================================
-- VIEW 3: dbo.pobrain_vw_processing_health
--         Powers the "Processing Health" components showing component performance.
-- ============================================================================
IF EXISTS (SELECT * FROM sys.views WHERE object_id = OBJECT_ID(N'dbo.pobrain_vw_processing_health'))
    DROP VIEW dbo.pobrain_vw_processing_health;
GO

CREATE VIEW dbo.pobrain_vw_processing_health AS
WITH LatestSnapshots AS (
    SELECT 
        snapshot_id,
        component_name,
        health_pct,
        total_processed,
        total_failed,
        total_pending,
        avg_processing_ms,
        snapshot_period,
        snapshot_at,
        ROW_NUMBER() OVER (PARTITION BY component_name ORDER BY snapshot_at DESC) as rn
    FROM dbo.pobrain_system_health_snapshots
)
SELECT 
    snapshot_id,
    component_name,
    health_pct,
    total_processed,
    total_failed,
    total_pending,
    avg_processing_ms,
    snapshot_period,
    snapshot_at
FROM LatestSnapshots
WHERE rn = 1;
GO

-- ============================================================================
-- VIEW 4: dbo.pobrain_vw_extraction_results
--         Powers the "Extraction Results" page (Master-Detail PO details).
-- ============================================================================
IF EXISTS (SELECT * FROM sys.views WHERE object_id = OBJECT_ID(N'dbo.pobrain_vw_extraction_results'))
    DROP VIEW dbo.pobrain_vw_extraction_results;
GO

CREATE VIEW dbo.pobrain_vw_extraction_results AS
SELECT 
    po.po_id,
    li.line_item_id,
    po.po_number,
    po.po_date,
    li.product_name,
    li.cas_number,
    li.cat_number,
    li.hsn_code,
    li.quantity,
    li.unit_of_measure,
    li.unit_price,
    li.amount AS line_amount,
    po.total_amount AS po_total_amount,
    po.delivery_address,
    po.gst_number,
    po.cgst_number,
    po.sgst_number,
    po.igst_number,
    s.status_name AS po_status_name,
    s.status_code AS po_status_code,
    e.email_from,
    e.email_received_at,
    po.created_at
FROM dbo.pobrain_purchase_order_line_items li
JOIN dbo.pobrain_purchase_orders po ON li.po_id = po.po_id
JOIN dbo.pobrain_emails e ON po.email_id = e.email_id
JOIN dbo.pobrain_lkp_status s ON po.status_id = s.status_id;
GO

-- ============================================================================
-- VIEW 5: dbo.pobrain_vw_failed_transactions
--         Powers the "Failed Transactions" screen.
-- ============================================================================
IF EXISTS (SELECT * FROM sys.views WHERE object_id = OBJECT_ID(N'dbo.pobrain_vw_failed_transactions'))
    DROP VIEW dbo.pobrain_vw_failed_transactions;
GO

CREATE VIEW dbo.pobrain_vw_failed_transactions AS
SELECT 
    ft.failed_id,
    ft.email_id,
    ft.extraction_job_id,
    ft.po_number,
    ft.po_date,
    ft.product_name,
    ft.quantity,
    ft.amount,
    ft.email_from,
    ft.email_date,
    ft.error_reason,
    ec.category_name AS error_category_name,
    ec.category_code AS error_category_code,
    ft.is_reprocessed,
    ft.reprocessed_by,
    ft.failed_at,
    ft.reprocessed_at,
    ft.created_at,
    ft.updated_at
FROM dbo.pobrain_failed_transactions ft
LEFT JOIN dbo.pobrain_lkp_error_category ec ON ft.error_category_id = ec.error_category_id;
GO

-- ============================================================================
-- VIEW 6: dbo.pobrain_vw_processing_logs
--         Powers the "Processing Logs" screen with live log streams.
-- ============================================================================
IF EXISTS (SELECT * FROM sys.views WHERE object_id = OBJECT_ID(N'dbo.pobrain_vw_processing_logs'))
    DROP VIEW dbo.pobrain_vw_processing_logs;
GO

CREATE VIEW dbo.pobrain_vw_processing_logs AS
SELECT 
    pl.log_id,
    pl.email_id,
    ll.level_code AS log_level_code,
    ll.level_name AS log_level_name,
    ll.severity_order,
    pl.sender_email,
    pl.email_subject,
    pl.message,
    pl.module_name,
    pl.correlation_id,
    pl.logged_at
FROM dbo.pobrain_processing_logs pl
JOIN dbo.pobrain_lkp_log_level ll ON pl.log_level_id = ll.log_level_id;
GO

PRINT '============================================================================';
PRINT '  05_views_dashboard.sql — All 6 UI views created successfully';
PRINT '  Database: hyma_testdb | Prefix: dbo.pobrain_';
PRINT '============================================================================';
GO
