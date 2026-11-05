namespace POBrain.API.Models.Notifications;

public class NotificationDto
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
}

public class CreateNotificationRequest
{
    public int UserId { get; set; }
    public string Type { get; set; } = null!;
    public string Title { get; set; } = null!;
    public string Message { get; set; } = null!;
    public string? RelatedPoNumber { get; set; }
    public int? RelatedErrorId { get; set; }
}

public class NotificationCountDto
{
    public int UnreadCount { get; set; }
    public int TotalCount { get; set; }
}
