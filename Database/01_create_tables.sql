-- ============================================================================
-- PO-Brain Database Schema
-- Database: hyma_testdb
-- Prefix:   dbo.pobrain_
-- Version:  1.0.0
-- Created:  2026-05-29
-- Description: Complete 3NF normalized schema for the PO-Brain 
--              Email Processing & Monitoring System
-- ============================================================================
-- Execution Order: Run this script FIRST
-- ============================================================================

USE [hyma_testdb];
GO

-- ============================================================================
-- SECTION 1: LOOKUP / REFERENCE TABLES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1.1  pobrain_lkp_status
--      Centralized status master for all entities
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_lkp_status') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_lkp_status
    (
        status_id       INT             IDENTITY(1,1)   NOT NULL,
        status_code     VARCHAR(30)                     NOT NULL,
        status_name     VARCHAR(100)                    NOT NULL,
        entity_type     VARCHAR(50)                     NOT NULL,
        is_active       BIT                             NOT NULL    CONSTRAINT DF_pobrain_lkp_status_is_active DEFAULT (1),
        created_at      DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_lkp_status_created_at DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),
        updated_at      DATETIME2(3)                    NULL,

        CONSTRAINT PK_pobrain_lkp_status PRIMARY KEY CLUSTERED (status_id),
        CONSTRAINT UQ_pobrain_lkp_status_code_entity UNIQUE (status_code, entity_type)
    );
END;
GO

-- ----------------------------------------------------------------------------
-- 1.2  pobrain_lkp_log_level
--      Log severity levels (DEBUG, INFO, WARN, ERROR, FATAL)
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_lkp_log_level') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_lkp_log_level
    (
        log_level_id    INT             IDENTITY(1,1)   NOT NULL,
        level_code      VARCHAR(10)                     NOT NULL,
        level_name      VARCHAR(30)                     NOT NULL,
        severity_order  INT                             NOT NULL,

        CONSTRAINT PK_pobrain_lkp_log_level PRIMARY KEY CLUSTERED (log_level_id),
        CONSTRAINT UQ_pobrain_lkp_log_level_code UNIQUE (level_code)
    );
END;
GO

-- ----------------------------------------------------------------------------
-- 1.3  pobrain_lkp_processing_stage
--      Pipeline stage definitions
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_lkp_processing_stage') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_lkp_processing_stage
    (
        stage_id        INT             IDENTITY(1,1)   NOT NULL,
        stage_code      VARCHAR(50)                     NOT NULL,
        stage_name      VARCHAR(100)                    NOT NULL,
        stage_order     INT                             NOT NULL,
        is_active       BIT                             NOT NULL    CONSTRAINT DF_pobrain_lkp_stage_is_active DEFAULT (1),

        CONSTRAINT PK_pobrain_lkp_processing_stage PRIMARY KEY CLUSTERED (stage_id),
        CONSTRAINT UQ_pobrain_lkp_stage_code UNIQUE (stage_code)
    );
END;
GO

-- ----------------------------------------------------------------------------
-- 1.4  pobrain_lkp_error_category
--      Error classification taxonomy
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_lkp_error_category') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_lkp_error_category
    (
        error_category_id   INT         IDENTITY(1,1)   NOT NULL,
        category_code       VARCHAR(50)                 NOT NULL,
        category_name       VARCHAR(100)                NOT NULL,
        is_active           BIT                         NOT NULL    CONSTRAINT DF_pobrain_lkp_errcat_is_active DEFAULT (1),

        CONSTRAINT PK_pobrain_lkp_error_category PRIMARY KEY CLUSTERED (error_category_id),
        CONSTRAINT UQ_pobrain_lkp_errcat_code UNIQUE (category_code)
    );
END;
GO

-- ----------------------------------------------------------------------------
-- 1.5  pobrain_lkp_parsing_engine
--      Extraction engine registry
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_lkp_parsing_engine') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_lkp_parsing_engine
    (
        engine_id       INT             IDENTITY(1,1)   NOT NULL,
        engine_name     VARCHAR(100)                    NOT NULL,
        engine_version  VARCHAR(30)                     NULL,
        is_active       BIT                             NOT NULL    CONSTRAINT DF_pobrain_lkp_engine_is_active DEFAULT (1),

        CONSTRAINT PK_pobrain_lkp_parsing_engine PRIMARY KEY CLUSTERED (engine_id),
        CONSTRAINT UQ_pobrain_lkp_engine_name UNIQUE (engine_name)
    );
