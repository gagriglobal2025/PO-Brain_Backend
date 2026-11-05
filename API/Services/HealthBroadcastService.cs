using Microsoft.AspNetCore.SignalR;
using Microsoft.EntityFrameworkCore;
using POBrain.API.Data;
using POBrain.API.Hubs;
using POBrain.API.Models.Dashboard;

namespace POBrain.API.Services;

public class HealthBroadcastService(
    IServiceScopeFactory serviceScopeFactory,
    IHubContext<HealthStreamHub> hubContext,
    ILogger<HealthBroadcastService> logger) : BackgroundService
{
    private readonly TimeSpan _interval = TimeSpan.FromSeconds(30);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var scope = serviceScopeFactory.CreateScope();
                var db = scope.ServiceProvider.GetRequiredService<PoBrainDbContext>();

                var health = await CalculateHealthAsync(db);

                await hubContext.Clients.Group("health-subscribers")
                    .SendAsync("health-update", health, cancellationToken: stoppingToken);

                logger.LogInformation("Health update broadcasted: Engine={Engine}%, Parser={Parser}%, OCR={OCR}%",
                    health.ExtractionEngine, health.EmailParser, health.OcrPipeline);
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "Error broadcasting health update");
            }

            await Task.Delay(_interval, stoppingToken);
        }
    }

    private async Task<HealthStatusDto> CalculateHealthAsync(PoBrainDbContext db)
    {
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
        var ocr = Get("OCRPipeline");

        if (engine < 0 || parser < 0 || ocr < 0)
        {
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
            ocr = l.OcrPct;
        }

        return new HealthStatusDto
        {
            ExtractionEngine = Math.Round(engine, 1),
            EmailParser = Math.Round(parser, 1),
            OcrPipeline = Math.Round(ocr, 1)
        };
    }

    private sealed class SnapRow
    {
        public string ComponentName { get; set; } = null!;
        public decimal HealthPct { get; set; }
    }

    private sealed class LiveHealth
    {
        public double ParserPct { get; set; }
        public double EnginePct { get; set; }
        public double OcrPct { get; set; }
    }
}
