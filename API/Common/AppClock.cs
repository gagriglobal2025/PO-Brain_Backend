namespace POBrain.API.Common;

/// <summary>
/// Central clock for the API. All persisted timestamps use Indian Standard Time
/// (UTC+5:30, no DST) so they match the Python extractor and the database defaults.
/// </summary>
public static class AppClock
{
    /// <summary>Fixed IST offset (India has no daylight saving).</summary>
    public static readonly TimeSpan IstOffset = TimeSpan.FromMinutes(330);

    /// <summary>Current time in Indian Standard Time.</summary>
    public static DateTime NowIst => DateTime.UtcNow.Add(IstOffset);
}
