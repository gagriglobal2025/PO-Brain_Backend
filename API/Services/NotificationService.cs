using Microsoft.AspNetCore.SignalR;
using Microsoft.EntityFrameworkCore;
using POBrain.API.Data;
using POBrain.API.Data.Entities;
using POBrain.API.Hubs;
using POBrain.API.Models.Common;
using POBrain.API.Models.Notifications;

namespace POBrain.API.Services;

public class NotificationService(PoBrainDbContext db, IHubContext<LogStreamHub> hubContext) : INotificationService
{
    public async Task<NotificationCountDto> GetUnreadCountAsync(int userId)
    {
        var unreadCount = await db.Notifications
            .Where(n => n.UserId == userId && !n.IsRead)
            .CountAsync();

        var totalCount = await db.Notifications
            .Where(n => n.UserId == userId)
            .CountAsync();

        return new NotificationCountDto
        {
            UnreadCount = unreadCount,
            TotalCount = totalCount
        };
    }

    public async Task<PagedResponse<NotificationDto>> GetAllAsync(int userId, bool? unreadOnly, int page = 1, int pageSize = 20)
    {
        page = Math.Max(1, page);
        pageSize = Math.Clamp(pageSize, 1, 100);
        int offset = (page - 1) * pageSize;

        var query = db.Notifications.Where(n => n.UserId == userId);

        if (unreadOnly.HasValue && unreadOnly.Value)
            query = query.Where(n => !n.IsRead);

        var total = await query.CountAsync();

        var notifications = await query
            .OrderByDescending(n => n.CreatedAt)
            .Skip(offset)
            .Take(pageSize)
            .Select(n => new NotificationDto
            {
                NotificationId = n.NotificationId,
                UserId = n.UserId,
                Type = n.Type,
                Title = n.Title,
                Message = n.Message,
                IsRead = n.IsRead,
                RelatedPoNumber = n.RelatedPoNumber,
                RelatedErrorId = n.RelatedErrorId,
                CreatedAt = n.CreatedAt,
                ReadAt = n.ReadAt
            })
            .ToListAsync();

        return new PagedResponse<NotificationDto>
        {
            Data = notifications,
            TotalCount = total,
            Page = page,
            PageSize = pageSize
        };
    }

    public async Task<NotificationDto?> GetByIdAsync(int notificationId, int userId)
    {
        var notification = await db.Notifications
            .Where(n => n.NotificationId == notificationId && n.UserId == userId)
            .FirstOrDefaultAsync();

        if (notification == null)
            return null;

        return new NotificationDto
        {
            NotificationId = notification.NotificationId,
            UserId = notification.UserId,
            Type = notification.Type,
            Title = notification.Title,
            Message = notification.Message,
            IsRead = notification.IsRead,
            RelatedPoNumber = notification.RelatedPoNumber,
            RelatedErrorId = notification.RelatedErrorId,
            CreatedAt = notification.CreatedAt,
            ReadAt = notification.ReadAt
        };
    }

    public async Task<NotificationDto> CreateAsync(CreateNotificationRequest request)
    {
        var notification = new Notification
        {
            UserId = request.UserId,
            Type = request.Type,
            Title = request.Title,
            Message = request.Message,
            RelatedPoNumber = request.RelatedPoNumber,
            RelatedErrorId = request.RelatedErrorId,
            IsRead = false,
            CreatedAt = AppClock.NowIst
        };

        db.Notifications.Add(notification);
        await db.SaveChangesAsync();

        var dto = new NotificationDto
        {
            NotificationId = notification.NotificationId,
            UserId = notification.UserId,
            Type = notification.Type,
            Title = notification.Title,
            Message = notification.Message,
            IsRead = notification.IsRead,
            RelatedPoNumber = notification.RelatedPoNumber,
            RelatedErrorId = notification.RelatedErrorId,
            CreatedAt = notification.CreatedAt,
            ReadAt = notification.ReadAt
        };

        await BroadcastNotificationAsync(request.UserId, dto);
        return dto;
    }

    public async Task<bool> MarkAsReadAsync(int notificationId, int userId)
    {
        var notification = await db.Notifications
            .Where(n => n.NotificationId == notificationId && n.UserId == userId)
            .FirstOrDefaultAsync();

        if (notification == null)
            return false;

        notification.IsRead = true;
        notification.ReadAt = AppClock.NowIst;
        await db.SaveChangesAsync();
        return true;
    }

    public async Task<bool> MarkAllAsReadAsync(int userId)
    {
        var notifications = await db.Notifications
            .Where(n => n.UserId == userId && !n.IsRead)
            .ToListAsync();

        if (!notifications.Any())
            return false;

        foreach (var notif in notifications)
        {
            notif.IsRead = true;
            notif.ReadAt = AppClock.NowIst;
        }

        await db.SaveChangesAsync();
        return true;
    }

    public async Task<bool> DeleteAsync(int notificationId, int userId)
    {
        var notification = await db.Notifications
            .Where(n => n.NotificationId == notificationId && n.UserId == userId)
            .FirstOrDefaultAsync();

        if (notification == null)
            return false;

        db.Notifications.Remove(notification);
        await db.SaveChangesAsync();
        return true;
    }

    public async Task BroadcastNotificationAsync(int userId, NotificationDto notification)
    {
        try
        {
            await hubContext.Clients.Group($"user-{userId}")
                .SendAsync("notification", notification);
        }
        catch
        {
            // SignalR not connected or no clients in group
        }
    }
}
