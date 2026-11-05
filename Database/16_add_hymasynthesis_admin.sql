-- ============================================================================
-- PO-Brain: Add Admin User Script
-- Database: hyma_testdb
-- Table: dbo.pobrain_users
-- ============================================================================

USE [hyma_testdb];
GO

IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_users WHERE email = 'hymasynthesis@gmail.com')
BEGIN
    INSERT INTO dbo.pobrain_users
        (username, email, password_hash, full_name, role, is_active, created_by)
    VALUES
    (
        'hymasynthesis',
        'hymasynthesis@gmail.com',
        '$2b$12$fhGnQElSZhhcjGI53Mdt6ewU6YUWUM1avHVtLSZyVbd0kFvS.nuYq', -- bcrypt hash for hyma@123
        'Hyma Administrator',
        'admin',
        1,
        'SYSTEM'
    );
    PRINT '  [OK] Successfully created admin user: hymasynthesis@gmail.com (Password: hyma@123)';
END
ELSE
BEGIN
    UPDATE dbo.pobrain_users
    SET role = 'admin',
        is_active = 1,
        password_hash = '$2b$12$fhGnQElSZhhcjGI53Mdt6ewU6YUWUM1avHVtLSZyVbd0kFvS.nuYq',
        updated_at = DATEADD(MINUTE, 330, GETUTCDATE())
    WHERE email = 'hymasynthesis@gmail.com';

    PRINT '  [OK] Updated existing user hymasynthesis@gmail.com to admin role with password hyma@123';
END
GO