END;
GO


-- ============================================================================
-- SECTION 2: CORE TRANSACTION TABLES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 2.1  pobrain_emails
--      Incoming email records — the root entity of the processing pipeline
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_emails') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_emails
    (
        email_id                BIGINT          IDENTITY(1,1)   NOT NULL,
        mail_uid                VARCHAR(255)                    NOT NULL,
        email_from              VARCHAR(320)                    NOT NULL,
        email_to                VARCHAR(320)                    NULL,
        email_subject           NVARCHAR(500)                   NULL,
        email_received_at       DATETIME2(3)                    NOT NULL,
        email_body_preview      NVARCHAR(1000)                  NULL,
        attachment_count        INT                             NOT NULL    CONSTRAINT DF_pobrain_emails_attach_count DEFAULT (0),
        has_pdf                 BIT                             NOT NULL    CONSTRAINT DF_pobrain_emails_has_pdf DEFAULT (0),
        status_id               INT                             NOT NULL,
        retry_count             INT                             NOT NULL    CONSTRAINT DF_pobrain_emails_retry_count DEFAULT (0),
        max_retries             INT                             NOT NULL    CONSTRAINT DF_pobrain_emails_max_retries DEFAULT (3),
        failure_reason          NVARCHAR(1000)                  NULL,
        processing_started_at   DATETIME2(3)                    NULL,
        processing_completed_at DATETIME2(3)                    NULL,
        processing_duration_ms  INT                             NULL,
        created_at              DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_emails_created_at DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),
        updated_at              DATETIME2(3)                    NULL,
        created_by              VARCHAR(100)                    NOT NULL    CONSTRAINT DF_pobrain_emails_created_by DEFAULT ('SYSTEM'),
        updated_by              VARCHAR(100)                    NULL,

        CONSTRAINT PK_pobrain_emails PRIMARY KEY CLUSTERED (email_id),
        CONSTRAINT UQ_pobrain_emails_mail_uid UNIQUE (mail_uid)
    );
END;
GO

-- ----------------------------------------------------------------------------
-- 2.2  pobrain_email_attachments
--      PDF/file attachment metadata per email
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_email_attachments') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_email_attachments
    (
        attachment_id       BIGINT          IDENTITY(1,1)   NOT NULL,
        email_id            BIGINT                          NOT NULL,
        file_name           NVARCHAR(500)                   NOT NULL,
        file_type           VARCHAR(20)                     NOT NULL,
        file_size_bytes     BIGINT                          NULL,
        storage_path        NVARCHAR(1000)                  NULL,
        file_hash           VARCHAR(64)                     NULL,
        status_id           INT                             NOT NULL,
        ocr_required        BIT                             NOT NULL    CONSTRAINT DF_pobrain_attach_ocr_req DEFAULT (0),
        ocr_status_id       INT                             NULL,
        page_count          INT                             NULL,
        created_at          DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_attach_created_at DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),
        updated_at          DATETIME2(3)                    NULL,
        created_by          VARCHAR(100)                    NOT NULL    CONSTRAINT DF_pobrain_attach_created_by DEFAULT ('SYSTEM'),
        updated_by          VARCHAR(100)                    NULL,

        CONSTRAINT PK_pobrain_email_attachments PRIMARY KEY CLUSTERED (attachment_id)
    );
END;
GO

-- ----------------------------------------------------------------------------
-- 2.3  pobrain_extraction_jobs
--      Extraction job tracking per attachment
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_extraction_jobs') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_extraction_jobs
    (
        job_id                  BIGINT          IDENTITY(1,1)   NOT NULL,
        attachment_id           BIGINT                          NULL,
        status_id               INT                             NOT NULL,
        engine_id               INT                             NULL,
        confidence_score        DECIMAL(5,2)                    NULL,
        validation_status_id    INT                             NULL,
        items_extracted         INT                             NOT NULL    CONSTRAINT DF_pobrain_jobs_items DEFAULT (0),
        raw_extraction_json     NVARCHAR(MAX)                   NULL,
        started_at              DATETIME2(3)                    NULL,
        completed_at            DATETIME2(3)                    NULL,
        duration_ms             INT                             NULL,
        attempt_number          INT                             NOT NULL    CONSTRAINT DF_pobrain_jobs_attempt DEFAULT (1),
        created_at              DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_jobs_created_at DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),
        updated_at              DATETIME2(3)                    NULL,
        created_by              VARCHAR(100)                    NOT NULL    CONSTRAINT DF_pobrain_jobs_created_by DEFAULT ('SYSTEM'),
        updated_by              VARCHAR(100)                    NULL,

        CONSTRAINT PK_pobrain_extraction_jobs PRIMARY KEY CLUSTERED (job_id),
        CONSTRAINT CK_pobrain_jobs_confidence CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100))
    );
