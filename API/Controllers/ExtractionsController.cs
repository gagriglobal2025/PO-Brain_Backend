using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using POBrain.API.Models.Extractions;
using POBrain.API.Services;
using Serilog.Context;

namespace POBrain.API.Controllers;

[ApiController]
[Route("api/extractions")]
[Authorize]
public class ExtractionsController(IExtractionService extractionService, ILogger<ExtractionsController> logger) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> GetAll(
        [FromQuery] string? search,
        [FromQuery] int page     = 1,
        [FromQuery] int pageSize = 50) =>
        Ok(await extractionService.GetAllAsync(search, page, pageSize));

    [HttpPost("filter")]
    public async Task<IActionResult> GetWithFilters([FromBody] ExtractionFilterRequest filter) =>
        Ok(await extractionService.GetAllWithFiltersAsync(filter));

    [HttpPost("export")]
    public async Task<IActionResult> ExportCsv([FromBody] ExtractionFilterRequest filter)
    {
        var userId = User.FindFirst(System.Security.Claims.ClaimTypes.NameIdentifier)?.Value ?? "unknown";
        using (LogContext.PushProperty("UserId", userId))
        using (LogContext.PushProperty("Action", "ExportExtractions"))
        {
            logger.LogInformation("Processing extractions export request: Search={Search}, Status={Status}, DateRange={FromDate}-{ToDate}, AmountRange={MinAmount}-{MaxAmount}",
                filter.Search ?? "none", filter.Status ?? "all", filter.FromDate?.Date, filter.ToDate?.Date, filter.MinAmount, filter.MaxAmount);
            try
            {
                var csv = await extractionService.ExportToCsvAsync(filter);
                var fileName = $"extractions-{AppClock.NowIst:yyyy-MM-dd-HHmmss}.csv";
                logger.LogInformation("Extractions exported successfully: {FileName}, Size={SizeKB}KB", fileName, csv.Length / 1024);
                return File(csv, "text/csv", fileName);
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "Error exporting extractions: Search={Search}, Status={Status}", filter.Search, filter.Status);
                throw;
            }
        }
    }
}
