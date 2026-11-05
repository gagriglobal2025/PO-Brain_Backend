-- ============================================================================
-- PO-Brain: Add New Admin User Script
-- Database: hyma_testdb
-- Table: dbo.pobrain_users
-- ============================================================================

USE [hyma_testdb];
GO

-- 1. Insert admin account for jingchaka1@gmail.com if it doesn't already exist
IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_users WHERE email = 'jingchaka1@gmail.com' OR username = 'jingchaka1')
BEGIN
    INSERT INTO dbo.pobrain_users
        (username, email, password_hash, full_name, role, is_active, created_by)
    VALUES
    (
        'jingchaka1',
        'jingchaka1@gmail.com',
        '$2b$12$mYFTWc23Nld6dPTljb3SeOzn.5YpEks2QtvWWrygDzbLc7Muk69Ma', -- bcrypt hash for Admin@1234
        'Test Admin User',
        'admin',
        1,
        'SYSTEM'
    );
    PRINT '  [OK] Successfully created admin user: jingchaka1@gmail.com (Password: Admin@1234)';
END
ELSE
BEGIN
    -- If user exists, ensure active and update role to admin
    UPDATE dbo.pobrain_users
    SET role = 'admin',
        is_active = 1,
        password_hash = '$2b$12$mYFTWc23Nld6dPTljb3SeOzn.5YpEks2QtvWWrygDzbLc7Muk69Ma',
        updated_at = DATEADD(MINUTE, 330, GETUTCDATE())
    WHERE email = 'jingchaka1@gmail.com' OR username = 'jingchaka1';

    PRINT '  [OK] Updated existing user jingchaka1@gmail.com to admin role with password Admin@1234';
END
GO
