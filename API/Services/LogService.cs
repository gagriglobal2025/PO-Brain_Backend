using Microsoft.EntityFrameworkCore;
using POBrain.API.Data;
using POBrain.API.Models.Common;
using POBrain.API.Models.Logs;
using System.Text;

namespace POBrain.API.Services;

public class LogService(PoBrainDbContext db) : ILogService
{
    public async Task<PagedResponse<LogEntryDto>> GetAllAsync(string? level, string? search, int page, int pageSize)
    {
        page     = Math.Max(1, page);
        pageSize = Math.Clamp(pageSize, 1, 500);
        int offset = (page - 1) * pageSize;

        var pattern      = string.IsNullOrWhiteSpace(search) ? "%" : $"%{search.Trim()}%";
        var levelPattern = string.IsNullOrWhiteSpace(level) || level.Equals("ALL", StringComparison.OrdinalIgnoreCase)
                           ? "%" : level.Trim().ToUpper();

        var countRows = await db.Database.SqlQuery<CountRow>($"""
            SELECT COUNT(*) AS Total
            FROM dbo.pobrain_processing_logs pl
            JOIN dbo.pobrain_lkp_log_level ll ON pl.log_level_id = ll.log_level_id
            WHERE ll.level_code LIKE {levelPattern}
              AND (pl.sender_email  LIKE {pattern}
                OR pl.email_subject LIKE {pattern})
            """).ToListAsync();

        int total = countRows.FirstOrDefault()?.Total ?? 0;

        var rows = await db.Database.SqlQuery<LogRow>($"""
            SELECT
                FORMAT(pl.logged_at, 'yyyy-MM-dd HH:mm:ss')  AS Timestamp,
                ll.level_code                                 AS Level,
                pl.sender_email                               AS Sender,
                pl.email_subject                              AS Subject,
                pl.message                                    AS Message
            FROM dbo.pobrain_processing_logs pl
            JOIN dbo.pobrain_lkp_log_level ll ON pl.log_level_id = ll.log_level_id
            WHERE ll.level_code LIKE {levelPattern}
              AND (pl.sender_email  LIKE {pattern}
                OR pl.email_subject LIKE {pattern})
            ORDER BY pl.logged_at DESC
            OFFSET {offset} ROWS FETCH NEXT {pageSize} ROWS ONLY
            """).ToListAsync();

        var data = rows.Select(r => new LogEntryDto
        {
            Timestamp = r.Timestamp,
            Level     = r.Level,
            Sender    = r.Sender,
            Subject   = r.Subject,
            Message   = r.Message
        });

        return new PagedResponse<LogEntryDto>
        {
            Data       = data,
            TotalCount = total,
            Page       = page,
            PageSize   = pageSize
        };
    }

    public async Task<byte[]> ExportToCsvAsync(string? level, string? search)
    {
        var pattern      = string.IsNullOrWhiteSpace(search) ? "%" : $"%{search.Trim()}%";
        var levelPattern = string.IsNullOrWhiteSpace(level) || level.Equals("ALL", StringComparison.OrdinalIgnoreCase)
                           ? "%" : level.Trim().ToUpper();

        var rows = await db.Database.SqlQuery<LogRow>($"""
            SELECT
                FORMAT(pl.logged_at, 'yyyy-MM-dd HH:mm:ss')  AS Timestamp,
                ll.level_code                                 AS Level,
                pl.sender_email                               AS Sender,
                pl.email_subject                              AS Subject,
                pl.message                                    AS Message
            FROM dbo.pobrain_processing_logs pl
            JOIN dbo.pobrain_lkp_log_level ll ON pl.log_level_id = ll.log_level_id
            WHERE ll.level_code LIKE {levelPattern}
              AND (pl.sender_email  LIKE {pattern}
                OR pl.email_subject LIKE {pattern})
            ORDER BY pl.logged_at DESC
            """).ToListAsync();

        var csv = new StringBuilder();
        csv.AppendLine("Timestamp,Level,Sender,Subject,Message");

        foreach (var row in rows)
        {
            csv.AppendLine($"{EscapeCsv(row.Timestamp)},{EscapeCsv(row.Level)},{EscapeCsv(row.Sender)},{EscapeCsv(row.Subject)},{EscapeCsv(row.Message)}");
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

    private sealed class CountRow { public int Total { get; set; } }

    private sealed class LogRow
    {
        public string  Timestamp { get; set; } = null!;
        public string  Level     { get; set; } = null!;
        public string? Sender    { get; set; }
        public string? Subject   { get; set; }
        public string  Message   { get; set; } = null!;
    }
}
