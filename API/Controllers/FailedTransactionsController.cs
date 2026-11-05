using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using POBrain.API.Models.FailedTransactions;
using POBrain.API.Services;
using Serilog.Context;

namespace POBrain.API.Controllers;

[ApiController]
[Route("api/failed-transactions")]
[Authorize]
public class FailedTransactionsController(IFailedTransactionService service, ILogger<FailedTransactionsController> logger) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> GetAll(
        [FromQuery] string? search,
        [FromQuery] int page     = 1,
        [FromQuery] int pageSize = 50) =>
        Ok(await service.GetAllAsync(search, page, pageSize));

    [HttpPost("filter")]
    public async Task<IActionResult> GetWithFilters([FromBody] FailedTransactionFilterRequest filter) =>
        Ok(await service.GetAllWithFiltersAsync(filter));

    [HttpPost("export")]
    public async Task<IActionResult> ExportCsv([FromBody] FailedTransactionFilterRequest filter)
    {
        var userId = User.FindFirst(System.Security.Claims.ClaimTypes.NameIdentifier)?.Value ?? "unknown";
        using (LogContext.PushProperty("UserId", userId))
        using (LogContext.PushProperty("Action", "ExportFailedTransactions"))
        {
            logger.LogInformation("Processing failed transactions export request: Search={Search}, ErrorCategory={ErrorCategory}, DateRange={FromDate}-{ToDate}, AmountRange={MinAmount}-{MaxAmount}",
                filter.Search ?? "none", filter.ErrorCategory ?? "all", filter.FromDate?.Date, filter.ToDate?.Date, filter.MinAmount, filter.MaxAmount);
            try
            {
                var csv = await service.ExportToCsvAsync(filter);
                var fileName = $"failed-transactions-{AppClock.NowIst:yyyy-MM-dd-HHmmss}.csv";
                logger.LogInformation("Failed transactions exported successfully: {FileName}, Size={SizeKB}KB", fileName, csv.Length / 1024);
                return File(csv, "text/csv", fileName);
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "Error exporting failed transactions: Search={Search}, ErrorCategory={ErrorCategory}", filter.Search, filter.ErrorCategory);
                throw;
            }
        }
    }
}