END;
GO

-- ----------------------------------------------------------------------------
-- 2.4  pobrain_purchase_orders
--      Normalized PO header / master data
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_purchase_orders') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_purchase_orders
    (
        po_id               BIGINT          IDENTITY(1,1)   NOT NULL,
        extraction_job_id   BIGINT                          NOT NULL,
        email_id            BIGINT                          NOT NULL,
        po_number           VARCHAR(50)                     NOT NULL,
        po_date             DATE                            NULL,
        vendor_name         NVARCHAR(300)                   NULL,
        vendor_email        VARCHAR(320)                    NULL,
        delivery_address    NVARCHAR(1000)                  NULL,
        gst_number          VARCHAR(20)                     NULL,
        cgst_number         VARCHAR(20)                     NULL,
        sgst_number         VARCHAR(20)                     NULL,
        igst_number         VARCHAR(20)                     NULL,
        total_quantity      DECIMAL(18,4)                   NULL,
        subtotal_amount     DECIMAL(18,2)                   NULL,
        total_tax_amount    DECIMAL(18,2)                   NULL,
        total_amount        DECIMAL(18,2)                   NULL,
        currency_code       VARCHAR(3)                      NOT NULL    CONSTRAINT DF_pobrain_po_currency DEFAULT ('INR'),
        status_id           INT                             NOT NULL,
        is_duplicate        BIT                             NOT NULL    CONSTRAINT DF_pobrain_po_is_dup DEFAULT (0),
        created_at          DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_po_created_at DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),
        updated_at          DATETIME2(3)                    NULL,
        created_by          VARCHAR(100)                    NOT NULL    CONSTRAINT DF_pobrain_po_created_by DEFAULT ('SYSTEM'),
        updated_by          VARCHAR(100)                    NULL,

        CONSTRAINT PK_pobrain_purchase_orders PRIMARY KEY CLUSTERED (po_id),
        CONSTRAINT UQ_pobrain_po_number UNIQUE (po_number)
    );
END;
GO

-- ----------------------------------------------------------------------------
-- 2.5  pobrain_purchase_order_line_items
--      Product/item level data — multiple items per PO
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_purchase_order_line_items') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_purchase_order_line_items
    (
        line_item_id    BIGINT          IDENTITY(1,1)   NOT NULL,
        po_id           BIGINT                          NOT NULL,
        line_number     INT                             NOT NULL,
        product_name    NVARCHAR(500)                   NOT NULL,
        cas_number      VARCHAR(30)                     NULL,
        cat_number      VARCHAR(50)                     NULL,
        hsn_code        VARCHAR(20)                     NULL,
        quantity        DECIMAL(18,4)                   NOT NULL,
        unit_of_measure VARCHAR(20)                     NULL,
        unit_price      DECIMAL(18,4)                   NULL,
        amount          DECIMAL(18,2)                   NOT NULL,
        cgst_rate       DECIMAL(5,2)                    NULL,
        cgst_amount     DECIMAL(18,2)                   NULL,
        sgst_rate       DECIMAL(5,2)                    NULL,
        sgst_amount     DECIMAL(18,2)                   NULL,
        igst_rate       DECIMAL(5,2)                    NULL,
        igst_amount     DECIMAL(18,2)                   NULL,
        created_at      DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_li_created_at DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),
        updated_at      DATETIME2(3)                    NULL,

        CONSTRAINT PK_pobrain_po_line_items PRIMARY KEY CLUSTERED (line_item_id),
        CONSTRAINT UQ_pobrain_li_po_line UNIQUE (po_id, line_number)
    );
END;
GO


-- ============================================================================
-- SECTION 3: MONITORING & OPERATIONS TABLES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 3.1  pobrain_workflow_steps
--      Pipeline stage execution tracking per email
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_workflow_steps') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_workflow_steps
    (
        step_id         BIGINT          IDENTITY(1,1)   NOT NULL,
        email_id        BIGINT                          NOT NULL,
        stage_id        INT                             NOT NULL,
        status_id       INT                             NOT NULL,
        service_name    VARCHAR(100)                    NULL,
        queue_position  INT                             NULL,
        started_at      DATETIME2(3)                    NULL,
        completed_at    DATETIME2(3)                    NULL,
        duration_ms     INT                             NULL,
        remarks         NVARCHAR(500)                   NULL,
        created_at      DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_wf_created_at DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),
        updated_at      DATETIME2(3)                    NULL,

        CONSTRAINT PK_pobrain_workflow_steps PRIMARY KEY CLUSTERED (step_id)
    );
