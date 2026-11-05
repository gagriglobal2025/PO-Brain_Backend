-- ============================================================================
-- PO-Brain Migration: Remove master-lookup fields from PO-Brain line items
-- Database: hyma_testdb
-- Version:  1.4.0
-- Created:  2026-06-18
-- Description:
--   Reverses part of 10_add_master_lookup_fields.sql. The pack/item/discount
--   enrichment is no longer persisted on the PO-Brain line-item table:
--     • pobrain_purchase_order_line_items.pack_size   (dropped)
--     • pobrain_purchase_order_line_items.pack_code   (dropped)
--     • pobrain_purchase_order_line_items.item_code   (dropped)
--     • pobrain_purchase_order_line_items.discount    (dropped)
--
--   The resolved Hyma catalog number now lands in the existing cat_number
--   column (see extractor change), not item_code. The ERP tblClientOrder still
--   carries PackCode/PackSize/Discount/CatalogNo — only the PO-Brain mirror
--   columns are removed here.
--
--   SCOPE: Only dbo.pobrain_purchase_order_line_items. ERP tables untouched.
--   SAFE:  Idempotent — checks for each column (and its default) before dropping.
--
-- Run order: After 10_add_master_lookup_fields.sql
-- ============================================================================

USE [hyma_testdb];
GO

PRINT '============================================================================';
PRINT '  11_drop_line_item_lookup_fields.sql — Starting migration';
PRINT '============================================================================';
GO

-- Drops a column, first removing any default constraint bound to it.
IF OBJECT_ID('tempdb..#drop_col') IS NOT NULL DROP PROCEDURE #drop_col;
GO
CREATE PROCEDURE #drop_col @col SYSNAME
AS
BEGIN
    DECLARE @tbl SYSNAME = N'dbo.pobrain_purchase_order_line_items';
    IF NOT EXISTS (SELECT * FROM sys.columns
                   WHERE object_id = OBJECT_ID(@tbl) AND name = @col)
    BEGIN
        PRINT '  [SKIP] ' + @col + ' does not exist';
        RETURN;
    END

    DECLARE @dc SYSNAME;
    SELECT @dc = dc.name
    FROM sys.default_constraints dc
    JOIN sys.columns c ON c.object_id = dc.parent_object_id AND c.column_id = dc.parent_column_id
    WHERE dc.parent_object_id = OBJECT_ID(@tbl) AND c.name = @col;

    IF @dc IS NOT NULL
        EXEC('ALTER TABLE ' + @tbl + ' DROP CONSTRAINT ' + @dc);

    EXEC('ALTER TABLE ' + @tbl + ' DROP COLUMN ' + @col);
    PRINT '  [OK] Dropped ' + @col;
END
GO

EXEC #drop_col 'pack_size';
EXEC #drop_col 'pack_code';
EXEC #drop_col 'item_code';
EXEC #drop_col 'discount';
GO

DROP PROCEDURE #drop_col;
GO

PRINT '';
PRINT '============================================================================';
PRINT '  11_drop_line_item_lookup_fields.sql — Migration complete';
PRINT '  Dropped: pack_size, pack_code, item_code, discount (line items)';
PRINT '============================================================================';
GO
