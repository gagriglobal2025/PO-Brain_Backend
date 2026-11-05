using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using POBrain.API.Services;

namespace POBrain.API.Controllers;

[ApiController]
[Route("api/dashboard")]
[Authorize]
public class DashboardController(IDashboardService dashboardService) : ControllerBase
{
    [HttpGet("stats")]
    public async Task<IActionResult> GetStats() =>
        Ok(await dashboardService.GetStatsAsync());

    [HttpGet("recent-extractions")]
    public async Task<IActionResult> GetRecentExtractions([FromQuery] int count = 10) =>
        Ok(await dashboardService.GetRecentExtractionsAsync(Math.Clamp(count, 1, 50)));

    [HttpGet("health")]
    public async Task<IActionResult> GetHealth() =>
        Ok(await dashboardService.GetHealthStatusAsync());
}
