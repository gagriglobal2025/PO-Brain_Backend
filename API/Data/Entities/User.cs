using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace POBrain.API.Data.Entities;

[Table("pobrain_users", Schema = "dbo")]
public class User
{
    [Key]
    [Column("user_id")]
    public int UserId { get; set; }

    [Column("username")]
    [MaxLength(100)]
    public string Username { get; set; } = null!;

    [Column("email")]
    [MaxLength(320)]
    public string Email { get; set; } = null!;

    [Column("password_hash")]
    [MaxLength(255)]
    public string PasswordHash { get; set; } = null!;

    [Column("full_name")]
    [MaxLength(200)]
    public string? FullName { get; set; }

    [Column("role")]
    [MaxLength(30)]
    public string Role { get; set; } = "viewer";

    [Column("is_active")]
    public bool IsActive { get; set; } = true;

    [Column("last_login_at")]
    public DateTime? LastLoginAt { get; set; }

    [Column("failed_login_attempts")]
    public int FailedLoginAttempts { get; set; }

    [Column("locked_until")]
    public DateTime? LockedUntil { get; set; }

    [Column("created_at")]
    public DateTime CreatedAt { get; set; }

    [Column("updated_at")]
    public DateTime? UpdatedAt { get; set; }

    [Column("created_by")]
    [MaxLength(100)]
    public string CreatedBy { get; set; } = "SYSTEM";

    public ICollection<PasswordReset> PasswordResets { get; set; } = [];
    public ICollection<Notification> Notifications { get; set; } = [];
}
