namespace POBrain.API.Models.Auth;

public class LoginResponse
{
    public bool Success { get; init; }
    public string Message { get; init; } = null!;
    public string? Token { get; init; }
    public UserInfo? User { get; init; }
}

public class UserInfo
{
    public int Id { get; init; }
    public string Username { get; init; } = null!;
    public string Email { get; init; } = null!;
    public string FullName { get; init; } = null!;
    public string Role { get; init; } = null!;
}
