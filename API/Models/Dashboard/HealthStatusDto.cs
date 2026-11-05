namespace POBrain.API.Models.Dashboard;

public class HealthStatusDto
{
    public double ExtractionEngine { get; init; }
    public double EmailParser { get; init; }
    public double OcrPipeline { get; init; }
}
