using System.ComponentModel.DataAnnotations;

namespace POBrain.API.Models.Auth;

public class ForgotPasswordRequest
{
    [Required, EmailAddress, MaxLength(320)]
    public string Email { get; set; } = null!;
}
