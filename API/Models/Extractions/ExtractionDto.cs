namespace POBrain.API.Models.Extractions;

public class ExtractionDto
{
    public string PoNumber { get; init; } = null!;
    public string ProductName { get; init; } = null!;
    public string? CasNumber { get; init; }
    public decimal Quantity { get; init; }
    public decimal Amount { get; init; }
    public string? DeliveryAddress { get; init; }
    public string? BranchLocation { get; init; }
    public string Status { get; init; } = null!;
}
