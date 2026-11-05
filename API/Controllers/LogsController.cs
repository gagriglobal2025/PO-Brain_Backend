using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using POBrain.API.Services;
using Serilog;
using Serilog.Context;

namespace POBrain.API.Controllers;

[ApiController]
[Route("api/logs")]
[Authorize]
public class LogsController(ILogService logService, ILogger<LogsController> logger) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> GetAll(
        [FromQuery] string? level,
        [FromQuery] string? search,
        [FromQuery] int page     = 1,
        [FromQuery] int pageSize = 100) =>
        Ok(await logService.GetAllAsync(level, search, page, pageSize));

    [HttpGet("export")]
    public async Task<IActionResult> ExportCsv(
        [FromQuery] string? level,
        [FromQuery] string? search)
    {
        var userId = User.FindFirst(System.Security.Claims.ClaimTypes.NameIdentifier)?.Value ?? "unknown";
        using (LogContext.PushProperty("UserId", userId))
        using (LogContext.PushProperty("Action", "ExportLogs"))
        {
            logger.LogInformation("Processing logs export request: Level={Level}, Search={Search}", level ?? "ALL", search ?? "none");
            try
            {
                var csv = await logService.ExportToCsvAsync(level, search);
                var fileName = $"processing-logs-{AppClock.NowIst:yyyy-MM-dd-HHmmss}.csv";
                logger.LogInformation("Logs exported successfully: {FileName}, Size={SizeKB}KB", fileName, csv.Length / 1024);
                return File(csv, "text/csv", fileName);
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "Error exporting logs: Level={Level}, Search={Search}", level, search);
                throw;
            }
        }
    }
}
