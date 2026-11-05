-- ============================================================================
-- PO-Brain Migration: Update Password Reset to use OTP
-- Database: hyma_testdb
-- Version:  1.2.0
-- Created:  2026-06-02
-- Description:
--   Updates the pobrain_password_resets table to use 6-digit OTP instead of
--   token-based reset. Removes token_hash column and adds OTP-related columns.
--
--   SCOPE: Only touches dbo.pobrain_password_resets
--   SAFE:  Idempotent — checks for existing columns before making changes
--
-- Run order: After 07_migration_add_auth_tables.sql
-- ============================================================================

USE [hyma_testdb];
GO

PRINT '============================================================================';
PRINT '  08_migration_add_otp_password_reset.sql — Starting migration';
PRINT '============================================================================';
GO

-- ============================================================================
-- STEP 1: Remove old unique constraint on token_hash
-- ============================================================================
IF EXISTS (SELECT * FROM sys.objects WHERE name = 'UQ_pobrain_password_resets_token' AND type = 'UQ')
BEGIN
    ALTER TABLE dbo.pobrain_password_resets
        DROP CONSTRAINT UQ_pobrain_password_resets_token;
    PRINT '  [OK] Dropped UQ_pobrain_password_resets_token constraint';
END
ELSE
    PRINT '  [SKIP] UQ_pobrain_password_resets_token not found';
GO

-- ============================================================================
-- STEP 1B: Drop old expires_at column (no longer used, replaced by otp_expires_at)
-- ============================================================================
IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.pobrain_password_resets') AND name = 'expires_at')
BEGIN
    ALTER TABLE dbo.pobrain_password_resets
        DROP COLUMN expires_at;
    PRINT '  [OK] Dropped old expires_at column';
END
ELSE
    PRINT '  [SKIP] expires_at column not found';
GO

-- ============================================================================
-- STEP 2: Drop token_hash column if it exists
-- ============================================================================
IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.pobrain_password_resets') AND name = 'token_hash')
BEGIN
    ALTER TABLE dbo.pobrain_password_resets
        DROP COLUMN token_hash;
    PRINT '  [OK] Dropped token_hash column';
END
ELSE
    PRINT '  [SKIP] token_hash column not found';
GO

-- ============================================================================
-- STEP 3: Add OTP-related columns if they don't exist
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.pobrain_password_resets') AND name = 'otp_code')
BEGIN
    ALTER TABLE dbo.pobrain_password_resets
        ADD otp_code VARCHAR(6) NOT NULL DEFAULT '000000';
    PRINT '  [OK] Added otp_code column';
END
ELSE
    PRINT '  [SKIP] otp_code column already exists';
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.pobrain_password_resets') AND name = 'otp_expires_at')
BEGIN
    ALTER TABLE dbo.pobrain_password_resets
        ADD otp_expires_at DATETIME2(3) NOT NULL DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE()));
    PRINT '  [OK] Added otp_expires_at column';
END
ELSE
    PRINT '  [SKIP] otp_expires_at column already exists';
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.pobrain_password_resets') AND name = 'max_attempts')
BEGIN
    ALTER TABLE dbo.pobrain_password_resets
        ADD max_attempts INT NOT NULL DEFAULT 3;
    PRINT '  [OK] Added max_attempts column';
END
ELSE
    PRINT '  [SKIP] max_attempts column already exists';
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.pobrain_password_resets') AND name = 'attempt_count')
BEGIN
    ALTER TABLE dbo.pobrain_password_resets
        ADD attempt_count INT NOT NULL DEFAULT 0;
    PRINT '  [OK] Added attempt_count column';
END
ELSE
    PRINT '  [SKIP] attempt_count column already exists';
GO

-- ============================================================================
-- STEP 4: Add unique constraint on user_id (only one active reset per user)
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'UQ_pobrain_password_resets_user_id' AND type = 'UQ')
BEGIN
    ALTER TABLE dbo.pobrain_password_resets
        ADD CONSTRAINT UQ_pobrain_password_resets_user_id UNIQUE (user_id);
    PRINT '  [OK] Added UQ_pobrain_password_resets_user_id constraint';
END
ELSE
    PRINT '  [SKIP] UQ_pobrain_password_resets_user_id constraint already exists';
GO

-- ============================================================================
-- STEP 5: Drop any existing data (optional cleanup)
-- ============================================================================
IF EXISTS (SELECT * FROM dbo.pobrain_password_resets WHERE is_used = 0)
BEGIN
    DELETE FROM dbo.pobrain_password_resets WHERE is_used = 0;
    PRINT '  [OK] Cleaned up unused password reset records';
END
ELSE
    PRINT '  [SKIP] No unused password reset records to clean';
GO

PRINT '';
PRINT '============================================================================';
PRINT '  08_migration_add_otp_password_reset.sql — Migration complete';
PRINT '  Changes: token_hash → otp_code, otp_expires_at, max_attempts, attempt_count';
PRINT '  Constraints: UQ(user_id) for single active reset per user';
PRINT '============================================================================';
GO
