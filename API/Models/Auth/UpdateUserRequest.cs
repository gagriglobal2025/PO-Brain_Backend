using System.ComponentModel.DataAnnotations;

namespace POBrain.API.Models.Auth;

public class UpdateUserRequest
{
    [MaxLength(200)]
    public string? FullName { get; set; }

    [EmailAddress]
    [MaxLength(320)]
    public string? Email { get; set; }

    public string? Role { get; set; }

    public bool? IsActive { get; set; }
}
