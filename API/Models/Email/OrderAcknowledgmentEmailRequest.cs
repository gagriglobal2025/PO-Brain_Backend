namespace POBrain.API.Models.Email;

public sealed class OrderAcknowledgmentEmailRequest
{
    public long OrderId { get; set; }
    public string? PoNumber { get; set; }
    public string? RecipientEmail { get; set; }
    public List<string>? CcEmails { get; set; }
    
    // Optional override details (if not provided, loaded from DB)
    public CustomerDetailsDto? Customer { get; set; }
    public List<OrderItemEmailDto>? Items { get; set; }
    public string? Comments { get; set; }
    public string? IpAddress { get; set; }
    public string? AcceptanceDate { get; set; }
    public string? AcceptanceStatus { get; set; }
    
    // Optional attachment
    public string? AttachmentBase64 { get; set; }
    public string? AttachmentFileName { get; set; }
}

public sealed class CustomerDetailsDto
{
    public string? CompanyName { get; set; }
    public string? CustomerName { get; set; }
    public string? Email { get; set; }
    public string? ContactNo { get; set; }
    public string? City { get; set; }
    public string? GstNo { get; set; }
    public string? Comments { get; set; }
}

public sealed class OrderItemEmailDto
{
    public long? OrderNo { get; set; }
    public string? ItemCode { get; set; }
    public string? HsnCode { get; set; }
    public decimal? GstRate { get; set; }
    public string? CasNo { get; set; }
    public string? ChemicalName { get; set; }
    public string? PackSize { get; set; }
    public decimal Quantity { get; set; }
    public decimal UnitPrice { get; set; }
    public decimal Price { get; set; }
    public decimal DiscountPercent { get; set; }
    public decimal DiscountPrice { get; set; }
    public decimal GstPrice { get; set; }
    public decimal TotalPrice { get; set; }
}
