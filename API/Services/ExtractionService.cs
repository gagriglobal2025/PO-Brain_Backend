using Microsoft.EntityFrameworkCore;
using POBrain.API.Data;
using POBrain.API.Models.Common;
using POBrain.API.Models.Extractions;
using System.Text;

namespace POBrain.API.Services;

public class ExtractionService(PoBrainDbContext db) : IExtractionService
{
    public async Task<PagedResponse<ExtractionDto>> GetAllAsync(string? search, int page, int pageSize)
    {
        page     = Math.Max(1, page);
        pageSize = Math.Clamp(pageSize, 1, 200);
        int offset = (page - 1) * pageSize;

        var pattern = string.IsNullOrWhiteSpace(search) ? "%" : $"%{search.Trim()}%";

        var countRows = await db.Database.SqlQuery<CountRow>($"""
            SELECT COUNT(*) AS Total
            FROM dbo.pobrain_purchase_order_line_items li
            JOIN dbo.pobrain_purchase_orders po ON li.po_id = po.po_id
            WHERE po.po_number NOT LIKE 'TEMP-%'
              AND (po.po_number    LIKE {pattern}
                OR li.product_name LIKE {pattern}
                OR li.cas_number   LIKE {pattern})
            """).ToListAsync();

        int total = countRows.FirstOrDefault()?.Total ?? 0;

        var rows = await db.Database.SqlQuery<ExtractionRow>($"""
            SELECT
                po.po_number       AS PoNumber,
                li.product_name    AS ProductName,
                li.cas_number      AS CasNumber,
                li.quantity        AS Quantity,
                li.amount          AS Amount,
                po.delivery_address AS DeliveryAddress,
                po.branch_location  AS BranchLocation,
                s.status_name      AS StatusName
            FROM dbo.pobrain_purchase_order_line_items li
            JOIN dbo.pobrain_purchase_orders     po ON li.po_id     = po.po_id
            JOIN dbo.pobrain_lkp_status           s ON po.status_id = s.status_id
            WHERE po.po_number NOT LIKE 'TEMP-%'
              AND (po.po_number    LIKE {pattern}
                OR li.product_name LIKE {pattern}
                OR li.cas_number   LIKE {pattern})
            ORDER BY li.created_at DESC
            OFFSET {offset} ROWS FETCH NEXT {pageSize} ROWS ONLY
            """).ToListAsync();

        var data = rows.Select(r => new ExtractionDto
        {
            PoNumber        = r.PoNumber,
            ProductName     = r.ProductName,
            CasNumber       = r.CasNumber,
            Quantity        = r.Quantity,
            Amount          = r.Amount,
            DeliveryAddress = r.DeliveryAddress,
            BranchLocation  = r.BranchLocation,
            Status          = r.StatusName.Contains("Active", StringComparison.OrdinalIgnoreCase)
                              ? "Success" : "Failed"
        });

        return new PagedResponse<ExtractionDto>
        {
            Data       = data,
            TotalCount = total,
            Page       = page,
            PageSize   = pageSize
        };
    }

    private sealed class CountRow { public int Total { get; set; } }

    public async Task<PagedResponse<ExtractionDto>> GetAllWithFiltersAsync(ExtractionFilterRequest filter)
    {
        filter.Page = Math.Max(1, filter.Page);
        filter.PageSize = Math.Clamp(filter.PageSize, 1, 200);
        int offset = (filter.Page - 1) * filter.PageSize;

        var pattern = string.IsNullOrWhiteSpace(filter.Search) ? "%" : $"%{filter.Search.Trim()}%";
        var fromDate = filter.FromDate?.Date;
        var toDate = filter.ToDate?.Date.AddDays(1);
        var minAmount = filter.MinAmount;
        var maxAmount = filter.MaxAmount;
        var status = string.IsNullOrWhiteSpace(filter.Status) ? "%" : filter.Status.Trim();
        var branch = string.IsNullOrWhiteSpace(filter.BranchLocation) ? "%" : filter.BranchLocation.Trim();

        var countRows = await db.Database.SqlQuery<CountRow>($"""
            SELECT COUNT(*) AS Total
            FROM dbo.pobrain_purchase_order_line_items li
            JOIN dbo.pobrain_purchase_orders po ON li.po_id = po.po_id
            JOIN dbo.pobrain_lkp_status s ON po.status_id = s.status_id
            WHERE po.po_number NOT LIKE 'TEMP-%'
              AND (po.po_number    LIKE {pattern}
                OR li.product_name LIKE {pattern}
                OR li.cas_number   LIKE {pattern})
              AND ({status} = '%' OR s.status_name LIKE {status})
              AND ({branch} = '%' OR po.branch_location LIKE {branch})
              AND ({fromDate} IS NULL OR po.po_date >= {fromDate})
              AND ({toDate} IS NULL OR po.po_date < {toDate})
              AND ({minAmount} IS NULL OR li.amount >= {minAmount})
              AND ({maxAmount} IS NULL OR li.amount <= {maxAmount})
            """).ToListAsync();

        int total = countRows.FirstOrDefault()?.Total ?? 0;

        var rows = await db.Database.SqlQuery<ExtractionRow>($"""
            SELECT
                po.po_number       AS PoNumber,
                li.product_name    AS ProductName,
                li.cas_number      AS CasNumber,
                li.quantity        AS Quantity,
                li.amount          AS Amount,
                po.delivery_address AS DeliveryAddress,
                po.branch_location  AS BranchLocation,
                s.status_name      AS StatusName
            FROM dbo.pobrain_purchase_order_line_items li
            JOIN dbo.pobrain_purchase_orders     po ON li.po_id     = po.po_id
            JOIN dbo.pobrain_lkp_status           s ON po.status_id = s.status_id
            WHERE po.po_number NOT LIKE 'TEMP-%'
              AND (po.po_number    LIKE {pattern}
                OR li.product_name LIKE {pattern}
                OR li.cas_number   LIKE {pattern})
              AND ({status} = '%' OR s.status_name LIKE {status})
              AND ({branch} = '%' OR po.branch_location LIKE {branch})
              AND ({fromDate} IS NULL OR po.po_date >= {fromDate})
              AND ({toDate} IS NULL OR po.po_date < {toDate})
              AND ({minAmount} IS NULL OR li.amount >= {minAmount})
              AND ({maxAmount} IS NULL OR li.amount <= {maxAmount})
            ORDER BY li.created_at DESC
            OFFSET {offset} ROWS FETCH NEXT {filter.PageSize} ROWS ONLY
            """).ToListAsync();

        var data = rows.Select(r => new ExtractionDto
        {
            PoNumber        = r.PoNumber,
            ProductName     = r.ProductName,
            CasNumber       = r.CasNumber,
            Quantity        = r.Quantity,
            Amount          = r.Amount,
            DeliveryAddress = r.DeliveryAddress,
            BranchLocation  = r.BranchLocation,
            Status          = r.StatusName.Contains("Active", StringComparison.OrdinalIgnoreCase)
                              ? "Success" : "Failed"
        });

        return new PagedResponse<ExtractionDto>
        {
            Data       = data,
            TotalCount = total,
            Page       = filter.Page,
            PageSize   = filter.PageSize
        };
    }

