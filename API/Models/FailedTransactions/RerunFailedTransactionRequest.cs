namespace POBrain.API.Models.FailedTransactions;

public class RerunFailedTransactionRequest
{
    public long? FailedId { get; set; }
    public string? PoNumber { get; set; }
    public string? EmailFrom { get; set; }
}

