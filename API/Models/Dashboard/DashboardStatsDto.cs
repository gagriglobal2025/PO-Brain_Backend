namespace POBrain.API.Models.Dashboard;

public class DashboardStatsDto
{
    public int TotalEmails { get; init; }
    public int Processed { get; init; }
    public int Failed { get; init; }
    public double SuccessRate { get; init; }
    public string CurrentStatus { get; init; } = "Active";
}
