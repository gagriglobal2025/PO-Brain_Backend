using System.ComponentModel.DataAnnotations;

namespace POBrain.API.Models.Auth;

public class ResetPasswordRequest
{
    [Required, EmailAddress]
    public string Email { get; set; } = null!;

    [Required, StringLength(4, MinimumLength = 4)]
    public string Otp { get; set; } = null!;

    [Required, MinLength(8), MaxLength(128)]
    public string NewPassword { get; set; } = null!;
}
