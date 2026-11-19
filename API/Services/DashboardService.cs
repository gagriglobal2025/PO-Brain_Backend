using Microsoft.EntityFrameworkCore;
using POBrain.API.Data;
using POBrain.API.Models.Dashboard;

namespace POBrain.API.Services;

public class DashboardService(PoBrainDbContext db) : IDashboardService
{
    public async Task<DashboardStatsDto> GetStatsAsync()
    {
        var rows = await db.Database.SqlQuery<StatsRow>($"""
            SELECT
                (SELECT COUNT(*) FROM dbo.pobrain_emails) AS TotalEmails,
                (SELECT COUNT(*) FROM dbo.pobrain_purchase_orders WHERE is_erp_inserted = 1) AS Processed,
                (SELECT COUNT(*) FROM dbo.pobrain_failed_transactions WHERE is_reprocessed = 0) AS Failed,
                (SELECT COUNT(*) FROM dbo.pobrain_emails WHERE status_id = 2) AS InProgress
            """).ToListAsync();

        var r = rows.FirstOrDefault() ?? new StatsRow();
        var effectiveTotal = Math.Max(r.TotalEmails, r.Processed + r.Failed);
        var successRate = effectiveTotal > 0
            ? Math.Round((double)r.Processed / effectiveTotal * 100, 1)
            : 100d;
        var status = r.InProgress > 0 ? "Processing" : "Live";

        return new DashboardStatsDto
        {
            TotalEmails   = effectiveTotal,
            Processed     = r.Processed,
            Failed        = r.Failed,
            SuccessRate   = successRate,
            CurrentStatus = status
        };
    }

    public async Task<IEnumerable<RecentExtractionDto>> GetRecentExtractionsAsync(int count = 10)
    {
        var rows = await db.Database.SqlQuery<RecentRow>($"""
            SELECT TOP ({count})
                po.po_number                                            AS PoNumber,
                COALESCE(po.vendor_name, 'Unknown Vendor')             AS VendorName,
                COALESCE(po.total_amount, 0)                            AS TotalAmount,
                CAST(po.po_date AS DATETIME)                            AS PoDate,
                po.created_at                                           AS CreatedAt,
                CASE WHEN po.is_erp_inserted = 1 THEN 'SUCCESS'
                     WHEN ft.failed_id IS NOT NULL THEN 'FAILED'
                     ELSE 'PENDING'
                END                                                     AS StatusName
            FROM dbo.pobrain_purchase_orders po
            LEFT JOIN dbo.pobrain_failed_transactions ft 
                ON po.po_number = ft.po_number AND ft.is_reprocessed = 0
            WHERE po.po_number NOT LIKE 'TEMP-%'
            ORDER BY po.created_at DESC
            """).ToListAsync();

        return rows.Select(r => new RecentExtractionDto
        {
            Id          = r.PoNumber,
            PoNumber    = r.PoNumber,
            Name        = r.VendorName,
            VendorName  = r.VendorName,
            Amount      = r.TotalAmount,
            TotalAmount = r.TotalAmount,
            Status      = r.StatusName,
            PoDate      = r.PoDate?.ToString("yyyy-MM-dd"),
            CreatedAt   = r.CreatedAt.ToString("o")
        });
    }

    public async Task<HealthStatusDto> GetHealthStatusAsync()
    {
        // Try snapshots first; fall back to computing from live operational data
        var snaps = await db.Database.SqlQuery<SnapRow>($"""
            SELECT component_name AS ComponentName, health_pct AS HealthPct
            FROM (
                SELECT component_name, health_pct,
                       ROW_NUMBER() OVER (PARTITION BY component_name ORDER BY snapshot_at DESC) AS rn
                FROM dbo.pobrain_system_health_snapshots
            ) t WHERE rn = 1
            """).ToListAsync();

        double Get(string name) =>
            (double)(snaps.FirstOrDefault(s => s.ComponentName.Equals(name, StringComparison.OrdinalIgnoreCase))
                 ?.HealthPct ?? -1);

        var engine = Get("ExtractionEngine");
        var parser = Get("EmailParser");
        var ocr    = Get("OCRPipeline");

        if (engine < 0 || parser < 0 || ocr < 0)
        {
            // Compute from live operational counts
            var live = await db.Database.SqlQuery<LiveHealth>($"""
                SELECT
                    CASE WHEN total_emails = 0 THEN 100.0
                         ELSE CAST(total_emails - parse_failures AS FLOAT) / total_emails * 100 END AS ParserPct,
                    CASE WHEN total_jobs = 0 THEN 100.0
                         ELSE CAST(completed_jobs AS FLOAT) / total_jobs * 100 END AS EnginePct,
                    CASE WHEN total_ocr = 0 THEN 100.0
                         ELSE CAST(completed_ocr AS FLOAT) / total_ocr * 100 END AS OcrPct
                FROM (
                    SELECT
                        COUNT(*) AS total_emails,
                        SUM(CASE WHEN failure_reason LIKE '%PARSE%' THEN 1 ELSE 0 END) AS parse_failures
                    FROM dbo.pobrain_emails
                ) e,
                (
                    SELECT
                        COUNT(*) AS total_jobs,
                        SUM(CASE WHEN status_id = 23 THEN 1 ELSE 0 END) AS completed_jobs
                    FROM dbo.pobrain_extraction_jobs
                ) j,
                (
                    SELECT
                        COUNT(*) AS total_ocr,
                        SUM(CASE WHEN status_id = 16 THEN 1 ELSE 0 END) AS completed_ocr
                    FROM dbo.pobrain_email_attachments
                    WHERE ocr_required = 1
                ) a
                """).ToListAsync();

            var l = live.FirstOrDefault() ?? new LiveHealth();
            parser = l.ParserPct;
            engine = l.EnginePct;
            ocr    = l.OcrPct;
        }

        return new HealthStatusDto
        {
            ExtractionEngine = Math.Round(engine, 1),
            EmailParser      = Math.Round(parser, 1),
            OcrPipeline      = Math.Round(ocr,    1)
        };
    }

    // ── Internal query result types ───────────────────────────────────────────

    private sealed class StatsRow
    {
        public int TotalEmails { get; set; }
        public int Processed   { get; set; }
        public int Failed      { get; set; }
        public int InProgress  { get; set; }
    }

    private sealed class RecentRow
    {
        public string    PoNumber    { get; set; } = null!;
        public string    VendorName  { get; set; } = null!;
        public decimal   TotalAmount { get; set; }
        public DateTime? PoDate      { get; set; }
        public DateTime  CreatedAt   { get; set; }
        public string    StatusName  { get; set; } = null!;
    }

    private sealed class SnapRow
    {
        public string  ComponentName { get; set; } = null!;
        public decimal HealthPct     { get; set; }
    }

    private sealed class LiveHealth
    {
        public double ParserPct { get; set; }
        public double EnginePct { get; set; }
        public double OcrPct    { get; set; }
    }
}
