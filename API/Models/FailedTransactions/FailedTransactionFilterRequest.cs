namespace POBrain.API.Models.FailedTransactions;

public class FailedTransactionFilterRequest
{
    public string? Search { get; set; }
    public string? ErrorCategory { get; set; }
    public DateTime? FromDate { get; set; }
    public DateTime? ToDate { get; set; }
    public decimal? MinAmount { get; set; }
    public decimal? MaxAmount { get; set; }
    public int Page { get; set; } = 1;
    public int PageSize { get; set; } = 50;
}
