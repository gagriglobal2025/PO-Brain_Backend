using Microsoft.EntityFrameworkCore;
using POBrain.API.Data;
using POBrain.API.Models.Common;
using POBrain.API.Models.Email;
using POBrain.API.Models.FailedTransactions;
using System.Net;
using System.Text;

namespace POBrain.API.Services;

public class FailedTransactionService(
    PoBrainDbContext db,
    IEmailService emailService,
    ILogger<FailedTransactionService> logger) : IFailedTransactionService
{
    public async Task<int> GetPendingCountAsync()
    {
        var countRows = await db.Database.SqlQuery<CountRow>($"""
            SELECT COUNT(*) AS Total
            FROM dbo.pobrain_failed_transactions
            WHERE is_reprocessed = 0
            """).ToListAsync();
        return countRows.FirstOrDefault()?.Total ?? 0;
    }

    public async Task<PagedResponse<FailedTransactionDto>> GetAllAsync(string? search, int page, int pageSize)
    {
        page     = Math.Max(1, page);
        pageSize = Math.Clamp(pageSize, 1, 200);
        int offset = (page - 1) * pageSize;

        var pattern = string.IsNullOrWhiteSpace(search) ? "%" : $"%{search.Trim()}%";

        var countRows = await db.Database.SqlQuery<CountRow>($"""
            SELECT COUNT(*) AS Total
            FROM dbo.pobrain_failed_transactions
            WHERE is_reprocessed = 0
              AND (po_number    LIKE {pattern}
                OR product_name LIKE {pattern}
                OR email_from   LIKE {pattern})
            """).ToListAsync();

        int total = countRows.FirstOrDefault()?.Total ?? 0;

        var rows = await db.Database.SqlQuery<FailedRow>($"""
            SELECT
                failed_id                                    AS FailedId,
                po_number                                    AS PoNumber,
                CONVERT(VARCHAR(10), po_date, 120)           AS PoDate,
                product_name                                 AS ProductName,
                quantity                                     AS Quantity,
                amount                                       AS Amount,
                email_from                                   AS EmailFrom,
                FORMAT(email_date, 'yyyy-MM-dd')             AS EmailDate,
                error_reason                                 AS ErrorReason,
                FORMAT(failed_at, 'yyyy-MM-dd HH:mm')        AS FailedAt
            FROM dbo.pobrain_failed_transactions
            WHERE is_reprocessed = 0
              AND (po_number    LIKE {pattern}
                OR product_name LIKE {pattern}
                OR email_from   LIKE {pattern})
            ORDER BY failed_at DESC
            OFFSET {offset} ROWS FETCH NEXT {pageSize} ROWS ONLY
            """).ToListAsync();

        var data = rows.Select(r => new FailedTransactionDto
        {
            FailedId     = r.FailedId,
            PoNumber     = r.PoNumber,
            PoDate       = r.PoDate,
            ProductName  = r.ProductName,
            Quantity     = r.Quantity,
            Amount       = r.Amount,
            EmailFrom    = r.EmailFrom,
            EmailDate    = r.EmailDate,
            ErrorReason  = r.ErrorReason,
            FailedAt     = r.FailedAt
        });

        return new PagedResponse<FailedTransactionDto>
        {
            Data       = data,
            TotalCount = total,
            Page       = page,
            PageSize   = pageSize
        };
    }

    private sealed class CountRow { public int Total { get; set; } }

    public async Task<PagedResponse<FailedTransactionDto>> GetAllWithFiltersAsync(FailedTransactionFilterRequest filter)
    {
        filter.Page = Math.Max(1, filter.Page);
        filter.PageSize = Math.Clamp(filter.PageSize, 1, 200);
        int offset = (filter.Page - 1) * filter.PageSize;

        var pattern = string.IsNullOrWhiteSpace(filter.Search) ? "%" : $"%{filter.Search.Trim()}%";
        var categoryFilter = string.IsNullOrWhiteSpace(filter.ErrorCategory) ? "%" : $"%{filter.ErrorCategory.Trim()}%";
        var fromDate = filter.FromDate?.Date;
        var toDate = filter.ToDate?.Date.AddDays(1);
        var minAmount = filter.MinAmount;
        var maxAmount = filter.MaxAmount;

        var countRows = await db.Database.SqlQuery<CountRow>($"""
            SELECT COUNT(*) AS Total
            FROM dbo.pobrain_failed_transactions
            WHERE is_reprocessed = 0
              AND (po_number    LIKE {pattern}
                OR product_name LIKE {pattern}
                OR email_from   LIKE {pattern})
              AND ({categoryFilter} = '%' OR error_reason LIKE {categoryFilter})
              AND ({fromDate} IS NULL OR failed_at >= {fromDate})
              AND ({toDate} IS NULL OR failed_at < {toDate})
              AND ({minAmount} IS NULL OR amount >= {minAmount})
              AND ({maxAmount} IS NULL OR amount <= {maxAmount})
            """).ToListAsync();

        int total = countRows.FirstOrDefault()?.Total ?? 0;

        var rows = await db.Database.SqlQuery<FailedRow>($"""
            SELECT
                failed_id                                    AS FailedId,
                po_number                                    AS PoNumber,
                CONVERT(VARCHAR(10), po_date, 120)           AS PoDate,
                product_name                                 AS ProductName,
                quantity                                     AS Quantity,
                amount                                       AS Amount,
                email_from                                   AS EmailFrom,
                FORMAT(email_date, 'yyyy-MM-dd')             AS EmailDate,
                error_reason                                 AS ErrorReason,
                FORMAT(failed_at, 'yyyy-MM-dd HH:mm')        AS FailedAt
            FROM dbo.pobrain_failed_transactions
            WHERE is_reprocessed = 0
              AND (po_number    LIKE {pattern}
                OR product_name LIKE {pattern}
                OR email_from   LIKE {pattern})
              AND ({categoryFilter} = '%' OR error_reason LIKE {categoryFilter})
              AND ({fromDate} IS NULL OR failed_at >= {fromDate})
              AND ({toDate} IS NULL OR failed_at < {toDate})
              AND ({minAmount} IS NULL OR amount >= {minAmount})
              AND ({maxAmount} IS NULL OR amount <= {maxAmount})
            ORDER BY failed_at DESC
            OFFSET {offset} ROWS FETCH NEXT {filter.PageSize} ROWS ONLY
            """).ToListAsync();

        var data = rows.Select(r => new FailedTransactionDto
        {
            FailedId     = r.FailedId,
            PoNumber     = r.PoNumber,
            PoDate       = r.PoDate,
            ProductName  = r.ProductName,
            Quantity     = r.Quantity,
            Amount       = r.Amount,
            EmailFrom    = r.EmailFrom,
            EmailDate    = r.EmailDate,
            ErrorReason  = r.ErrorReason,
            FailedAt     = r.FailedAt
        });

        return new PagedResponse<FailedTransactionDto>
        {
            Data       = data,
            TotalCount = total,
            Page       = filter.Page,
            PageSize   = filter.PageSize
        };
    }

    public async Task<byte[]> ExportToCsvAsync(FailedTransactionFilterRequest filter)
    {
        var pattern = string.IsNullOrWhiteSpace(filter.Search) ? "%" : $"%{filter.Search.Trim()}%";
        var categoryFilter = string.IsNullOrWhiteSpace(filter.ErrorCategory) ? "%" : $"%{filter.ErrorCategory.Trim()}%";
        var fromDate = filter.FromDate?.Date;
        var toDate = filter.ToDate?.Date.AddDays(1);
        var minAmount = filter.MinAmount;
        var maxAmount = filter.MaxAmount;

        var rows = await db.Database.SqlQuery<FailedRow>($"""
            SELECT
                failed_id                                    AS FailedId,
                po_number                                    AS PoNumber,
                CONVERT(VARCHAR(10), po_date, 120)           AS PoDate,
                product_name                                 AS ProductName,
                quantity                                     AS Quantity,
                amount                                       AS Amount,
                email_from                                   AS EmailFrom,
                FORMAT(email_date, 'yyyy-MM-dd')             AS EmailDate,
                error_reason                                 AS ErrorReason,
                FORMAT(failed_at, 'yyyy-MM-dd HH:mm')        AS FailedAt
            FROM dbo.pobrain_failed_transactions
            WHERE is_reprocessed = 0
              AND (po_number    LIKE {pattern}
                OR product_name LIKE {pattern}
                OR email_from   LIKE {pattern})
              AND ({categoryFilter} = '%' OR error_reason LIKE {categoryFilter})
              AND ({fromDate} IS NULL OR failed_at >= {fromDate})
              AND ({toDate} IS NULL OR failed_at < {toDate})
              AND ({minAmount} IS NULL OR amount >= {minAmount})
              AND ({maxAmount} IS NULL OR amount <= {maxAmount})
            ORDER BY failed_at DESC
            """).ToListAsync();

        var csv = new StringBuilder();
        csv.AppendLine("PO Number,PO Date,Product Name,Quantity,Amount,Email From,Email Date,Error Reason,Failed At");

        foreach (var row in rows)
        {
            csv.AppendLine($"{EscapeCsv(row.PoNumber)},{EscapeCsv(row.PoDate)},{EscapeCsv(row.ProductName)},{row.Quantity},{row.Amount},{EscapeCsv(row.EmailFrom)},{EscapeCsv(row.EmailDate)},{EscapeCsv(row.ErrorReason)},{EscapeCsv(row.FailedAt)}");
        }

        return Encoding.UTF8.GetBytes(csv.ToString());
    }

    public async Task<RerunFailedTransactionResponse> RerunAsync(RerunFailedTransactionRequest request, string? user = null)
    {
        user ??= "Web User";

        // 1. Locate the failed transaction record
        FailedDetailRow? failedRecord = null;
        if (request.FailedId.HasValue)
        {
            var records = await db.Database.SqlQuery<FailedDetailRow>($"""
                SELECT TOP 1
                    failed_id                       AS FailedId,
                    email_id                        AS EmailId,
                    po_number                       AS PoNumber,
                    CONVERT(VARCHAR(10), po_date, 120) AS PoDate,
                    product_name                    AS ProductName,
                    quantity                        AS Quantity,
                    amount                          AS Amount,
                    email_from                      AS EmailFrom
                FROM dbo.pobrain_failed_transactions
                WHERE failed_id = {request.FailedId.Value}
                """).ToListAsync();
            failedRecord = records.FirstOrDefault();
        }
        else if (!string.IsNullOrWhiteSpace(request.PoNumber))
        {
            var records = await db.Database.SqlQuery<FailedDetailRow>($"""
                SELECT TOP 1
                    failed_id                       AS FailedId,
                    email_id                        AS EmailId,
                    po_number                       AS PoNumber,
                    CONVERT(VARCHAR(10), po_date, 120) AS PoDate,
                    product_name                    AS ProductName,
                    quantity                        AS Quantity,
                    amount                          AS Amount,
                    email_from                      AS EmailFrom
                FROM dbo.pobrain_failed_transactions
                WHERE po_number = {request.PoNumber.Trim()}
                ORDER BY failed_id DESC
                """).ToListAsync();
            failedRecord = records.FirstOrDefault();
        }
        else if (!string.IsNullOrWhiteSpace(request.EmailFrom))
        {
            var records = await db.Database.SqlQuery<FailedDetailRow>($"""
                SELECT TOP 1
                    failed_id                       AS FailedId,
                    email_id                        AS EmailId,
                    po_number                       AS PoNumber,
                    CONVERT(VARCHAR(10), po_date, 120) AS PoDate,
                    product_name                    AS ProductName,
                    quantity                        AS Quantity,
                    amount                          AS Amount,
                    email_from                      AS EmailFrom
                FROM dbo.pobrain_failed_transactions
                WHERE email_from = {request.EmailFrom.Trim()}
                ORDER BY failed_id DESC
                """).ToListAsync();
            failedRecord = records.FirstOrDefault();
        }

        if (failedRecord == null)
        {
            return new RerunFailedTransactionResponse
            {
                Success = false,
                Message = "Failed transaction record not found."
            };
        }

        string emailToCheck = (request.EmailFrom ?? failedRecord.EmailFrom ?? "").Trim();
        if (string.IsNullOrWhiteSpace(emailToCheck))
        {
            return new RerunFailedTransactionResponse
            {
                Success = false,
                Message = "No customer email address is associated with this PO."
            };
        }

        // 2. Check if customer is registered in dbo.tblRegistration
        var customerRows = await db.Database.SqlQuery<CustomerMasterRow>($"""
            SELECT TOP 1
                PersonID                                     AS PersonId,
                CompanyCode                                  AS CompanyCode,
                ISNULL(Discount, 0)                          AS Discount,
                ContPerson                                   AS FullName,
                Phone1                                       AS MobileNo,
                City                                         AS City,
                CompanyName                                  AS CompanyName,
                GSTNo                                        AS GSTNo
            FROM dbo.tblRegistration
            WHERE RTRIM(LTRIM(EMailID)) = {emailToCheck}
            """).ToListAsync();

        var customer = customerRows.FirstOrDefault();
        if (customer == null)
        {
            return new RerunFailedTransactionResponse
            {
                Success = false,
                Message = $"Customer email '{emailToCheck}' is still not registered in tblRegistration. Please add it to the ERP first."
            };
        }

        // 3. Retrieve PO header and line items from pobrain_purchase_orders (if present)
        var poNumber = failedRecord.PoNumber ?? "UNKNOWN";
        var poDateStr = failedRecord.PoDate ?? AppClock.NowIst.ToString("yyyy-MM-dd");

        PoHeaderRow? poHeader = null;
        if (!string.IsNullOrWhiteSpace(failedRecord.PoNumber) && failedRecord.PoNumber != "UNKNOWN")
        {
            var poList = await db.Database.SqlQuery<PoHeaderRow>($"""
                SELECT TOP 1
                    po_id                                        AS PoId,
                    po_number                                    AS PoNumber,
                    CONVERT(VARCHAR(10), po_date, 120)           AS PoDate,
                    delivery_address                             AS DeliveryAddress,
                    total_amount                                 AS TotalAmount
                FROM dbo.pobrain_purchase_orders
                WHERE po_number = {failedRecord.PoNumber.Trim()}
                ORDER BY po_id DESC
                """).ToListAsync();
            poHeader = poList.FirstOrDefault();
        }
        else if (failedRecord.EmailId.HasValue)
        {
            var poList = await db.Database.SqlQuery<PoHeaderRow>($"""
                SELECT TOP 1
                    po_id                                        AS PoId,
                    po_number                                    AS PoNumber,
                    CONVERT(VARCHAR(10), po_date, 120)           AS PoDate,
                    delivery_address                             AS DeliveryAddress,
                    total_amount                                 AS TotalAmount
                FROM dbo.pobrain_purchase_orders
                WHERE email_id = {failedRecord.EmailId.Value}
                ORDER BY po_id DESC
                """).ToListAsync();
            poHeader = poList.FirstOrDefault();
        }

        if (poHeader != null)
        {
            poNumber = poHeader.PoNumber;
            if (!string.IsNullOrWhiteSpace(poHeader.PoDate))
            {
                poDateStr = poHeader.PoDate;
            }
        }

        // Fetch Line Items
        List<PoItemRow> lineItems = [];
        if (poHeader != null)
        {
            lineItems = await db.Database.SqlQuery<PoItemRow>($"""
                SELECT
                    line_number                                  AS LineNumber,
                    product_name                                 AS ProductName,
                    ISNULL(cas_number, '')                       AS CasNumber,
                    ISNULL(cat_number, '')                       AS CatNumber,
                    ISNULL(hsn_code, '')                         AS HsnCode,
                    quantity                                     AS Quantity,
                    ISNULL(unit_of_measure, 'EA')                AS UnitOfMeasure,
                    ISNULL(unit_price, 0)                        AS UnitPrice,
                    amount                                       AS Amount,
                    ISNULL(cgst_rate, 0) + ISNULL(sgst_rate, 0) + ISNULL(igst_rate, 0) AS GstTax
                FROM dbo.pobrain_purchase_order_line_items
                WHERE po_id = {poHeader.PoId}
                ORDER BY line_number ASC
                """).ToListAsync();
        }

        // Fallback: If no line items exist in DB, synthesize one from the failed transaction record
        if (lineItems.Count == 0)
        {
            lineItems.Add(new PoItemRow
            {
                LineNumber = 1,
                ProductName = failedRecord.ProductName ?? "PO Item",
                CasNumber = "",
                CatNumber = "",
                HsnCode = "",
                Quantity = failedRecord.Quantity ?? 1,
                UnitOfMeasure = "EA",
                UnitPrice = failedRecord.Amount ?? 0,
                Amount = failedRecord.Amount ?? 0,
                GstTax = 18
            });
        }

        // 4. Retrieve email metadata if available
        string emailNotes = "";
        if (failedRecord.EmailId.HasValue)
        {
            var emailMeta = await db.Database.SqlQuery<EmailMetaRow>($"""
                SELECT TOP 1
                    email_subject                                AS Subject,
                    email_body_preview                           AS BodyText
                FROM dbo.pobrain_emails
                WHERE email_id = {failedRecord.EmailId.Value}
                """).ToListAsync();
            emailNotes = emailMeta.FirstOrDefault()?.BodyText ?? "";
        }

        string commentText = !string.IsNullOrWhiteSpace(emailNotes)
            ? (emailNotes.Length > 1000 ? emailNotes[..1000] : emailNotes)
            : $"PO {poNumber} rerun from Web Interface.";

        // 5. Execute ERP insertion inside an Atomic SQL Transaction
        long newOrderId;
        await using (var transaction = await db.Database.BeginTransactionAsync())
        {
            try
            {
                // 5a. Generate next OrderID (MAX + 1 across tblClientOrder and SAT_WebOrder_Tracking)
                var orderIdRows = await db.Database.SqlQuery<OrderIdRow>($"""
                    SELECT ISNULL(MAX(n), 0) + 1 AS NewOrderId FROM (
                        SELECT MAX(OrderID) AS n FROM dbo.tblClientOrder
                        UNION ALL
                        SELECT MAX(WebOrderID) FROM dbo.SAT_WebOrder_Tracking
                    ) x
                    """).ToListAsync();
                newOrderId = orderIdRows.FirstOrDefault()?.NewOrderId ?? 1;

                var companyCode = customer.CompanyCode ?? "";
                int discPct = customer.Discount;

                // 5b. Insert each line item into dbo.tblClientOrder
                foreach (var item in lineItems)
                {
                    decimal qty = item.Quantity > 0 ? item.Quantity : 1;
                    decimal unitPrice = item.UnitPrice;
                    decimal price = item.Amount > 0 ? item.Amount : (qty * unitPrice);
                    decimal discountPrice = discPct > 0 ? Math.Round(price * (100 - discPct) / 100m, 2) : price;
                    int gstRate = (int)Math.Round(item.GstTax > 0 ? item.GstTax : 18m);
                    decimal gstPrice = Math.Round(discountPrice * gstRate / 100m, 2);
                    string chemicalName = item.ProductName.Length > 500 ? item.ProductName[..500] : item.ProductName;
                    string catNo = item.CatNumber.Length > 50 ? item.CatNumber[..50] : item.CatNumber;
                    string casNo = item.CasNumber.Length > 30 ? item.CasNumber[..30] : item.CasNumber;
                    string hsn = item.HsnCode.Length > 20 ? item.HsnCode[..20] : item.HsnCode;
                    string packSize = item.UnitOfMeasure.Length > 50 ? item.UnitOfMeasure[..50] : item.UnitOfMeasure;

                    await db.Database.ExecuteSqlRawAsync("""
                        INSERT INTO dbo.tblClientOrder (
                            PersonID, CompanyCode, PackCode, PackSize, CASNo, ChemicalName,
                            CatalogNo, Quantity, UnitPrice, CurrentQty, DItemCode, ItemCode,
                            Price, Discount, DiscountPrice, CAS, OrderID, POID, Flag,
                            OrderDate, HSNCode, GSTTAX, Plateform, GstPrice
                        ) VALUES (
                            @p0, @p1, NULL, @p2, @p3, @p4,
                            @p5, @p6, @p7, @p8, NULL, @p9,
                            @p10, @p11, @p12, @p13, @p14, @p15, '0',
                            @p16, @p17, @p18, 'Email', @p19
                        )
                        """,
                        customer.PersonId,
                        companyCode,
                        packSize,
                        casNo,
                        chemicalName,
                        catNo,
                        qty,
                        unitPrice.ToString("F2"),
                        (int)qty,
                        catNo,
                        price,
                        discPct,
                        discountPrice,
                        casNo,
                        newOrderId,
                        poNumber,
                        poDateStr,
                        hsn,
                        gstRate,
                        gstPrice
                    );
                }

                // 5c. Insert into dbo.tblComment (if notes exist)
                await db.Database.ExecuteSqlRawAsync("""
                    INSERT INTO dbo.tblComment (OrderID, Comment, CreatedDate, CreatedBy)
                    VALUES (@p0, @p1, DATEADD(MINUTE, 330, GETUTCDATE()), @p2)
                    """,
                    newOrderId,
                    commentText,
                    customer.PersonId
                );

                // 5d. Insert into dbo.SAT_WebOrder_Tracking
                string soNo = poNumber.Length > 20 ? poNumber[..20] : poNumber;
                await db.Database.ExecuteSqlRawAsync("""
                    INSERT INTO dbo.SAT_WebOrder_Tracking (
                        WebOrderID, WebOrderDate, WebOrderCustCode, WebOrderTimeStamp, SONo, SODate
                    ) VALUES (
                        @p0, @p1, @p2, DATEADD(MINUTE, 330, GETUTCDATE()), @p3, @p4
                    )
                    """,
                    newOrderId,
                    poDateStr,
                    companyCode,
                    soNo,
                    poDateStr
                );

                // 5e. Update dbo.pobrain_purchase_orders
                if (poHeader != null)
                {
                    await db.Database.ExecuteSqlRawAsync("""
                        UPDATE dbo.pobrain_purchase_orders
                        SET is_erp_inserted = 1,
                            erp_order_id = @p0,
                            updated_at = DATEADD(MINUTE, 330, GETUTCDATE()),
                            updated_by = @p1
                        WHERE po_id = @p2
                        """,
                        newOrderId,
                        user,
                        poHeader.PoId
                    );
                }

                // 5f. Update dbo.pobrain_failed_transactions
                await db.Database.ExecuteSqlRawAsync("""
                    UPDATE dbo.pobrain_failed_transactions
                    SET is_reprocessed = 1,
                        reprocessed_by = @p0,
                        reprocessed_at = DATEADD(MINUTE, 330, GETUTCDATE()),
                        updated_at = DATEADD(MINUTE, 330, GETUTCDATE())
                    WHERE failed_id = @p1
                    """,
                    user,
                    failedRecord.FailedId
                );

                // 5g. Update dbo.pobrain_emails
                if (failedRecord.EmailId.HasValue && failedRecord.EmailId.Value > 0)
                {
                    await db.Database.ExecuteSqlRawAsync("""
                        UPDATE dbo.pobrain_emails
                        SET erp_insertion_status = 'SUCCESS',
                            status_id = 2,
                            updated_at = DATEADD(MINUTE, 330, GETUTCDATE())
                        WHERE email_id = @p0
                        """,
                        failedRecord.EmailId.Value
                    );
                }

                await transaction.CommitAsync();
            }
            catch (Exception ex)
            {
                await transaction.RollbackAsync();
                logger.LogError(ex, "Transaction rolled back during rerun for PO {PoNum}", poNumber);
                return new RerunFailedTransactionResponse
                {
                    Success = false,
                    Message = $"ERP insertion failed: {ex.Message}"
                };
            }
        }

        // 6. Dispatch acknowledgment email using unified EmailService
        bool emailSent = false;
        string emailMessage = "";
        try
        {
            var emailItems = lineItems.Select(itm =>
            {
                decimal qty = itm.Quantity > 0 ? itm.Quantity : 1;
                decimal unitPrice = itm.UnitPrice;
                decimal price = itm.Amount > 0 ? itm.Amount : (qty * unitPrice);
                decimal discountPrice = customer.Discount > 0 ? Math.Round(price * (100 - customer.Discount) / 100m, 2) : price;
                int gstRate = (int)Math.Round(itm.GstTax > 0 ? itm.GstTax : 18m);
                decimal gstPrice = Math.Round(discountPrice * gstRate / 100m, 2);

                return new OrderItemEmailDto
                {
                    OrderNo = newOrderId,
                    ItemCode = itm.CatNumber,
                    HsnCode = itm.HsnCode,
                    GstRate = gstRate,
                    CasNo = itm.CasNumber,
                    ChemicalName = itm.ProductName,
                    PackSize = itm.UnitOfMeasure,
                    Quantity = qty,
                    UnitPrice = unitPrice,
                    Price = price,
                    DiscountPercent = customer.Discount,
                    DiscountPrice = discountPrice,
                    GstPrice = gstPrice,
                    TotalPrice = discountPrice + gstPrice
                };
            }).ToList();

            var (sent, msg) = await emailService.SendOrderAcknowledgmentAsync(new OrderAcknowledgmentEmailRequest
            {
                OrderId = newOrderId,
                PoNumber = poNumber,
                RecipientEmail = emailToCheck,
                Customer = new CustomerDetailsDto
                {
                    CompanyName = customer.CompanyName,
                    CustomerName = customer.FullName ?? customer.CompanyName,
                    Email = emailToCheck,
                    ContactNo = customer.MobileNo,
                    City = customer.City,
                    GstNo = customer.GSTNo,
                    Comments = commentText
                },
                Items = emailItems,
                Comments = commentText,
                AcceptanceDate = poDateStr
            });

            emailSent = sent;
            emailMessage = msg;
            if (sent)
            {
                logger.LogInformation("Order #{OrderId} acknowledgment email dispatched successfully to {Email}", newOrderId, emailToCheck);
            }
            else
            {
                logger.LogWarning("Order #{OrderId} acknowledgment email dispatch returned false: {Msg}", newOrderId, msg);
            }
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed sending order acknowledgment email for Order #{OrderId} (non-fatal)", newOrderId);
            emailMessage = ex.Message;
        }

        logger.LogInformation("Successfully reprocessed failed transaction ID={FailedId}, PO={PoNum}, NewOrderId={OrderId}",
            failedRecord.FailedId, poNumber, newOrderId);

        string userMessage = emailSent
            ? $"Successfully created ERP Order #{newOrderId} and sent acknowledgment email to {emailToCheck}."
            : $"Successfully created ERP Order #{newOrderId}. (Email notice: {emailMessage})";

        return new RerunFailedTransactionResponse
        {
            Success = true,
            OrderId = newOrderId,
            Message = userMessage
        };
    }

    private static string EscapeCsv(string? value)
    {
        if (string.IsNullOrEmpty(value))
            return string.Empty;

        if (value.Contains(",") || value.Contains("\"") || value.Contains("\n"))
            return $"\"{value.Replace("\"", "\"\"")}\"";

        return value;
    }

    private sealed class FailedRow
    {
        public long     FailedId    { get; set; }
        public string?  PoNumber    { get; set; }
        public string?  PoDate      { get; set; }
        public string?  ProductName { get; set; }
        public decimal? Quantity    { get; set; }
        public decimal? Amount      { get; set; }
        public string?  EmailFrom   { get; set; }
        public string?  EmailDate   { get; set; }
        public string   ErrorReason { get; set; } = null!;
        public string   FailedAt    { get; set; } = null!;
    }

    private sealed class FailedDetailRow
    {
        public long     FailedId    { get; set; }
        public long?    EmailId     { get; set; }
        public string?  PoNumber    { get; set; }
        public string?  PoDate      { get; set; }
        public string?  ProductName { get; set; }
        public decimal? Quantity    { get; set; }
        public decimal? Amount      { get; set; }
        public string?  EmailFrom   { get; set; }
    }

    private sealed class CustomerMasterRow
    {
        public int     PersonId    { get; set; }
        public string? CompanyCode { get; set; }
        public int     Discount    { get; set; }
        public string? FullName    { get; set; }
        public string? MobileNo    { get; set; }
        public string? City        { get; set; }
        public string? CompanyName { get; set; }
        public string? GSTNo       { get; set; }
    }

    private sealed class PoHeaderRow
    {
        public long    PoId            { get; set; }
        public string  PoNumber        { get; set; } = string.Empty;
        public string? PoDate          { get; set; }
        public string? DeliveryAddress { get; set; }
        public decimal TotalAmount     { get; set; }
    }

    private sealed class PoItemRow
    {
        public int     LineNumber    { get; set; }
        public string  ProductName   { get; set; } = string.Empty;
        public string  CasNumber     { get; set; } = string.Empty;
        public string  CatNumber     { get; set; } = string.Empty;
        public string  HsnCode       { get; set; } = string.Empty;
        public decimal Quantity      { get; set; }
        public string  UnitOfMeasure { get; set; } = "EA";
        public decimal UnitPrice     { get; set; }
        public decimal Amount        { get; set; }
        public decimal GstTax        { get; set; } = 18;
    }

    private sealed class EmailMetaRow
    {
        public string? Subject  { get; set; }
        public string? BodyText { get; set; }
    }

    private sealed class OrderIdRow
    {
        public long NewOrderId { get; set; }
    }
}
