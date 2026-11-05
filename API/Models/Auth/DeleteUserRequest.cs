using System.ComponentModel.DataAnnotations;

namespace POBrain.API.Models.Auth;

public class DeleteUserRequest
{
    [Required]
    public string Password { get; set; } = null!;
}
