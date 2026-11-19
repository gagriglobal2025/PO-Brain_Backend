using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using POBrain.API.Models.Email;
using POBrain.API.Services;
using Serilog.Context;

namespace POBrain.API.Controllers;

[ApiController]
[Route("api/emails")]
public class EmailsController(IEmailService emailService, ILogger<EmailsController> logger) : ControllerBase
{
    [HttpPost("order-acknowledgment")]
    [AllowAnonymous]
    public async Task<IActionResult> SendOrderAcknowledgment([FromBody] OrderAcknowledgmentEmailRequest request)
    {
        if (request.OrderId <= 0)
        {
            return BadRequest(new { success = false, message = "Valid OrderId is required." });
        }

        using (LogContext.PushProperty("Action", "SendOrderAcknowledgmentEmail"))
        using (LogContext.PushProperty("OrderId", request.OrderId))
        {
            logger.LogInformation("Processing order acknowledgment email request: OrderId={OrderId}, PoNumber={PoNum}, Recipient={Recipient}",
                request.OrderId, request.PoNumber ?? "N/A", request.RecipientEmail ?? "From DB");

            var result = await emailService.SendOrderAcknowledgmentAsync(request);
            if (!result.Success)
            {
                return BadRequest(new { success = false, message = result.Message });
            }

            return Ok(new { success = true, message = result.Message });
        }
    }
}