END;
GO

-- ----------------------------------------------------------------------------
-- 3.2  pobrain_processing_logs
--      System event log — maps to Processing Logs UI screen
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_processing_logs') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_processing_logs
    (
        log_id          BIGINT          IDENTITY(1,1)   NOT NULL,
        email_id        BIGINT                          NULL,
        log_level_id    INT                             NOT NULL,
        sender_email    VARCHAR(320)                    NULL,
        email_subject   NVARCHAR(500)                   NULL,
        message         NVARCHAR(2000)                  NOT NULL,
        module_name     VARCHAR(100)                    NULL,
        correlation_id  VARCHAR(50)                     NULL,
        logged_at       DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_plog_logged_at DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),

        CONSTRAINT PK_pobrain_processing_logs PRIMARY KEY CLUSTERED (log_id)
    );
END;
GO

-- ----------------------------------------------------------------------------
-- 3.3  pobrain_error_logs
--      Detailed error/exception records
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_error_logs') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_error_logs
    (
        error_id            BIGINT          IDENTITY(1,1)   NOT NULL,
        email_id            BIGINT                          NULL,
        attachment_id       BIGINT                          NULL,
        job_id              BIGINT                          NULL,
        error_category_id   INT                             NULL,
        error_code          VARCHAR(50)                     NULL,
        error_message       NVARCHAR(2000)                  NOT NULL,
        stack_trace         NVARCHAR(MAX)                   NULL,
        failed_module       VARCHAR(100)                    NULL,
        severity            INT                             NOT NULL    CONSTRAINT DF_pobrain_err_severity DEFAULT (3),
        retry_attempt       INT                             NOT NULL    CONSTRAINT DF_pobrain_err_retry DEFAULT (0),
        is_resolved         BIT                             NOT NULL    CONSTRAINT DF_pobrain_err_resolved DEFAULT (0),
        resolved_by         VARCHAR(100)                    NULL,
        resolution_notes    NVARCHAR(1000)                  NULL,
        occurred_at         DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_err_occurred_at DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),
        resolved_at         DATETIME2(3)                    NULL,

        CONSTRAINT PK_pobrain_error_logs PRIMARY KEY CLUSTERED (error_id),
        CONSTRAINT CK_pobrain_err_severity CHECK (severity BETWEEN 1 AND 4)
    );
END;
GO

-- ----------------------------------------------------------------------------
-- 3.4  pobrain_failed_transactions
--      Failed PO processing records — maps to Failed Transactions UI screen
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_failed_transactions') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_failed_transactions
    (
        failed_id           BIGINT          IDENTITY(1,1)   NOT NULL,
        email_id            BIGINT                          NULL,
        extraction_job_id   BIGINT                          NULL,
        po_number           VARCHAR(50)                     NULL,
        po_date             DATE                            NULL,
        product_name        NVARCHAR(500)                   NULL,
        quantity            DECIMAL(18,4)                   NULL,
        amount              DECIMAL(18,2)                   NULL,
        email_from          VARCHAR(320)                    NULL,
        email_date          DATETIME2(3)                    NULL,
        error_reason        NVARCHAR(1000)                  NOT NULL,
        error_category_id   INT                             NULL,
        is_reprocessed      BIT                             NOT NULL    CONSTRAINT DF_pobrain_ft_reprocessed DEFAULT (0),
        reprocessed_by      VARCHAR(100)                    NULL,
        failed_at           DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_ft_failed_at DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),
        reprocessed_at      DATETIME2(3)                    NULL,
        created_at          DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_ft_created_at DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),
        updated_at          DATETIME2(3)                    NULL,

        CONSTRAINT PK_pobrain_failed_transactions PRIMARY KEY CLUSTERED (failed_id)
    );
END;
GO

