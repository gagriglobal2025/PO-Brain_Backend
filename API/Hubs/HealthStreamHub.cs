using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;

namespace POBrain.API.Hubs;

[Authorize]
public class HealthStreamHub : Hub
{
    public override async Task OnConnectedAsync()
    {
        await Groups.AddToGroupAsync(Context.ConnectionId, "health-subscribers");
        await base.OnConnectedAsync();
    }

    public override async Task OnDisconnectedAsync(Exception? exception)
    {
        await Groups.RemoveFromGroupAsync(Context.ConnectionId, "health-subscribers");
        await base.OnDisconnectedAsync(exception);
    }
}
