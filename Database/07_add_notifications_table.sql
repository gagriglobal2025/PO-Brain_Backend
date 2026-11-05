-- Create Notifications table for PO-Brain
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.pobrain_notifications') AND type in (N'U'))
BEGIN
    CREATE TABLE dbo.pobrain_notifications
    (
        notification_id INT PRIMARY KEY IDENTITY(1,1),
        user_id INT NOT NULL,
        type NVARCHAR(50) NOT NULL,
        title NVARCHAR(255) NOT NULL,
        message NVARCHAR(MAX) NOT NULL,
        is_read BIT NOT NULL DEFAULT 0,
        related_po_number NVARCHAR(50) NULL,
        related_error_id INT NULL,
        created_at DATETIME2 NOT NULL DEFAULT DATEADD(MINUTE, 330, GETUTCDATE()),
        read_at DATETIME2 NULL,
        CONSTRAINT FK_pobrain_notifications_user
            FOREIGN KEY (user_id) REFERENCES dbo.pobrain_users(user_id) ON DELETE CASCADE
    );

    -- Create indexes for performance
    CREATE INDEX IX_pobrain_notifications_user_id
        ON dbo.pobrain_notifications(user_id);

    CREATE INDEX IX_pobrain_notifications_user_id_is_read
        ON dbo.pobrain_notifications(user_id, is_read);

    PRINT 'Notifications table created successfully.';
END
ELSE
BEGIN
    PRINT 'Notifications table already exists.';
END
