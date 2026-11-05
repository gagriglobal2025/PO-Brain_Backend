using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using POBrain.API.Models.Auth;
using POBrain.API.Services;
using System.Security.Claims;

namespace POBrain.API.Controllers;

[ApiController]
[Route("api/auth")]
public class AuthController(IAuthService authService) : ControllerBase
{
    [HttpPost("login")]
    [AllowAnonymous]
    public async Task<IActionResult> Login([FromBody] LoginRequest request)
    {
        var ip     = HttpContext.Connection.RemoteIpAddress?.ToString();
        var result = await authService.LoginAsync(request, ip);
        return result.Success ? Ok(result) : Unauthorized(result);
    }

    [HttpPost("logout")]
    [Authorize]
    public IActionResult Logout() =>
        Ok(new { success = true, message = "Logged out successfully." });

    [HttpPost("forgot-password")]
    [AllowAnonymous]
    public async Task<IActionResult> ForgotPassword([FromBody] ForgotPasswordRequest request)
    {
        var ip           = HttpContext.Connection.RemoteIpAddress?.ToString();
        var (_, message) = await authService.ForgotPasswordAsync(request.Email, ip);
        return Ok(new { success = true, message });
    }

    [HttpPost("reset-password")]
    [AllowAnonymous]
    public async Task<IActionResult> ResetPassword([FromBody] ResetPasswordRequest request)
    {
        var (success, message) = await authService.ResetPasswordAsync(request);
        return success ? Ok(new { success, message }) : BadRequest(new { success, message });
    }

    [HttpGet("me")]
    [Authorize]
    public IActionResult Me()
    {
        return Ok(new
        {
            id       = User.FindFirst(ClaimTypes.NameIdentifier)?.Value,
            username = User.FindFirst(ClaimTypes.Name)?.Value,
            email    = User.FindFirst(ClaimTypes.Email)?.Value,
            fullName = User.FindFirst("full_name")?.Value,
            role     = User.FindFirst(ClaimTypes.Role)?.Value
        });
    }

    [HttpPut("update/{userId:int}")]
    [Authorize]
    public async Task<IActionResult> UpdateUser(int userId, [FromBody] UpdateUserRequest request)
    {
        var currentUserId = int.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var id) ? id : -1;
        var userRole = User.FindFirst(ClaimTypes.Role)?.Value;

        if (currentUserId != userId && userRole != "admin")
            return Forbid();

        var (success, message) = await authService.UpdateUserAsync(userId, request, userRole);
        return success ? Ok(new { success, message }) : BadRequest(new { success, message });
    }

    [HttpDelete("delete/{userId:int}")]
    [Authorize]
    public async Task<IActionResult> DeleteUser(int userId, [FromBody] DeleteUserRequest request)
    {
        var userRole = User.FindFirst(ClaimTypes.Role)?.Value;

        var (success, message) = await authService.DeleteUserAsync(userId, userRole, request);
        return success ? Ok(new { success, message }) : BadRequest(new { success, message });
    }
}
