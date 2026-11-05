using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using POBrain.API.Data;
using POBrain.API.Data.Entities;
using POBrain.API.Models.Auth;
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;

namespace POBrain.API.Services;

public class AuthService(PoBrainDbContext db, IConfiguration config, IEmailService emailService, ILogger<AuthService> log) : IAuthService
{
    public async Task<LoginResponse> LoginAsync(LoginRequest request, string? ipAddress)
    {
        var user = await db.Users.FirstOrDefaultAsync(u => u.Email == request.Email);

        if (user is null || !user.IsActive)
            return Fail("Invalid email or password.");

        if (user.LockedUntil.HasValue && user.LockedUntil > AppClock.NowIst)
            return Fail($"Account locked until {user.LockedUntil:HH:mm} IST. Try again later.");

        bool valid;
        try { valid = BCrypt.Net.BCrypt.Verify(request.Password, user.PasswordHash); }
        catch { valid = false; }

        if (!valid)
        {
            user.FailedLoginAttempts++;
            if (user.FailedLoginAttempts >= 5)
                user.LockedUntil = AppClock.NowIst.AddMinutes(15);
            user.UpdatedAt = AppClock.NowIst;
            await db.SaveChangesAsync();
            return Fail("Invalid email or password.");
        }

        user.FailedLoginAttempts = 0;
        user.LockedUntil = null;
        user.LastLoginAt = AppClock.NowIst;
        user.UpdatedAt = AppClock.NowIst;
        await db.SaveChangesAsync();

        log.LogInformation("User {Username} logged in from {IP}", user.Username, ipAddress);

        return new LoginResponse
        {
            Success = true,
            Message = "Login successful.",
            Token   = GenerateToken(user),
            User    = new UserInfo
            {
                Id       = user.UserId,
                Username = user.Username,
                Email    = user.Email,
                FullName = user.FullName ?? user.Username,
                Role     = user.Role
            }
        };
    }

    public async Task<(bool Success, string Message)> ForgotPasswordAsync(string email, string? ipAddress)
    {
        var user = await db.Users.FirstOrDefaultAsync(u => u.Email == email);
        if (user is null || !user.IsActive)
            return (true, "If that email exists, a password reset OTP has been sent.");

        var otp = Random.Shared.Next(1000, 9999).ToString();
        var otpExpiryMinutes = int.TryParse(config["SmtpSettings:OtpExpiryMinutes"], out var m) ? m : 15;

        var existingReset = await db.PasswordResets.FirstOrDefaultAsync(r => r.UserId == user.UserId);
        if (existingReset != null)
            db.PasswordResets.Remove(existingReset);

        db.PasswordResets.Add(new PasswordReset
        {
            UserId       = user.UserId,
            OtpCode      = otp,
            OtpExpiresAt = AppClock.NowIst.AddMinutes(otpExpiryMinutes),
            MaxAttempts  = 3,
            AttemptCount = 0,
            RequestedIp  = ipAddress,
            CreatedAt    = AppClock.NowIst
        });
        await db.SaveChangesAsync();

        var (emailSuccess, emailMsg) = await emailService.SendOtpAsync(email, otp, user.Username);

        log.LogInformation("Password reset OTP requested for {Email} from {IP} — Email sent: {Success}", email, ipAddress, emailSuccess);

        if (!emailSuccess)
            log.LogWarning("Failed to send OTP email to {Email}: {Message}", email, emailMsg);

        return (true, "If that email exists, a password reset OTP has been sent.");
    }

    public async Task<(bool Success, string Message)> ResetPasswordAsync(ResetPasswordRequest request)
    {
        var user = await db.Users.FirstOrDefaultAsync(u => u.Email == request.Email);
        if (user is null)
            return (false, "Invalid email address.");

        var reset = await db.PasswordResets
            .FirstOrDefaultAsync(r => r.UserId == user.UserId && !r.IsUsed && r.OtpExpiresAt > AppClock.NowIst);

        if (reset is null)
            return (false, "Invalid or expired OTP. Please request a new password reset.");

        if (reset.OtpCode != request.Otp)
        {
            reset.AttemptCount++;
            if (reset.AttemptCount >= reset.MaxAttempts)
            {
                reset.IsUsed = true;
                reset.UsedAt = AppClock.NowIst;
            }
            await db.SaveChangesAsync();
            var remaining = reset.MaxAttempts - reset.AttemptCount;
            return (false, remaining > 0
                ? $"Invalid OTP. {remaining} attempt(s) remaining."
                : "Maximum OTP attempts exceeded. Please request a new password reset.");
        }

        user.PasswordHash = BCrypt.Net.BCrypt.HashPassword(request.NewPassword, 12);
        user.UpdatedAt = AppClock.NowIst;
        user.FailedLoginAttempts = 0;
        user.LockedUntil = null;

        reset.IsUsed = true;
        reset.UsedAt = AppClock.NowIst;

        await db.SaveChangesAsync();

        log.LogInformation("Password reset completed for user {UserId}", user.UserId);
        return (true, "Password updated successfully.");
    }

