using System.ComponentModel.DataAnnotations;

namespace POBrain.API.Models.Auth;

public class LoginRequest
{
    [Required, EmailAddress, MaxLength(320)]
    public string Email { get; set; } = null!;

    [Required, MaxLength(128)]
    public string Password { get; set; } = null!;

    public bool RememberDevice { get; set; }
}
