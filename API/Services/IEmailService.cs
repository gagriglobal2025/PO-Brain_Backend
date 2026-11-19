using POBrain.API.Models.Email;

namespace POBrain.API.Services;

public interface IEmailService
{
    Task<(bool Success, string Message)> SendOtpAsync(string email, string otp, string userName);
    Task<(bool Success, string Message)> SendOrderAcknowledgmentAsync(OrderAcknowledgmentEmailRequest request);
}
