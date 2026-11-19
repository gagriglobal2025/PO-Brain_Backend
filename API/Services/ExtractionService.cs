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
            FROM dbo.pobrain_purchase_orders po
            WHERE po.po_number NOT LIKE 'TEMP-%'
              AND (po.po_number    LIKE {pattern}
                OR po.vendor_name  LIKE {pattern}
                OR EXISTS (
                    SELECT 1 FROM dbo.pobrain_purchase_order_line_items li 
                    WHERE li.po_id = po.po_id 
                      AND (li.product_name LIKE {pattern} OR li.cas_number LIKE {pattern})
                ))
            """).ToListAsync();

        int total = countRows.FirstOrDefault()?.Total ?? 0;

        var poRows = await db.Database.SqlQuery<PoHeaderRow>($"""
            SELECT
                po.po_id           AS PoId,
                po.po_number       AS PoNumber,
                CONVERT(VARCHAR(10), po.po_date, 120) AS PoDate,
                po.vendor_name     AS VendorName,
                po.vendor_email    AS VendorEmail,
                po.subtotal_amount AS SubTotalAmount,
                po.total_tax_amount AS TotalTaxAmount,
                po.total_amount    AS TotalAmount,
                po.delivery_address AS DeliveryAddress,
                po.branch_location  AS BranchLocation,
                s.status_name      AS StatusName,
                ISNULL(po.is_erp_inserted, 0) AS IsErpInserted,
                po.erp_order_id    AS ErpOrderId
            FROM dbo.pobrain_purchase_orders po
            JOIN dbo.pobrain_lkp_status       s ON po.status_id = s.status_id
            WHERE po.po_number NOT LIKE 'TEMP-%'
              AND (po.po_number    LIKE {pattern}
                OR po.vendor_name  LIKE {pattern}
                OR EXISTS (
                    SELECT 1 FROM dbo.pobrain_purchase_order_line_items li 
                    WHERE li.po_id = po.po_id 
                      AND (li.product_name LIKE {pattern} OR li.cas_number LIKE {pattern})
                ))
            ORDER BY po.created_at DESC
            OFFSET {offset} ROWS FETCH NEXT {pageSize} ROWS ONLY
            """).ToListAsync();

        var poIds = poRows.Select(p => p.PoId).ToList();
        var lineItemsByPo = new Dictionary<long, List<ExtractionLineItemDto>>();

        if (poIds.Count > 0)
        {
            var idList = string.Join(",", poIds);
            var rawLineItems = await db.Database.SqlQueryRaw<LineItemRow>($"""
                SELECT
                    li.line_item_id   AS LineItemId,
                    li.po_id          AS PoId,
                    li.line_number    AS LineNumber,
                    li.product_name   AS ProductName,
                    li.cas_number     AS CasNumber,
                    li.cat_number     AS CatNumber,
                    li.hsn_code       AS HsnCode,
                    li.quantity       AS Quantity,
                    li.unit_of_measure AS UnitOfMeasure,
                    li.unit_price     AS UnitPrice,
                    li.amount         AS Amount
                FROM dbo.pobrain_purchase_order_line_items li
                WHERE li.po_id IN ({idList})
                ORDER BY li.line_number ASC
                """).ToListAsync();

            lineItemsByPo = rawLineItems
                .GroupBy(l => l.PoId)
                .ToDictionary(
                    g => g.Key,
                    g => g.Select(l => new ExtractionLineItemDto
                    {
                        LineItemId    = l.LineItemId,
                        LineNumber    = l.LineNumber,
                        ProductName   = l.ProductName ?? string.Empty,
                        CasNumber     = l.CasNumber,
                        CatNumber     = l.CatNumber,
                        HsnCode       = l.HsnCode,
                        Quantity      = l.Quantity,
                        UnitOfMeasure = l.UnitOfMeasure,
                        UnitPrice     = l.UnitPrice,
                        Amount        = l.Amount
                    }).ToList()
                );
        }

        var data = poRows.Select(r =>
        {
            lineItemsByPo.TryGetValue(r.PoId, out var items);
            items ??= [];
            var firstItem = items.FirstOrDefault();

            return new ExtractionDto
            {
                PoId            = r.PoId,
                PoNumber        = r.PoNumber,
                PoDate          = r.PoDate,
                VendorName      = r.VendorName,
                VendorEmail     = r.VendorEmail,
                ProductName     = firstItem?.ProductName ?? string.Empty,
                CasNumber       = firstItem?.CasNumber,
                Quantity        = firstItem?.Quantity ?? 0,
                Amount          = firstItem?.Amount ?? 0,
                SubTotalAmount  = r.SubTotalAmount,
                TotalTaxAmount  = r.TotalTaxAmount,
                TotalAmount     = r.TotalAmount,
                DeliveryAddress = r.DeliveryAddress,
                BranchLocation  = r.BranchLocation,
                Status          = r.StatusName.Contains("Active", StringComparison.OrdinalIgnoreCase)
                                  ? "Success" : "Failed",
                IsErpInserted   = r.IsErpInserted == true,
                ErpOrderId      = r.ErpOrderId,
                Details         = new ExtractionDetailsDto
                {
                    PoNumber    = r.PoNumber,
                    PoDate      = r.PoDate,
                    VendorName  = r.VendorName,
                    VendorEmail = r.VendorEmail,
                    LineItems   = items
                }
            };
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
            FROM dbo.pobrain_purchase_orders po
            JOIN dbo.pobrain_lkp_status s ON po.status_id = s.status_id
            WHERE po.po_number NOT LIKE 'TEMP-%'
              AND (po.po_number    LIKE {pattern}
                OR po.vendor_name  LIKE {pattern}
                OR EXISTS (
                    SELECT 1 FROM dbo.pobrain_purchase_order_line_items li 
                    WHERE li.po_id = po.po_id 
                      AND (li.product_name LIKE {pattern} OR li.cas_number LIKE {pattern})
                ))
              AND ({status} = '%' OR s.status_name LIKE {status})
              AND ({branch} = '%' OR po.branch_location LIKE {branch})
              AND ({fromDate} IS NULL OR po.po_date >= {fromDate})
              AND ({toDate} IS NULL OR po.po_date < {toDate})
              AND ({minAmount} IS NULL OR po.total_amount >= {minAmount})
              AND ({maxAmount} IS NULL OR po.total_amount <= {maxAmount})
            """).ToListAsync();

        int total = countRows.FirstOrDefault()?.Total ?? 0;

        var poRows = await db.Database.SqlQuery<PoHeaderRow>($"""
            SELECT
                po.po_id           AS PoId,
                po.po_number       AS PoNumber,
                CONVERT(VARCHAR(10), po.po_date, 120) AS PoDate,
                po.vendor_name     AS VendorName,
                po.vendor_email    AS VendorEmail,
                po.subtotal_amount AS SubTotalAmount,
                po.total_tax_amount AS TotalTaxAmount,
                po.total_amount    AS TotalAmount,
                po.delivery_address AS DeliveryAddress,
                po.branch_location  AS BranchLocation,
                s.status_name      AS StatusName,
                ISNULL(po.is_erp_inserted, 0) AS IsErpInserted,
                po.erp_order_id    AS ErpOrderId
            FROM dbo.pobrain_purchase_orders po
            JOIN dbo.pobrain_lkp_status       s ON po.status_id = s.status_id
            WHERE po.po_number NOT LIKE 'TEMP-%'
              AND (po.po_number    LIKE {pattern}
                OR po.vendor_name  LIKE {pattern}
                OR EXISTS (
                    SELECT 1 FROM dbo.pobrain_purchase_order_line_items li 
                    WHERE li.po_id = po.po_id 
                      AND (li.product_name LIKE {pattern} OR li.cas_number LIKE {pattern})
                ))
              AND ({status} = '%' OR s.status_name LIKE {status})
              AND ({branch} = '%' OR po.branch_location LIKE {branch})
              AND ({fromDate} IS NULL OR po.po_date >= {fromDate})
              AND ({toDate} IS NULL OR po.po_date < {toDate})
              AND ({minAmount} IS NULL OR po.total_amount >= {minAmount})
              AND ({maxAmount} IS NULL OR po.total_amount <= {maxAmount})
            ORDER BY po.created_at DESC
            OFFSET {offset} ROWS FETCH NEXT {filter.PageSize} ROWS ONLY
            """).ToListAsync();

        var poIds = poRows.Select(p => p.PoId).ToList();
        var lineItemsByPo = new Dictionary<long, List<ExtractionLineItemDto>>();

        if (poIds.Count > 0)
        {
            var idList = string.Join(",", poIds);
            var rawLineItems = await db.Database.SqlQueryRaw<LineItemRow>($"""
                SELECT
                    li.line_item_id   AS LineItemId,
                    li.po_id          AS PoId,
                    li.line_number    AS LineNumber,
                    li.product_name   AS ProductName,
                    li.cas_number     AS CasNumber,
                    li.cat_number     AS CatNumber,
                    li.hsn_code       AS HsnCode,
                    li.quantity       AS Quantity,
                    li.unit_of_measure AS UnitOfMeasure,
                    li.unit_price     AS UnitPrice,
                    li.amount         AS Amount
                FROM dbo.pobrain_purchase_order_line_items li
                WHERE li.po_id IN ({idList})
                ORDER BY li.line_number ASC
                """).ToListAsync();

            lineItemsByPo = rawLineItems
                .GroupBy(l => l.PoId)
                .ToDictionary(
                    g => g.Key,
                    g => g.Select(l => new ExtractionLineItemDto
                    {
                        LineItemId    = l.LineItemId,
                        LineNumber    = l.LineNumber,
                        ProductName   = l.ProductName ?? string.Empty,
                        CasNumber     = l.CasNumber,
                        CatNumber     = l.CatNumber,
                        HsnCode       = l.HsnCode,
                        Quantity      = l.Quantity,
                        UnitOfMeasure = l.UnitOfMeasure,
                        UnitPrice     = l.UnitPrice,
                        Amount        = l.Amount
                    }).ToList()
                );
        }

        var data = poRows.Select(r =>
        {
            lineItemsByPo.TryGetValue(r.PoId, out var items);
            items ??= [];
            var firstItem = items.FirstOrDefault();

            return new ExtractionDto
            {
                PoId            = r.PoId,
                PoNumber        = r.PoNumber,
                PoDate          = r.PoDate,
                VendorName      = r.VendorName,
                VendorEmail     = r.VendorEmail,
                ProductName     = firstItem?.ProductName ?? string.Empty,
                CasNumber       = firstItem?.CasNumber,
                Quantity        = firstItem?.Quantity ?? 0,
                Amount          = firstItem?.Amount ?? 0,
                SubTotalAmount  = r.SubTotalAmount,
                TotalTaxAmount  = r.TotalTaxAmount,
                TotalAmount     = r.TotalAmount,
                DeliveryAddress = r.DeliveryAddress,
                BranchLocation  = r.BranchLocation,
                Status          = r.StatusName.Contains("Active", StringComparison.OrdinalIgnoreCase)
                                  ? "Success" : "Failed",
                IsErpInserted   = r.IsErpInserted == true,
                ErpOrderId      = r.ErpOrderId,
                Details         = new ExtractionDetailsDto
                {
                    PoNumber    = r.PoNumber,
                    PoDate      = r.PoDate,
                    VendorName  = r.VendorName,
                    VendorEmail = r.VendorEmail,
                    LineItems   = items
                }
            };
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

        var poRows = await db.Database.SqlQuery<PoHeaderRow>($"""
            SELECT
                po.po_id           AS PoId,
                po.po_number       AS PoNumber,
                CONVERT(VARCHAR(10), po.po_date, 120) AS PoDate,
                po.vendor_name     AS VendorName,
                po.vendor_email    AS VendorEmail,
                po.subtotal_amount AS SubTotalAmount,
                po.total_tax_amount AS TotalTaxAmount,
                po.total_amount    AS TotalAmount,
                po.delivery_address AS DeliveryAddress,
                po.branch_location  AS BranchLocation,
                s.status_name      AS StatusName,
                ISNULL(po.is_erp_inserted, 0) AS IsErpInserted,
                po.erp_order_id    AS ErpOrderId
            FROM dbo.pobrain_purchase_orders po
            JOIN dbo.pobrain_lkp_status       s ON po.status_id = s.status_id
            WHERE po.po_number NOT LIKE 'TEMP-%'
              AND (po.po_number    LIKE {pattern}
                OR po.vendor_name  LIKE {pattern}
                OR EXISTS (
                    SELECT 1 FROM dbo.pobrain_purchase_order_line_items li 
                    WHERE li.po_id = po.po_id 
                      AND (li.product_name LIKE {pattern} OR li.cas_number LIKE {pattern})
                ))
              AND ({status} = '%' OR s.status_name LIKE {status})
              AND ({branch} = '%' OR po.branch_location LIKE {branch})
              AND ({fromDate} IS NULL OR po.po_date >= {fromDate})
              AND ({toDate} IS NULL OR po.po_date < {toDate})
              AND ({minAmount} IS NULL OR po.total_amount >= {minAmount})
              AND ({maxAmount} IS NULL OR po.total_amount <= {maxAmount})
            ORDER BY po.created_at DESC
            """).ToListAsync();

        var poIds = poRows.Select(p => p.PoId).ToList();
        var lineItemsByPo = new Dictionary<long, List<ExtractionLineItemDto>>();

        if (poIds.Count > 0)
        {
            var idList = string.Join(",", poIds);
            var rawLineItems = await db.Database.SqlQueryRaw<LineItemRow>($"""
                SELECT
                    li.line_item_id   AS LineItemId,
                    li.po_id          AS PoId,
                    li.line_number    AS LineNumber,
                    li.product_name   AS ProductName,
                    li.cas_number     AS CasNumber,
                    li.cat_number     AS CatNumber,
                    li.hsn_code       AS HsnCode,
                    li.quantity       AS Quantity,
                    li.unit_of_measure AS UnitOfMeasure,
                    li.unit_price     AS UnitPrice,
                    li.amount         AS Amount
                FROM dbo.pobrain_purchase_order_line_items li
                WHERE li.po_id IN ({idList})
                ORDER BY li.line_number ASC
                """).ToListAsync();

            lineItemsByPo = rawLineItems
                .GroupBy(l => l.PoId)
                .ToDictionary(
                    g => g.Key,
                    g => g.Select(l => new ExtractionLineItemDto
                    {
                        LineItemId    = l.LineItemId,
                        LineNumber    = l.LineNumber,
                        ProductName   = l.ProductName ?? string.Empty,
                        CasNumber     = l.CasNumber,
                        CatNumber     = l.CatNumber,
                        HsnCode       = l.HsnCode,
                        Quantity      = l.Quantity,
                        UnitOfMeasure = l.UnitOfMeasure,
                        UnitPrice     = l.UnitPrice,
                        Amount        = l.Amount
                    }).ToList()
                );
        }

        var csv = new StringBuilder();
        csv.AppendLine("PO Number,PO Date,Vendor Name,Vendor Email,Sub Total,Tax,Total Amount,Product Name,CAS Number,Cat Number,HSN Code,Quantity,UOM,Unit Price,Item Amount,Delivery Address,Branch Location,Status");

        foreach (var po in poRows)
        {
            var status_display = po.StatusName.Contains("Active", StringComparison.OrdinalIgnoreCase) ? "Success" : "Failed";
            lineItemsByPo.TryGetValue(po.PoId, out var items);

            if (items == null || items.Count == 0)
            {
                csv.AppendLine($"{EscapeCsv(po.PoNumber)},{EscapeCsv(po.PoDate)},{EscapeCsv(po.VendorName)},{EscapeCsv(po.VendorEmail)},{po.SubTotalAmount},{po.TotalTaxAmount},{po.TotalAmount},,,,,,,,{EscapeCsv(po.DeliveryAddress)},{EscapeCsv(po.BranchLocation)},{status_display}");
            }
            else
            {
                foreach (var item in items)
                {
                    csv.AppendLine($"{EscapeCsv(po.PoNumber)},{EscapeCsv(po.PoDate)},{EscapeCsv(po.VendorName)},{EscapeCsv(po.VendorEmail)},{po.SubTotalAmount},{po.TotalTaxAmount},{po.TotalAmount},{EscapeCsv(item.ProductName)},{EscapeCsv(item.CasNumber)},{EscapeCsv(item.CatNumber)},{EscapeCsv(item.HsnCode)},{item.Quantity},{EscapeCsv(item.UnitOfMeasure)},{item.UnitPrice},{item.Amount},{EscapeCsv(po.DeliveryAddress)},{EscapeCsv(po.BranchLocation)},{status_display}");
                }
            }
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

    private sealed class PoHeaderRow
    {
        public long    PoId            { get; set; }
        public string  PoNumber        { get; set; } = null!;
        public string? PoDate          { get; set; }
        public string? VendorName      { get; set; }
        public string? VendorEmail     { get; set; }
        public decimal? SubTotalAmount { get; set; }
        public decimal? TotalTaxAmount { get; set; }
        public decimal? TotalAmount    { get; set; }
        public string? DeliveryAddress { get; set; }
        public string? BranchLocation  { get; set; }
        public string  StatusName      { get; set; } = null!;
        public bool?   IsErpInserted   { get; set; }
        public long?   ErpOrderId      { get; set; }
    }

    private sealed class LineItemRow
    {
        public long    LineItemId    { get; set; }
        public long    PoId          { get; set; }
        public int     LineNumber    { get; set; }
        public string? ProductName   { get; set; }
        public string? CasNumber     { get; set; }
        public string? CatNumber     { get; set; }
        public string? HsnCode       { get; set; }
        public decimal Quantity      { get; set; }
        public string? UnitOfMeasure { get; set; }
        public decimal UnitPrice     { get; set; }
        public decimal Amount        { get; set; }
    }
}
