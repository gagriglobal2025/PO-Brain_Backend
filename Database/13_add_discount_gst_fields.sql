-- ============================================================================
-- PO-Brain Migration: Add discount and GST tracking fields
-- Database: hyma_testdb
-- Version:  1.5.0
-- Created:  2026-07-07
-- Description:
--   Adds discount and GST columns to the PO-Brain tables to store resolved
--   master and derived tax/discount values matching the ERP columns.
-- ============================================================================

USE [hyma_testdb];
GO

PRINT '============================================================================';
PRINT '  13_add_discount_gst_fields.sql — Starting migration';
PRINT '============================================================================';
GO

-- 1. Add total_discount_amount to dbo.pobrain_purchase_orders
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_purchase_orders') AND name = 'total_discount_amount')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_orders ADD total_discount_amount DECIMAL(18,2) NULL;
    PRINT '  [OK] Added pobrain_purchase_orders.total_discount_amount';
END
ELSE
    PRINT '  [SKIP] pobrain_purchase_orders.total_discount_amount already exists';
GO

-- 2. Add discount_price to dbo.pobrain_purchase_order_line_items
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_purchase_order_line_items') AND name = 'discount_price')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_order_line_items ADD discount_price DECIMAL(18,2) NULL;
    PRINT '  [OK] Added pobrain_purchase_order_line_items.discount_price';
END
ELSE
    PRINT '  [SKIP] pobrain_purchase_order_line_items.discount_price already exists';
GO

-- 3. Add gst_rate to dbo.pobrain_purchase_order_line_items
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_purchase_order_line_items') AND name = 'gst_rate')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_order_line_items ADD gst_rate DECIMAL(5,2) NULL;
    PRINT '  [OK] Added pobrain_purchase_order_line_items.gst_rate';
END
ELSE
    PRINT '  [SKIP] pobrain_purchase_order_line_items.gst_rate already exists';
GO

-- 4. Add gst_amount to dbo.pobrain_purchase_order_line_items
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_purchase_order_line_items') AND name = 'gst_amount')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_order_line_items ADD gst_amount DECIMAL(18,2) NULL;
    PRINT '  [OK] Added pobrain_purchase_order_line_items.gst_amount';
END
ELSE
    PRINT '  [SKIP] pobrain_purchase_order_line_items.gst_amount already exists';
GO

PRINT '============================================================================';
PRINT '  13_add_discount_gst_fields.sql — Migration complete';
PRINT '============================================================================';
GO
