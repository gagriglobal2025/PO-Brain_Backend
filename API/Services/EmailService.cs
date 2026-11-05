using System.Net;
using System.Net.Mail;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

namespace POBrain.API.Services;

public sealed class EmailService(IConfiguration config, ILogger<EmailService> logger) : IEmailService
{
    public async Task<(bool Success, string Message)> SendOtpAsync(string email, string otp, string userName)
    {
        try
        {
            var smtpConfig = config.GetSection("SmtpSettings");
            var smtpServer = smtpConfig["Server"] ?? "smtp.gmail.com";
            var smtpPort = int.Parse(smtpConfig["Port"] ?? "587");
            var smtpUser = smtpConfig["Username"];
            var smtpPass = smtpConfig["Password"];
            var fromEmail = smtpConfig["FromEmail"];
            var fromName = smtpConfig["FromName"] ?? "PO-Brain";
            var enableSsl = bool.Parse(smtpConfig["EnableSsl"] ?? "true");

            if (string.IsNullOrEmpty(smtpUser) || string.IsNullOrEmpty(smtpPass))
            {
                logger.LogError("SMTP credentials not configured. Username: {User}, Password exists: {PassExists}",
                    string.IsNullOrEmpty(smtpUser) ? "MISSING" : "SET",
                    !string.IsNullOrEmpty(smtpPass));
                return (false, "SMTP configuration is incomplete.");
            }

            logger.LogInformation("Sending OTP email: Server={Server}, Port={Port}, User={User}, To={Email}",
                smtpServer, smtpPort, smtpUser, email);

            using var client = new SmtpClient(smtpServer, smtpPort)
            {
                Credentials = new NetworkCredential(smtpUser, smtpPass),
                EnableSsl = enableSsl,
                Timeout = 30000
            };

            var subject = "PO-Brain Password Reset - Your OTP Code";
            var body = $$"""
                <html>
                <head>
                    <style>
                        body { font-family: Arial, sans-serif; background-color: #f4f4f4; }
                        .container { max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; }
                        .header { color: #333; text-align: center; margin-bottom: 20px; }
                        .content { color: #555; line-height: 1.6; }
                        .otp-box { background-color: #f0f0f0; border: 2px solid #007bff; padding: 15px; text-align: center; border-radius: 5px; margin: 20px 0; }
                        .otp-code { font-size: 48px; font-weight: bold; color: #007bff; letter-spacing: 4px; }
                        .footer { color: #999; text-align: center; margin-top: 20px; font-size: 12px; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Password Reset Request</h1>
                        </div>
                        <div class="content">
                            <p>Hi {{userName}},</p>
                            <p>You requested to reset your PO-Brain account password. Use the OTP code below to proceed with the reset:</p>
                            <div class="otp-box">
                                <div class="otp-code">{{otp}}</div>
                            </div>
                            <p><strong>Important:</strong></p>
                            <ul>
                                <li>This OTP expires in 5 minutes</li>
                                <li>Never share this code with anyone</li>
                                <li>If you did not request this, please ignore this email</li>
                            </ul>
                            <p>Best regards,<br />The PO-Brain Team</p>
                        </div>
                        <div class="footer">
                            <p>This is an automated message. Please do not reply to this email.</p>
                        </div>
                    </div>
                </body>
                </html>
                """;

            var message = new MailMessage
            {
                From = new MailAddress(fromEmail!, fromName),
                Subject = subject,
                Body = body,
                IsBodyHtml = true
            };

            message.To.Add(email);

            await client.SendMailAsync(message);
            logger.LogInformation("✅ OTP email sent successfully to {Email}", email);
            return (true, "OTP sent successfully to your email");
        }
        catch (SmtpException smtpEx)
        {
            logger.LogError(smtpEx, "❌ SMTP Error sending OTP to {Email}. StatusCode: {StatusCode}, Message: {Message}",
                email, smtpEx.StatusCode, smtpEx.Message);
            return (false, $"Email server error: {smtpEx.StatusCode}. Please try again later.");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "❌ Failed to send OTP email to {Email}. Exception: {ExceptionType}: {Message}",
                email, ex.GetType().Name, ex.Message);
            return (false, $"Failed to send OTP email. Error: {ex.GetType().Name}");
        }
    }
}
