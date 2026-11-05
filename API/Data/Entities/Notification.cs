namespace POBrain.API.Data.Entities;

public class Notification
{
    public int NotificationId { get; set; }
    public int UserId { get; set; }
    public string Type { get; set; } = null!;
    public string Title { get; set; } = null!;
    public string Message { get; set; } = null!;
    public bool IsRead { get; set; }
    public string? RelatedPoNumber { get; set; }
    public int? RelatedErrorId { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime? ReadAt { get; set; }

    public virtual User User { get; set; } = null!;
}
