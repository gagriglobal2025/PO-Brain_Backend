-- ============================================================================
-- PO-Brain Migration: Add Authentication Tables
-- Database: hyma_testdb
-- Version:  1.1.0
-- Created:  2026-06-01
-- Description:
--   Adds pobrain_users and pobrain_password_resets tables plus the FK
--   constraints that link existing operational tables to pobrain_users.
--
--   SCOPE: Only touches dbo.pobrain_* objects — no other tables are altered.
--   SAFE:  All statements are guarded with IF NOT EXISTS; re-running is safe.
--
-- Run order: After 06_sample_data.sql on an existing deployment.
--            For a fresh deployment, the schema files 01–06 already include
--            these objects — do NOT run this file on top of a fresh deploy.
-- ============================================================================

USE [hyma_testdb];
GO

PRINT '============================================================================';
PRINT '  07_migration_add_auth_tables.sql — Starting migration';
PRINT '============================================================================';
GO

-- ============================================================================
-- STEP 1: Create pobrain_users
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_users') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_users
    (
        user_id                 INT             IDENTITY(1,1)   NOT NULL,
        username                VARCHAR(100)                    NOT NULL,
        email                   VARCHAR(320)                    NOT NULL,
        password_hash           VARCHAR(255)                    NOT NULL,
        full_name               NVARCHAR(200)                   NULL,
        role                    VARCHAR(30)                     NOT NULL    CONSTRAINT DF_pobrain_users_role          DEFAULT ('viewer'),
        is_active               BIT                             NOT NULL    CONSTRAINT DF_pobrain_users_is_active     DEFAULT (1),
        last_login_at           DATETIME2(3)                    NULL,
        failed_login_attempts   INT                             NOT NULL    CONSTRAINT DF_pobrain_users_failed_logins DEFAULT (0),
        locked_until            DATETIME2(3)                    NULL,
        created_at              DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_users_created_at   DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),
        updated_at              DATETIME2(3)                    NULL,
        created_by              VARCHAR(100)                    NOT NULL    CONSTRAINT DF_pobrain_users_created_by   DEFAULT ('SYSTEM'),

        CONSTRAINT PK_pobrain_users          PRIMARY KEY CLUSTERED (user_id),
        CONSTRAINT UQ_pobrain_users_username UNIQUE (username),
        CONSTRAINT UQ_pobrain_users_email    UNIQUE (email),
        CONSTRAINT CK_pobrain_users_role     CHECK (role IN ('admin', 'operator', 'viewer', 'system'))
    );
    PRINT '  [OK] Created dbo.pobrain_users';
END
ELSE
    PRINT '  [SKIP] dbo.pobrain_users already exists';
GO

-- ============================================================================
-- STEP 2: Create pobrain_password_resets
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_password_resets') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_password_resets
    (
        reset_id        INT             IDENTITY(1,1)   NOT NULL,
        user_id         INT                             NOT NULL,
        otp_code        VARCHAR(6)                      NOT NULL,
        otp_expires_at  DATETIME2(3)                    NOT NULL,
        max_attempts    INT                             NOT NULL    CONSTRAINT DF_pobrain_pwr_max_attempts DEFAULT (3),
        attempt_count   INT                             NOT NULL    CONSTRAINT DF_pobrain_pwr_attempt_count DEFAULT (0),
        is_used         BIT                             NOT NULL    CONSTRAINT DF_pobrain_pwr_is_used       DEFAULT (0),
        used_at         DATETIME2(3)                    NULL,
        requested_ip    VARCHAR(45)                     NULL,
        created_at      DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_pwr_created_at   DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),

        CONSTRAINT PK_pobrain_password_resets       PRIMARY KEY CLUSTERED (reset_id),
        CONSTRAINT UQ_pobrain_password_resets_user_id UNIQUE (user_id)
    );
    PRINT '  [OK] Created dbo.pobrain_password_resets';
END
ELSE
    PRINT '  [SKIP] dbo.pobrain_password_resets already exists';
GO

-- ============================================================================
-- STEP 3: FK — pobrain_password_resets.user_id → pobrain_users.user_id
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_pwr_user')
BEGIN
    ALTER TABLE dbo.pobrain_password_resets
        ADD CONSTRAINT FK_pobrain_pwr_user
        FOREIGN KEY (user_id) REFERENCES dbo.pobrain_users (user_id);
    PRINT '  [OK] FK_pobrain_pwr_user added';
END
ELSE
    PRINT '  [SKIP] FK_pobrain_pwr_user already exists';
GO

-- ============================================================================
-- STEP 4: FK — pobrain_error_logs.resolved_by → pobrain_users.username
--   resolved_by is VARCHAR(100) NULL — the UNIQUE constraint on username
--   allows this VARCHAR-to-VARCHAR FK. NULL values are allowed.
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_err_resolved_by')
BEGIN
    ALTER TABLE dbo.pobrain_error_logs
        ADD CONSTRAINT FK_pobrain_err_resolved_by
        FOREIGN KEY (resolved_by) REFERENCES dbo.pobrain_users (username);
    PRINT '  [OK] FK_pobrain_err_resolved_by added';
END
ELSE
    PRINT '  [SKIP] FK_pobrain_err_resolved_by already exists';
GO

-- ============================================================================
-- STEP 5: FK — pobrain_failed_transactions.reprocessed_by → pobrain_users.username
--   reprocessed_by is VARCHAR(100) NULL — same VARCHAR FK pattern as above.
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_pobrain_ft_reprocessed_by')
BEGIN
    ALTER TABLE dbo.pobrain_failed_transactions
        ADD CONSTRAINT FK_pobrain_ft_reprocessed_by
        FOREIGN KEY (reprocessed_by) REFERENCES dbo.pobrain_users (username);
    PRINT '  [OK] FK_pobrain_ft_reprocessed_by added';
END
ELSE
    PRINT '  [SKIP] FK_pobrain_ft_reprocessed_by already exists';
GO

-- ============================================================================
-- STEP 6: Seed default users
--
--   Default passwords (bcrypt cost 12):
--     SYSTEM   → System@1234  (is_active = 0, cannot log in via UI)
--     admin    → Admin@1234
--     operator → Operator@1234
--     viewer   → Viewer@1234
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_users WHERE username = 'SYSTEM')
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

    PRINT '  [OK] 4 default users seeded — update password_hash before production use';
END
ELSE
    PRINT '  [SKIP] Default users already exist';
GO

PRINT '';
PRINT '============================================================================';
PRINT '  07_migration_add_auth_tables.sql — Migration complete';
PRINT '  Tables added  : dbo.pobrain_users, dbo.pobrain_password_resets';
PRINT '  FKs added     : FK_pobrain_pwr_user, FK_pobrain_err_resolved_by,';
PRINT '                  FK_pobrain_ft_reprocessed_by';
PRINT '  Rows seeded   : 4 default users (update password_hash before going live)';
PRINT '============================================================================';
GO
