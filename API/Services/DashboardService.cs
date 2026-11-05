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
                COUNT(*)                                                          AS TotalEmails,
                SUM(CASE WHEN e.status_id = 3  THEN 1 ELSE 0 END)                AS Processed,
                SUM(CASE WHEN e.status_id = 4  THEN 1 ELSE 0 END)                AS Failed,
                SUM(CASE WHEN e.status_id NOT IN (3,4) THEN 1 ELSE 0 END)        AS InProgress
            FROM dbo.pobrain_emails e
            """).ToListAsync();

        var r           = rows.FirstOrDefault() ?? new StatsRow();
        var successRate = r.TotalEmails > 0
            ? Math.Round((double)r.Processed / r.TotalEmails * 100, 1)
            : 0d;
        var status      = r.InProgress > 0 ? "Active" : r.TotalEmails == 0 ? "Idle" : "Active";

        return new DashboardStatsDto
        {
            TotalEmails   = r.TotalEmails,
            Processed     = r.Processed,
            Failed        = r.Failed,
            SuccessRate   = successRate,
            CurrentStatus = status
        };
    }

    public async Task<IEnumerable<RecentExtractionDto>> GetRecentExtractionsAsync(int count = 10)
    {
        return await db.Database.SqlQuery<RecentRow>($"""
            SELECT TOP ({count})
                po.po_number      AS PoNumber,
                li.product_name   AS ProductName,
                li.amount         AS Amount,
                s.status_name     AS StatusName
            FROM dbo.pobrain_purchase_order_line_items li
            JOIN dbo.pobrain_purchase_orders     po ON li.po_id      = po.po_id
            JOIN dbo.pobrain_lkp_status           s ON po.status_id  = s.status_id
            WHERE po.po_number NOT LIKE 'TEMP-%'
            ORDER BY li.created_at DESC
            """)
            .Select(r => new RecentExtractionDto
            {
                Id     = r.PoNumber,
                Name   = r.ProductName,
                Amount = r.Amount,
                Status = r.StatusName.Contains("Active", StringComparison.OrdinalIgnoreCase) ? "SUCCESS" : "FAILED"
            })
            .ToListAsync();
    }

    public async Task<HealthStatusDto> GetHealthStatusAsync()
    {
        // Try snapshots first; fall back to computing from live data
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
            // Compute from live data
            var live = await db.Database.SqlQuery<LiveHealth>($"""
                SELECT
                    CASE WHEN total_emails = 0 THEN 100.0
                         ELSE CAST(completed_emails AS FLOAT) / total_emails * 100 END AS ParserPct,
                    CASE WHEN total_jobs   = 0 THEN 100.0
                         ELSE CAST(completed_jobs   AS FLOAT) / total_jobs   * 100 END AS EnginePct,
                    CASE WHEN total_ocr    = 0 THEN 100.0
                         ELSE CAST(completed_ocr    AS FLOAT) / total_ocr    * 100 END AS OcrPct
                FROM (
                    SELECT
                        COUNT(*)                                             AS total_emails,
                        SUM(CASE WHEN status_id = 3 THEN 1 ELSE 0 END)      AS completed_emails
                    FROM dbo.pobrain_emails
                ) e,
                (
                    SELECT
                        COUNT(*)                                             AS total_jobs,
                        SUM(CASE WHEN status_id = 23 THEN 1 ELSE 0 END)     AS completed_jobs
                    FROM dbo.pobrain_extraction_jobs
                ) j,
                (
                    SELECT
                        COUNT(*)                                             AS total_ocr,
                        SUM(CASE WHEN status_id = 16 THEN 1 ELSE 0 END)     AS completed_ocr
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
        public string  PoNumber    { get; set; } = null!;
        public string  ProductName { get; set; } = null!;
        public decimal Amount      { get; set; }
        public string  StatusName  { get; set; } = null!;
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
