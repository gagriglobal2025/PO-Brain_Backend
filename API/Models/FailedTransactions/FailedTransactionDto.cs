namespace POBrain.API.Models.FailedTransactions;

public class FailedTransactionDto
{
    public string? PoNumber { get; init; }
    public string? PoDate { get; init; }
    public string? ProductName { get; init; }
    public decimal? Quantity { get; init; }
    public decimal? Amount { get; init; }
    public string? EmailFrom { get; init; }
    public string? EmailDate { get; init; }
    public string ErrorReason { get; init; } = null!;
    public string FailedAt { get; init; } = null!;
}
