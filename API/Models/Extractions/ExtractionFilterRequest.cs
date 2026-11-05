namespace POBrain.API.Models.Extractions;

public class ExtractionFilterRequest
{
    public string? Search { get; set; }
    public string? Status { get; set; }
    public DateTime? FromDate { get; set; }
    public DateTime? ToDate { get; set; }
    public decimal? MinAmount { get; set; }
    public decimal? MaxAmount { get; set; }
    public string? BranchLocation { get; set; }
    public int Page { get; set; } = 1;
    public int PageSize { get; set; } = 50;
}
