-- ============================================================================
-- PO-Brain Migration: Add master-data lookup fields to PO-Brain tables
-- Database: hyma_testdb
-- Version:  1.3.0
-- Created:  2026-06-16
-- Description:
--   Adds columns to the PO-Brain tables so the values we now resolve for the
--   ERP (tblClientOrder) are ALSO persisted in the PO-Brain schema:
--     • pobrain_purchase_orders.company_code   -> customer CompanyCode (tblRegistration)
--     • pobrain_purchase_order_line_items.pack_size  -> pack size read off the PO
--     • pobrain_purchase_order_line_items.pack_code  -> resolved Avra2020_PackingCodes.PackCode
--     • pobrain_purchase_order_line_items.item_code  -> resolved ItemMst.ItemCode (by CAS)
--     • pobrain_purchase_order_line_items.discount   -> customer default discount (tblRegistration)
--
--   SCOPE: Only PO-Brain (pobrain_*) tables. The ERP tables (tblClientOrder,
--          tblComment, SAT_WebOrder_Tracking, tblRegistration, ItemMst,
--          Avra2020_PackingCodes) are FIXED and are NOT modified here.
--   SAFE:  Idempotent — checks for each column before adding it.
--
-- Run order: After 09_migration_utc_to_ist.sql
-- ============================================================================

USE [hyma_testdb];
GO

PRINT '============================================================================';
PRINT '  10_add_master_lookup_fields.sql — Starting migration';
PRINT '============================================================================';
GO

-- ── pobrain_purchase_orders.company_code ────────────────────────────────────
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_purchase_orders') AND name = 'company_code')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_orders ADD company_code NVARCHAR(50) NULL;
    PRINT '  [OK] Added pobrain_purchase_orders.company_code';
END
ELSE
    PRINT '  [SKIP] pobrain_purchase_orders.company_code already exists';
GO

-- ── pobrain_purchase_orders.branch_location ─────────────────────────────────
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_purchase_orders') AND name = 'branch_location')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_orders ADD branch_location NVARCHAR(50) NULL;
    PRINT '  [OK] Added pobrain_purchase_orders.branch_location';
END
ELSE
    PRINT '  [SKIP] pobrain_purchase_orders.branch_location already exists';
GO

-- ── pobrain_purchase_order_line_items.pack_size ─────────────────────────────
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_purchase_order_line_items') AND name = 'pack_size')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_order_line_items ADD pack_size VARCHAR(100) NULL;
    PRINT '  [OK] Added pobrain_purchase_order_line_items.pack_size';
END
ELSE
    PRINT '  [SKIP] pobrain_purchase_order_line_items.pack_size already exists';
GO

-- ── pobrain_purchase_order_line_items.pack_code ─────────────────────────────
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_purchase_order_line_items') AND name = 'pack_code')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_order_line_items ADD pack_code VARCHAR(50) NULL;
    PRINT '  [OK] Added pobrain_purchase_order_line_items.pack_code';
END
ELSE
    PRINT '  [SKIP] pobrain_purchase_order_line_items.pack_code already exists';
GO

-- ── pobrain_purchase_order_line_items.item_code ─────────────────────────────
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_purchase_order_line_items') AND name = 'item_code')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_order_line_items ADD item_code NVARCHAR(50) NULL;
    PRINT '  [OK] Added pobrain_purchase_order_line_items.item_code';
END
ELSE
    PRINT '  [SKIP] pobrain_purchase_order_line_items.item_code already exists';
GO

-- ── pobrain_purchase_order_line_items.discount ──────────────────────────────
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_purchase_order_line_items') AND name = 'discount')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_order_line_items ADD discount INT NULL;
    PRINT '  [OK] Added pobrain_purchase_order_line_items.discount';
END
ELSE
    PRINT '  [SKIP] pobrain_purchase_order_line_items.discount already exists';
GO

PRINT '';
PRINT '============================================================================';
PRINT '  10_add_master_lookup_fields.sql — Migration complete';
PRINT '  Added: company_code (PO), pack_size/pack_code/item_code/discount (line item)';
PRINT '============================================================================';
GO
