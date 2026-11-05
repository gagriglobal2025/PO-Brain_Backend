using Microsoft.EntityFrameworkCore;
using POBrain.API.Data;
using POBrain.API.Models.Common;
using POBrain.API.Models.FailedTransactions;
using System.Text;

namespace POBrain.API.Services;

public class FailedTransactionService(PoBrainDbContext db) : IFailedTransactionService
{
    public async Task<PagedResponse<FailedTransactionDto>> GetAllAsync(string? search, int page, int pageSize)
    {
        page     = Math.Max(1, page);
        pageSize = Math.Clamp(pageSize, 1, 200);
        int offset = (page - 1) * pageSize;

        var pattern = string.IsNullOrWhiteSpace(search) ? "%" : $"%{search.Trim()}%";

        var countRows = await db.Database.SqlQuery<CountRow>($"""
            SELECT COUNT(*) AS Total
            FROM dbo.pobrain_failed_transactions
            WHERE (po_number    LIKE {pattern}
                OR product_name LIKE {pattern}
                OR email_from   LIKE {pattern})
            """).ToListAsync();

        int total = countRows.FirstOrDefault()?.Total ?? 0;

        var rows = await db.Database.SqlQuery<FailedRow>($"""
            SELECT
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
            WHERE (po_number    LIKE {pattern}
                OR product_name LIKE {pattern}
                OR email_from   LIKE {pattern})
            ORDER BY failed_at DESC
            OFFSET {offset} ROWS FETCH NEXT {pageSize} ROWS ONLY
            """).ToListAsync();

        var data = rows.Select(r => new FailedTransactionDto
        {
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
            WHERE (po_number    LIKE {pattern}
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
            WHERE (po_number    LIKE {pattern}
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
            WHERE (po_number    LIKE {pattern}
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
}