    public async Task<byte[]> ExportToCsvAsync(ExtractionFilterRequest filter)
    {
        var pattern = string.IsNullOrWhiteSpace(filter.Search) ? "%" : $"%{filter.Search.Trim()}%";
        var fromDate = filter.FromDate?.Date;
        var toDate = filter.ToDate?.Date.AddDays(1);
        var minAmount = filter.MinAmount;
        var maxAmount = filter.MaxAmount;
        var status = string.IsNullOrWhiteSpace(filter.Status) ? "%" : filter.Status.Trim();
        var branch = string.IsNullOrWhiteSpace(filter.BranchLocation) ? "%" : filter.BranchLocation.Trim();

        var rows = await db.Database.SqlQuery<ExtractionRow>($"""
            SELECT
                po.po_number       AS PoNumber,
                li.product_name    AS ProductName,
                li.cas_number      AS CasNumber,
                li.quantity        AS Quantity,
                li.amount          AS Amount,
                po.delivery_address AS DeliveryAddress,
                po.branch_location  AS BranchLocation,
                s.status_name      AS StatusName
            FROM dbo.pobrain_purchase_order_line_items li
            JOIN dbo.pobrain_purchase_orders     po ON li.po_id     = po.po_id
            JOIN dbo.pobrain_lkp_status           s ON po.status_id = s.status_id
            WHERE po.po_number NOT LIKE 'TEMP-%'
              AND (po.po_number    LIKE {pattern}
                OR li.product_name LIKE {pattern}
                OR li.cas_number   LIKE {pattern})
              AND ({status} = '%' OR s.status_name LIKE {status})
              AND ({branch} = '%' OR po.branch_location LIKE {branch})
              AND ({fromDate} IS NULL OR po.po_date >= {fromDate})
              AND ({toDate} IS NULL OR po.po_date < {toDate})
              AND ({minAmount} IS NULL OR li.amount >= {minAmount})
              AND ({maxAmount} IS NULL OR li.amount <= {maxAmount})
            ORDER BY li.created_at DESC
            """).ToListAsync();

        var csv = new StringBuilder();
        csv.AppendLine("PO Number,Product Name,CAS Number,Quantity,Amount,Delivery Address,Branch Location,Status");

        foreach (var row in rows)
        {
            var status_display = row.StatusName.Contains("Active", StringComparison.OrdinalIgnoreCase) ? "Success" : "Failed";
            csv.AppendLine($"{EscapeCsv(row.PoNumber)},{EscapeCsv(row.ProductName)},{EscapeCsv(row.CasNumber)},{row.Quantity},{row.Amount},{EscapeCsv(row.DeliveryAddress)},{EscapeCsv(row.BranchLocation)},{status_display}");
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

    private sealed class ExtractionRow
    {
        public string  PoNumber        { get; set; } = null!;
        public string  ProductName     { get; set; } = null!;
        public string? CasNumber       { get; set; }
        public decimal Quantity        { get; set; }
        public decimal Amount          { get; set; }
        public string? DeliveryAddress { get; set; }
        public string? BranchLocation  { get; set; }
        public string  StatusName      { get; set; } = null!;
    }
}
