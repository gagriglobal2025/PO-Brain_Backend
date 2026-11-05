using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using System.Security.Claims;

namespace POBrain.API.Hubs;

[Authorize]
public class LogStreamHub : Hub
{
    public override async Task OnConnectedAsync()
    {
        // Subscribe to global log stream
        await Groups.AddToGroupAsync(Context.ConnectionId, "log-subscribers");

        // Subscribe to user-specific notification group
        var userId = Context.User?.FindFirst(ClaimTypes.NameIdentifier)?.Value;
        if (!string.IsNullOrEmpty(userId))
        {
            await Groups.AddToGroupAsync(Context.ConnectionId, $"user-{userId}");
        }

        await base.OnConnectedAsync();
    }

    public override async Task OnDisconnectedAsync(Exception? exception)
    {
        await Groups.RemoveFromGroupAsync(Context.ConnectionId, "log-subscribers");

        var userId = Context.User?.FindFirst(ClaimTypes.NameIdentifier)?.Value;
        if (!string.IsNullOrEmpty(userId))
        {
            await Groups.RemoveFromGroupAsync(Context.ConnectionId, $"user-{userId}");
        }

        await base.OnDisconnectedAsync(exception);
    }
}

