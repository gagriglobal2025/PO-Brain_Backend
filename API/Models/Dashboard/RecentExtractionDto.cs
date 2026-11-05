namespace POBrain.API.Models.Dashboard;

public class RecentExtractionDto
{
    public string Id { get; init; } = null!;
    public string Name { get; init; } = null!;
    public decimal Amount { get; init; }
    public string Status { get; init; } = null!;
}
