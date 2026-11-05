using POBrain.API.Models.Common;
using POBrain.API.Models.Notifications;

namespace POBrain.API.Services;

public interface INotificationService
{
    Task<NotificationCountDto> GetUnreadCountAsync(int userId);
    Task<PagedResponse<NotificationDto>> GetAllAsync(int userId, bool? unreadOnly, int page = 1, int pageSize = 20);
    Task<NotificationDto?> GetByIdAsync(int notificationId, int userId);
    Task<NotificationDto> CreateAsync(CreateNotificationRequest request);
    Task<bool> MarkAsReadAsync(int notificationId, int userId);
    Task<bool> MarkAllAsReadAsync(int userId);
    Task<bool> DeleteAsync(int notificationId, int userId);
    Task BroadcastNotificationAsync(int userId, NotificationDto notification);
}
