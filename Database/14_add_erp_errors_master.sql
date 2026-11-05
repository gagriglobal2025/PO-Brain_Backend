-- ============================================================================
-- PO-Brain Migration: Add ERP Errors Master and ERP error columns to emails
-- Database: hyma_testdb
-- Version:  1.5.0
-- Created:  2026-07-23
-- Description:
--   Creates Errors Master table, seeds standard codes, and updates pobrain_emails.
-- ============================================================================

USE [hyma_testdb];
GO

PRINT '============================================================================';
PRINT '  14_add_erp_errors_master.sql — Starting migration';
PRINT '============================================================================';
GO

-- 1. Create pobrain_erp_errors_master
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_erp_errors_master') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_erp_errors_master
    (
        error_code              VARCHAR(50)     NOT NULL,
        error_reason            NVARCHAR(500)   NOT NULL,
        recommended_solution    NVARCHAR(1000)  NOT NULL,

        CONSTRAINT PK_pobrain_erp_errors_master PRIMARY KEY CLUSTERED (error_code)
    );
    PRINT '  [OK] Created dbo.pobrain_erp_errors_master';
END
ELSE
    PRINT '  [SKIP] dbo.pobrain_erp_errors_master already exists';
GO

-- 2. Seed standard error codes
IF EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_erp_errors_master') AND type = 'U')
BEGIN
    -- Seed CUSTOMER_NOT_FOUND
    IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_erp_errors_master WHERE error_code = 'CUSTOMER_NOT_FOUND')
    BEGIN
        INSERT INTO dbo.pobrain_erp_errors_master (error_code, error_reason, recommended_solution)
        VALUES ('CUSTOMER_NOT_FOUND', 
                'The vendor/buyer email address is not registered in the customer master table (dbo.tblRegistration).', 
                'Register the customer''s email address in tblRegistration with a valid CompanyCode and PersonID, or update the purchase order with the registered contact email.');
    END

    -- Seed MISSING_EMAIL
    IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_erp_errors_master WHERE error_code = 'MISSING_EMAIL')
    BEGIN
        INSERT INTO dbo.pobrain_erp_errors_master (error_code, error_reason, recommended_solution)
        VALUES ('MISSING_EMAIL', 
                'No vendor/buyer email address was provided or extracted for this purchase order.', 
                'Verify the sender''s email address or the email body/PDF contact details, and ensure a valid email address is associated with the transaction.');
    END

    -- Seed ERP_DB_INSERT_ERROR
    IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_erp_errors_master WHERE error_code = 'ERP_DB_INSERT_ERROR')
    BEGIN
        INSERT INTO dbo.pobrain_erp_errors_master (error_code, error_reason, recommended_solution)
        VALUES ('ERP_DB_INSERT_ERROR', 
                'A database error or constraint violation occurred during insertion into the legacy ERP tables.', 
                'Check SQL server constraint logs and verify if all fields (e.g., item codes, quantities) match the ERP table data types.');
    END

    -- Seed ERP_UNKNOWN_ERROR
    IF NOT EXISTS (SELECT 1 FROM dbo.pobrain_erp_errors_master WHERE error_code = 'ERP_UNKNOWN_ERROR')
    BEGIN
        INSERT INTO dbo.pobrain_erp_errors_master (error_code, error_reason, recommended_solution)
        VALUES ('ERP_UNKNOWN_ERROR', 
                'An unexpected error occurred during the ERP insertion process.', 
                'Review the application logs or stack trace to identify the cause of the failure and retry processing.');
    END

    PRINT '  [OK] Seeded standard error codes in dbo.pobrain_erp_errors_master';
END;
GO

-- 3. Add erp_insertion_status to dbo.pobrain_emails
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_emails') AND name = 'erp_insertion_status')
BEGIN
    ALTER TABLE dbo.pobrain_emails ADD erp_insertion_status VARCHAR(20) NOT NULL CONSTRAINT DF_pobrain_emails_erp_status DEFAULT ('PENDING');
    PRINT '  [OK] Added pobrain_emails.erp_insertion_status';
END
ELSE
    PRINT '  [SKIP] pobrain_emails.erp_insertion_status already exists';
GO

-- 4. Add erp_error_code to dbo.pobrain_emails
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_emails') AND name = 'erp_error_code')
BEGIN
    ALTER TABLE dbo.pobrain_emails ADD erp_error_code VARCHAR(50) NULL;
    PRINT '  [OK] Added pobrain_emails.erp_error_code';
END
ELSE
    PRINT '  [SKIP] pobrain_emails.erp_error_code already exists';
GO

-- 5. Add erp_error_reason to dbo.pobrain_emails
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_emails') AND name = 'erp_error_reason')
BEGIN
    ALTER TABLE dbo.pobrain_emails ADD erp_error_reason NVARCHAR(500) NULL;
    PRINT '  [OK] Added pobrain_emails.erp_error_reason';
END
ELSE
    PRINT '  [SKIP] pobrain_emails.erp_error_reason already exists';
GO

-- 6. Add erp_error_solution to dbo.pobrain_emails
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.pobrain_emails') AND name = 'erp_error_solution')
BEGIN
    ALTER TABLE dbo.pobrain_emails ADD erp_error_solution NVARCHAR(1000) NULL;
    PRINT '  [OK] Added pobrain_emails.erp_error_solution';
END
ELSE
    PRINT '  [SKIP] pobrain_emails.erp_error_solution already exists';
GO

PRINT '============================================================================';
PRINT '  14_add_erp_errors_master.sql — Migration complete';
PRINT '============================================================================';
GO