-- ----------------------------------------------------------------------------
-- 3.5  pobrain_audit_logs
--      All data modification tracking
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_audit_logs') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_audit_logs
    (
        audit_id        BIGINT          IDENTITY(1,1)   NOT NULL,
        table_name      VARCHAR(128)                    NOT NULL,
        record_id       BIGINT                          NOT NULL,
        action_type     VARCHAR(10)                     NOT NULL,
        changed_by      VARCHAR(100)                    NOT NULL,
        old_values      NVARCHAR(MAX)                   NULL,
        new_values      NVARCHAR(MAX)                   NULL,
        ip_address      VARCHAR(45)                     NULL,
        user_agent      VARCHAR(500)                    NULL,
        correlation_id  VARCHAR(50)                     NULL,
        changed_at      DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_audit_changed_at DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),

        CONSTRAINT PK_pobrain_audit_logs PRIMARY KEY CLUSTERED (audit_id),
        CONSTRAINT CK_pobrain_audit_action CHECK (action_type IN ('INSERT', 'UPDATE', 'DELETE'))
    );
END;
GO

-- ----------------------------------------------------------------------------
-- 3.6  pobrain_system_health_snapshots
--      Periodic health metric snapshots — maps to Processing Health dashboard widget
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_system_health_snapshots') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_system_health_snapshots
    (
        snapshot_id         BIGINT          IDENTITY(1,1)   NOT NULL,
        component_name      VARCHAR(100)                    NOT NULL,
        health_pct          DECIMAL(5,2)                    NOT NULL,
        total_processed     INT                             NOT NULL    CONSTRAINT DF_pobrain_health_processed DEFAULT (0),
        total_failed        INT                             NOT NULL    CONSTRAINT DF_pobrain_health_failed DEFAULT (0),
        total_pending       INT                             NOT NULL    CONSTRAINT DF_pobrain_health_pending DEFAULT (0),
        avg_processing_ms   INT                             NULL,
        snapshot_period     VARCHAR(20)                     NOT NULL    CONSTRAINT DF_pobrain_health_period DEFAULT ('24h'),
        snapshot_at         DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_health_snapshot_at DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),

        CONSTRAINT PK_pobrain_system_health_snapshots PRIMARY KEY CLUSTERED (snapshot_id),
        CONSTRAINT CK_pobrain_health_pct CHECK (health_pct >= 0 AND health_pct <= 100)
    );
END;
GO

-- ============================================================================
-- SECTION 4: AUTHENTICATION
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 4.1  pobrain_users
--      Application login accounts. password_hash stores a bcrypt hash.
--      The 'system' role is reserved for the automated pipeline (username = 'SYSTEM').
--      resolved_by (error_logs) and reprocessed_by (failed_transactions) carry
--      FK constraints back to this table — see 02_foreign_keys.sql.
-- ----------------------------------------------------------------------------
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

        CONSTRAINT PK_pobrain_users         PRIMARY KEY CLUSTERED (user_id),
        CONSTRAINT UQ_pobrain_users_username UNIQUE (username),
        CONSTRAINT UQ_pobrain_users_email   UNIQUE (email),
        CONSTRAINT CK_pobrain_users_role    CHECK (role IN ('admin', 'operator', 'viewer', 'system'))
    );
END;
GO

-- ----------------------------------------------------------------------------
-- 4.2  pobrain_password_resets
--      One-time reset tokens emailed to the user. Token is consumed on use
--      and hard-expires at expires_at regardless. FK back to pobrain_users.
-- ----------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_password_resets') AND type = 'U')
BEGIN
    CREATE TABLE dbo.pobrain_password_resets
    (
        reset_id        INT             IDENTITY(1,1)   NOT NULL,
        user_id         INT                             NOT NULL,
        token_hash      VARCHAR(255)                    NOT NULL,
        expires_at      DATETIME2(3)                    NOT NULL,
        is_used         BIT                             NOT NULL    CONSTRAINT DF_pobrain_pwr_is_used    DEFAULT (0),
        used_at         DATETIME2(3)                    NULL,
        requested_ip    VARCHAR(45)                     NULL,
        created_at      DATETIME2(3)                    NOT NULL    CONSTRAINT DF_pobrain_pwr_created_at DEFAULT (DATEADD(MINUTE, 330, GETUTCDATE())),

        CONSTRAINT PK_pobrain_password_resets           PRIMARY KEY CLUSTERED (reset_id),
        CONSTRAINT UQ_pobrain_password_resets_token     UNIQUE (token_hash)
    );
END;
GO

PRINT '============================================================================';
PRINT '  01_create_tables.sql — All 18 tables created successfully';
PRINT '  Database: hyma_testdb | Prefix: dbo.pobrain_';
PRINT '============================================================================';
GO
