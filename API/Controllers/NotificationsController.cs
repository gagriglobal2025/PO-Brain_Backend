using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using POBrain.API.Models.Notifications;
using POBrain.API.Services;
using System.Security.Claims;

namespace POBrain.API.Controllers;

[ApiController]
[Route("api/notifications")]
[Authorize]
public class NotificationsController(INotificationService notificationService) : ControllerBase
{
    private int GetUserId()
    {
        var userIdClaim = User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
        return int.TryParse(userIdClaim, out var userId) ? userId : 0;
    }

    [HttpGet("count")]
    public async Task<IActionResult> GetUnreadCount()
    {
        var userId = GetUserId();
        if (userId == 0)
            return Unauthorized();

        var result = await notificationService.GetUnreadCountAsync(userId);
        return Ok(result);
    }

    [HttpGet]
    public async Task<IActionResult> GetAll(
        [FromQuery] bool? unreadOnly,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 20)
    {
        var userId = GetUserId();
        if (userId == 0)
            return Unauthorized();

        var result = await notificationService.GetAllAsync(userId, unreadOnly, page, pageSize);
        return Ok(result);
    }

    [HttpGet("{notificationId:int}")]
    public async Task<IActionResult> GetById(int notificationId)
    {
        var userId = GetUserId();
        if (userId == 0)
            return Unauthorized();

        var notification = await notificationService.GetByIdAsync(notificationId, userId);
        if (notification == null)
            return NotFound();

        return Ok(notification);
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] CreateNotificationRequest request)
    {
        var currentUserId = GetUserId();
        if (currentUserId == 0)
            return Unauthorized();

        var currentUserRole = User.FindFirst(ClaimTypes.Role)?.Value;
        if (currentUserRole != "admin")
            return Forbid("Only admins can create notifications");

        var result = await notificationService.CreateAsync(request);
        return CreatedAtAction(nameof(GetById), new { notificationId = result.NotificationId }, result);
    }

    [HttpPut("{notificationId:int}/read")]
    public async Task<IActionResult> MarkAsRead(int notificationId)
    {
        var userId = GetUserId();
        if (userId == 0)
            return Unauthorized();

        var success = await notificationService.MarkAsReadAsync(notificationId, userId);
        if (!success)
            return NotFound();

        return Ok(new { success = true, message = "Notification marked as read" });
    }

    [HttpPut("read-all")]
    public async Task<IActionResult> MarkAllAsRead()
    {
        var userId = GetUserId();
        if (userId == 0)
            return Unauthorized();

        var success = await notificationService.MarkAllAsReadAsync(userId);
        return Ok(new { success, message = success ? "All notifications marked as read" : "No unread notifications" });
    }

    [HttpDelete("{notificationId:int}")]
    public async Task<IActionResult> Delete(int notificationId)
    {
        var userId = GetUserId();
        if (userId == 0)
            return Unauthorized();

        var success = await notificationService.DeleteAsync(notificationId, userId);
        if (!success)
            return NotFound();

        return Ok(new { success = true, message = "Notification deleted" });
    }
}
