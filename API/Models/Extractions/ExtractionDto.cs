namespace POBrain.API.Models.Extractions;

public class ExtractionLineItemDto
{
    public long LineItemId { get; init; }
    public int LineNumber { get; init; }
    public string ProductName { get; init; } = string.Empty;
    public string? CasNumber { get; init; }
    public string? CatNumber { get; init; }
    public string? HsnCode { get; init; }
    public decimal Quantity { get; init; }
    public string? UnitOfMeasure { get; init; }
    public decimal UnitPrice { get; init; }
    public decimal Amount { get; init; }
}

public class ExtractionDetailsDto
{
    public string PoNumber { get; init; } = string.Empty;
    public string? PoDate { get; init; }
    public string? VendorName { get; init; }
    public string? VendorEmail { get; init; }
    public List<ExtractionLineItemDto> LineItems { get; init; } = [];
}

public class ExtractionDto
{
    public long? PoId { get; init; }
    public string PoNumber { get; init; } = null!;
    public string? PoDate { get; init; }
    public string? VendorName { get; init; }
    public string? VendorEmail { get; init; }
    public string ProductName { get; init; } = string.Empty;
    public string? CasNumber { get; init; }
    public decimal Quantity { get; init; }
    public decimal Amount { get; init; }
    public decimal? SubTotalAmount { get; init; }
    public decimal? TotalTaxAmount { get; init; }
    public decimal? TotalAmount { get; init; }
    public string? DeliveryAddress { get; init; }
    public string? BranchLocation { get; init; }
    public string Status { get; init; } = null!;
    public bool IsErpInserted { get; init; }
    public long? ErpOrderId { get; init; }
    public ExtractionDetailsDto? Details { get; init; }
}
