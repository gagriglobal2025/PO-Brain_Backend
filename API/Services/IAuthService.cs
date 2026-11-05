using POBrain.API.Models.Auth;

namespace POBrain.API.Services;

public interface IAuthService
{
    Task<LoginResponse> LoginAsync(LoginRequest request, string? ipAddress);
    Task<(bool Success, string Message)> ForgotPasswordAsync(string email, string? ipAddress);
    Task<(bool Success, string Message)> ResetPasswordAsync(ResetPasswordRequest request);
    Task<(bool Success, string Message)> UpdateUserAsync(int userId, UpdateUserRequest request, string? userRole);
    Task<(bool Success, string Message)> DeleteUserAsync(int userId, string? userRole, DeleteUserRequest request);
}
