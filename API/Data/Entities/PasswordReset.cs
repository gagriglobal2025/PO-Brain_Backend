using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace POBrain.API.Data.Entities;

[Table("pobrain_password_resets", Schema = "dbo")]
public class PasswordReset
{
    [Key]
    [Column("reset_id")]
    public int ResetId { get; set; }

    [Column("user_id")]
    public int UserId { get; set; }

    [Column("otp_code")]
    [MaxLength(6)]
    public string OtpCode { get; set; } = null!;

    [Column("otp_expires_at")]
    public DateTime OtpExpiresAt { get; set; }

    [Column("max_attempts")]
    public int MaxAttempts { get; set; } = 3;

    [Column("attempt_count")]
    public int AttemptCount { get; set; } = 0;

    [Column("is_used")]
    public bool IsUsed { get; set; }

    [Column("used_at")]
    public DateTime? UsedAt { get; set; }

    [Column("requested_ip")]
    [MaxLength(45)]
    public string? RequestedIp { get; set; }

    [Column("created_at")]
    public DateTime CreatedAt { get; set; }

    [ForeignKey(nameof(UserId))]
    public User User { get; set; } = null!;
}
