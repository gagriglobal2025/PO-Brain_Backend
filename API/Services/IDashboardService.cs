using POBrain.API.Models.Dashboard;

namespace POBrain.API.Services;

public interface IDashboardService
{
    Task<DashboardStatsDto> GetStatsAsync();
    Task<IEnumerable<RecentExtractionDto>> GetRecentExtractionsAsync(int count = 10);
    Task<HealthStatusDto> GetHealthStatusAsync();
}
