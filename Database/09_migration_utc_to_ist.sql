-- ============================================================================
-- 09_migration_utc_to_ist.sql
-- Converts every pobrain_* DEFAULT constraint that uses GETUTCDATE() to Indian
-- Standard Time (UTC+5:30, no DST) by wrapping it in DATEADD(MINUTE, 330, ...).
--
-- Scope: dbo.pobrain_* tables ONLY. The legacy ERP tables (tblClientOrder,
-- tblComment, SAT_WebOrder_Tracking, tblRegistration) are deliberately untouched.
--
-- Idempotent: re-running is safe — constraints already on IST are skipped because
-- their definition no longer matches the GETUTCDATE-only pattern.
--
-- NOTE: this changes DEFAULTS for NEW rows only; it does NOT shift timestamps in
-- existing rows. Existing test rows keep their original (UTC) values.
-- ============================================================================
USE [hyma_testdb];
GO
SET NOCOUNT ON;

DECLARE @sql NVARCHAR(MAX) = N'';

SELECT @sql = @sql +
    'ALTER TABLE ' + QUOTENAME(s.name) + '.' + QUOTENAME(t.name) +
        ' DROP CONSTRAINT ' + QUOTENAME(dc.name) + ';' + CHAR(13) + CHAR(10) +
    'ALTER TABLE ' + QUOTENAME(s.name) + '.' + QUOTENAME(t.name) +
        ' ADD CONSTRAINT ' + QUOTENAME(dc.name) +
        ' DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())) FOR ' + QUOTENAME(c.name) + ';' + CHAR(13) + CHAR(10)
FROM sys.default_constraints dc
JOIN sys.tables   t ON dc.parent_object_id = t.object_id
JOIN sys.schemas  s ON t.schema_id = s.schema_id
JOIN sys.columns  c ON c.object_id = t.object_id AND c.column_id = dc.parent_column_id
WHERE t.name LIKE 'pobrain[_]%'
  AND dc.definition LIKE '%getutcdate%'
  AND dc.definition NOT LIKE '%dateadd%';   -- skip ones already converted to IST

IF LEN(@sql) = 0
    PRINT 'No UTC default constraints found — nothing to convert (already IST).';
ELSE
BEGIN
    PRINT @sql;
    EXEC sp_executesql @sql;
    PRINT '============================================================================';
    PRINT '  pobrain_* DEFAULT constraints converted from UTC to IST (+330 min).';
    PRINT '============================================================================';
END
GO
