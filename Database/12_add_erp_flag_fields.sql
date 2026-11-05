-- ============================================================================
-- PO-Brain Migration: Add ERP tracking columns to pobrain_purchase_orders
-- Database: hyma_testdb
-- Version:  1.4.0
-- Created:  2026-07-07
-- Description:
--   Adds columns to dbo.pobrain_purchase_orders to log if the order was written
--   to the legacy ERP tables and links back to the generated ERP OrderID.
-- ============================================================================

USE [hyma_testdb];
GO

PRINT '============================================================================';
PRINT '  12_add_erp_flag_fields.sql — Starting migration';
PRINT '============================================================================';
GO

-- 1. Add is_erp_inserted (BIT, default 0, NOT NULL)
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_purchase_orders') AND name = 'is_erp_inserted')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_orders ADD is_erp_inserted BIT NOT NULL CONSTRAINT DF_pobrain_po_is_erp_inserted DEFAULT (0);
    PRINT '  [OK] Added pobrain_purchase_orders.is_erp_inserted';
END
ELSE
    PRINT '  [SKIP] pobrain_purchase_orders.is_erp_inserted already exists';
GO

-- 2. Add erp_order_id (BIGINT, NULL)
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_purchase_orders') AND name = 'erp_order_id')
BEGIN
    ALTER TABLE dbo.pobrain_purchase_orders ADD erp_order_id BIGINT NULL;
    PRINT '  [OK] Added pobrain_purchase_orders.erp_order_id';
END
ELSE
    PRINT '  [SKIP] pobrain_purchase_orders.erp_order_id already exists';
GO

PRINT '============================================================================';
PRINT '  12_add_erp_flag_fields.sql — Migration complete';
PRINT '============================================================================';
GO
