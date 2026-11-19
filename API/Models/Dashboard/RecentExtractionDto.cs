namespace POBrain.API.Models.Dashboard;

public class RecentExtractionDto
{
    public string Id { get; init; } = null!;
    public string PoNumber { get; init; } = null!;
    public string Name { get; init; } = null!;
    public string VendorName { get; init; } = null!;
    public decimal Amount { get; init; }
    public decimal TotalAmount { get; init; }
    public string Status { get; init; } = null!;
    public string? PoDate { get; init; }
    public string? CreatedAt { get; init; }
}
