namespace POBrain.API.Models.FailedTransactions;

public class RerunFailedTransactionResponse
{
    public bool Success { get; set; }
    public string Message { get; set; } = string.Empty;
    public long? OrderId { get; set; }
}