    public async Task<(bool Success, string Message)> UpdateUserAsync(int userId, UpdateUserRequest request, string? userRole)
    {
        var user = await db.Users.FindAsync(userId);
        if (user is null)
            return (false, "User not found.");

        var isAdmin = userRole == "admin";
        var isOwner = true;

        if (!isAdmin && !isOwner)
            return (false, "Unauthorized to update this user.");

        if (!string.IsNullOrWhiteSpace(request.FullName))
        {
            if (request.FullName.Length > 200)
                return (false, "Full name must not exceed 200 characters.");
            user.FullName = request.FullName;
        }

        if (!string.IsNullOrWhiteSpace(request.Email))
        {
            if (request.Email.Length > 320 || !request.Email.Contains("@"))
                return (false, "Invalid email address.");

            var emailExists = await db.Users.AnyAsync(u => u.Email == request.Email && u.UserId != userId);
            if (emailExists)
                return (false, "Email is already in use.");

            user.Email = request.Email;
        }

        if (isAdmin && !string.IsNullOrWhiteSpace(request.Role))
        {
            var validRoles = new[] { "admin", "operator", "viewer", "system" };
            if (!validRoles.Contains(request.Role))
                return (false, "Invalid role.");
            user.Role = request.Role;
        }

        if (isAdmin && request.IsActive.HasValue)
        {
            user.IsActive = request.IsActive.Value;
        }

        user.UpdatedAt = AppClock.NowIst;
        await db.SaveChangesAsync();

        log.LogInformation("User {UserId} updated by {Role}: Email={Email}, Role={Role}, Active={Active}",
            userId, userRole, request.Email, request.Role, request.IsActive);

        return (true, "User updated successfully.");
    }

    public async Task<(bool Success, string Message)> DeleteUserAsync(int userId, string? userRole, DeleteUserRequest request)
    {
        var user = await db.Users.FindAsync(userId);
        if (user is null)
            return (false, "User not found.");

        var isAdmin = userRole == "admin";

        if (!isAdmin)
            return (false, "Only admins can delete users.");

        bool valid;
        try { valid = BCrypt.Net.BCrypt.Verify(request.Password, user.PasswordHash); }
        catch { valid = false; }

        if (!valid)
            return (false, "Invalid password.");

        db.Users.Remove(user);
        var deletedResets = await db.PasswordResets.Where(r => r.UserId == userId).ToListAsync();
        db.PasswordResets.RemoveRange(deletedResets);

        await db.SaveChangesAsync();

        log.LogInformation("User {UserId} ({Email}) deleted by {AdminRole}", userId, user.Email, userRole);

        return (true, "User deleted successfully.");
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private string GenerateToken(User user)
    {
        var key    = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(config["JwtSettings:SecretKey"]!));
        var creds  = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);
        var expiry = int.TryParse(config["JwtSettings:ExpiryMinutes"], out var m) ? m : 480;

        var claims = new[]
        {
            new Claim(JwtRegisteredClaimNames.Sub,   user.UserId.ToString()),
            new Claim(JwtRegisteredClaimNames.Email, user.Email),
            new Claim(ClaimTypes.Name,               user.Username),
            new Claim(ClaimTypes.Role,               user.Role),
            new Claim("full_name",                   user.FullName ?? user.Username),
            new Claim(JwtRegisteredClaimNames.Jti,   Guid.NewGuid().ToString())
        };

        var token = new JwtSecurityToken(
            issuer:             config["JwtSettings:Issuer"],
            audience:           config["JwtSettings:Audience"],
            claims:             claims,
            expires:            AppClock.NowIst.AddMinutes(expiry),
            signingCredentials: creds);

        return new JwtSecurityTokenHandler().WriteToken(token);
    }

    private static LoginResponse Fail(string message) =>
        new() { Success = false, Message = message };
}
