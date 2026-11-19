using MailKit.Net.Smtp;
using MailKit.Security;
using MimeKit;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using POBrain.API.Data;
using POBrain.API.Models.Email;
using System.Text;

namespace POBrain.API.Services;

public sealed class EmailService(
    IConfiguration config,
    ILogger<EmailService> logger,
    PoBrainDbContext db) : IEmailService
{
    private async Task ConnectAndSendAsync(MimeMessage message, string host, int port, string user, string pass, bool enableSsl)
    {
        using var client = new SmtpClient();
        client.ServerCertificateValidationCallback = (s, c, h, e) => true;

        bool connected = false;
        Exception? lastEx = null;

        var primaryOptions = port == 465 ? SecureSocketOptions.SslOnConnect : (enableSsl ? SecureSocketOptions.StartTls : SecureSocketOptions.None);
        try
        {
            await client.ConnectAsync(host, port, primaryOptions);
            connected = true;
        }
        catch (Exception ex)
        {
            lastEx = ex;
            logger.LogWarning(ex, "Failed connecting to SMTP on port {Port}. Attempting fallback port...", port);
        }

        if (!connected)
        {
            int altPort = port == 587 ? 465 : 587;
            var altOptions = altPort == 465 ? SecureSocketOptions.SslOnConnect : SecureSocketOptions.StartTls;
            try
            {
                await client.ConnectAsync(host, altPort, altOptions);
                connected = true;
                logger.LogInformation("Successfully connected to SMTP via fallback port {AltPort}", altPort);
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "Fallback connection to SMTP port {AltPort} also failed.", altPort);
                throw lastEx ?? ex;
            }
        }

        await client.AuthenticateAsync(user, pass);
        await client.SendAsync(message);
        await client.DisconnectAsync(true);
    }

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
                logger.LogError("SMTP credentials not configured. Username: {User}",
                    string.IsNullOrEmpty(smtpUser) ? "MISSING" : "SET");
                return (false, "SMTP configuration is incomplete.");
            }

            logger.LogInformation("Sending OTP email: Server={Server}, Port={Port}, User={User}, To={Email}",
                smtpServer, smtpPort, smtpUser, email);

            var subject = "PO-Brain Password Reset - Your OTP Code";
            var bodyHtml = $$"""
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

            var senderEmail = !string.IsNullOrWhiteSpace(smtpUser) ? smtpUser : fromEmail!;
            var message = new MimeMessage();
            message.From.Add(new MailboxAddress(fromName, senderEmail));
            if (!string.IsNullOrWhiteSpace(fromEmail) && !string.Equals(fromEmail, senderEmail, StringComparison.OrdinalIgnoreCase))
            {
                message.ReplyTo.Add(new MailboxAddress(fromName, fromEmail));
            }

            message.To.Add(MailboxAddress.Parse(email));
            message.Subject = subject;

            var builder = new BodyBuilder { HtmlBody = bodyHtml };
            message.Body = builder.ToMessageBody();

            await ConnectAndSendAsync(message, smtpServer, smtpPort, smtpUser, smtpPass, enableSsl);
            logger.LogInformation("✅ OTP email sent successfully to {Email}", email);
            return (true, "OTP sent successfully to your email");
        }
        catch (Exception ex)
        {
            var innerMsg = ex.InnerException?.Message;
            var fullErr = !string.IsNullOrWhiteSpace(innerMsg) ? $"{ex.Message} (Inner: {innerMsg})" : ex.Message;
            logger.LogError(ex, "❌ Failed to send OTP email to {Email}. Error: {Error}", email, fullErr);
            return (false, $"Email delivery failed: {fullErr}");
        }
    }

    public async Task<(bool Success, string Message)> SendOrderAcknowledgmentAsync(OrderAcknowledgmentEmailRequest request)
    {
        try
        {
            var smtpConfig = config.GetSection("SmtpSettings");
            var smtpServer = smtpConfig["Server"] ?? "smtp.gmail.com";
            var smtpPort = int.Parse(smtpConfig["Port"] ?? "587");
            var smtpUser = smtpConfig["Username"];
            var smtpPass = smtpConfig["Password"];
            var fromEmail = smtpConfig["FromEmail"] ?? smtpUser;
            var fromName = "Hyma Synthesis Pvt. Ltd";
            var enableSsl = bool.Parse(smtpConfig["EnableSsl"] ?? "true");

            if (string.IsNullOrEmpty(smtpUser) || string.IsNullOrEmpty(smtpPass))
            {
                logger.LogError("SMTP credentials not configured for Order Acknowledgment. Username: {User}",
                    string.IsNullOrEmpty(smtpUser) ? "MISSING" : "SET");
                return (false, "SMTP configuration is incomplete.");
            }

            // 1. Resolve Items and Customer if not fully supplied
            var items = request.Items ?? [];
            var customer = request.Customer ?? new CustomerDetailsDto();
            string? ipAddress = request.IpAddress;
            string? acceptanceDate = request.AcceptanceDate;

            if (items.Count == 0 && request.OrderId > 0)
            {
                var dbItems = await db.Database.SqlQuery<ClientOrderDbRow>($"""
                    SELECT
                        OrderID,
                        PersonID,
                        ItemCode,
                        HSNCode,
                        GSTTAX,
                        CASNo,
                        ChemicalName,
                        PackSize,
                        Quantity,
                        UnitPrice,
                        Price,
                        Discount,
                        DiscountPrice,
                        GstPrice,
                        IPAddress,
                        OrderDate
                    FROM dbo.tblClientOrder
                    WHERE OrderID = {request.OrderId}
                    """).ToListAsync();

                if (dbItems.Count > 0)
                {
                    items = dbItems.Select(r => new OrderItemEmailDto
                    {
                        OrderNo = r.OrderID,
                        ItemCode = r.ItemCode ?? "",
                        HsnCode = r.HSNCode ?? "",
                        GstRate = r.GSTTAX ?? 18,
                        CasNo = r.CASNo ?? "",
                        ChemicalName = r.ChemicalName ?? "",
                        PackSize = r.PackSize ?? "",
                        Quantity = r.Quantity,
                        UnitPrice = decimal.TryParse(r.UnitPrice, out var up) ? up : 0m,
                        Price = r.Price,
                        DiscountPercent = r.Discount,
                        DiscountPrice = r.DiscountPrice,
                        GstPrice = r.GstPrice,
                        TotalPrice = r.DiscountPrice + r.GstPrice
                    }).ToList();

                    var firstItem = dbItems.First();
                    ipAddress ??= firstItem.IPAddress;
                    if (firstItem.OrderDate.HasValue)
                    {
                        acceptanceDate ??= firstItem.OrderDate.Value.ToString("dd-MMM-yyyy");
                    }

                    if (string.IsNullOrWhiteSpace(customer.Email) && firstItem.PersonID.HasValue)
                    {
                        var reg = await db.Database.SqlQuery<RegistrationDbRow>($"""
                            SELECT TOP 1
                                PersonID,
                                CompanyName,
                                ContPerson,
                                EMailID,
                                Phone1,
                                City,
                                GSTNo
                            FROM dbo.tblRegistration
                            WHERE PersonID = {firstItem.PersonID.Value}
                            """).FirstOrDefaultAsync();

                        if (reg != null)
                        {
                            customer.CompanyName ??= reg.CompanyName;
                            customer.CustomerName ??= reg.ContPerson;
                            customer.Email ??= reg.EMailID;
                            customer.ContactNo ??= reg.Phone1;
                            customer.City ??= reg.City;
                            customer.GstNo ??= reg.GSTNo;
                        }
                    }
                }
            }

            if (string.IsNullOrWhiteSpace(customer.Comments) && request.OrderId > 0)
            {
                var commentRow = await db.Database.SqlQuery<CommentDbRow>($"""
                    SELECT TOP 1 Comment
                    FROM dbo.tblComment
                    WHERE OrderID = {request.OrderId}
                    ORDER BY CommentID DESC
                    """).FirstOrDefaultAsync();

                if (commentRow != null && !string.IsNullOrWhiteSpace(commentRow.Comment))
                {
                    customer.Comments = commentRow.Comment;
                }
            }

            var recipientEmail = request.RecipientEmail ?? customer.Email;
            if (string.IsNullOrWhiteSpace(recipientEmail))
            {
                recipientEmail = smtpConfig["FallbackRecipientEmail"];
            }

            if (string.IsNullOrWhiteSpace(recipientEmail))
            {
                return (false, "Recipient email address is required.");
            }

            ipAddress ??= "122.175.19.60";
            acceptanceDate ??= AppClock.NowIst.ToString("dd-MMM-yyyy");
            var acceptanceStatus = request.AcceptanceStatus ?? "ACCEPTED ELECTRONICALLY AT THE TIME OF WEB ORDER PLACEMENT";

            // 2. Build HTML Body
            var htmlBody = BuildOrderAcknowledgmentHtml(
                request.OrderId,
                customer,
                items,
                ipAddress,
                acceptanceDate,
                acceptanceStatus
            );

            // 3. Compose Email with MailKit
            var senderEmail = !string.IsNullOrWhiteSpace(smtpUser) ? smtpUser : fromEmail!;
            var message = new MimeMessage();
            message.From.Add(new MailboxAddress(fromName, senderEmail));
            if (!string.IsNullOrWhiteSpace(fromEmail) && !string.Equals(fromEmail, senderEmail, StringComparison.OrdinalIgnoreCase))
            {
                message.ReplyTo.Add(new MailboxAddress(fromName, fromEmail));
            }

            message.To.Add(MailboxAddress.Parse(recipientEmail));
            message.Subject = $"Hyma | Web | Order | {request.OrderId}";

            var configuredCcs = smtpConfig.GetSection("InternalCcEmails").Get<string[]>() ?? [];
            foreach (var cc in configuredCcs)
            {
                if (!string.IsNullOrWhiteSpace(cc))
                {
                    try { message.Cc.Add(MailboxAddress.Parse(cc.Trim())); }
                    catch { /* skip invalid CC */ }
                }
            }

            if (request.CcEmails != null)
            {
                foreach (var cc in request.CcEmails)
                {
                    if (!string.IsNullOrWhiteSpace(cc))
                    {
                        try { message.Cc.Add(MailboxAddress.Parse(cc.Trim())); }
                        catch { /* skip invalid CC */ }
                    }
                }
            }

            var builder = new BodyBuilder { HtmlBody = htmlBody };

            if (!string.IsNullOrWhiteSpace(request.AttachmentBase64))
            {
                try
                {
                    var fileBytes = Convert.FromBase64String(request.AttachmentBase64);
                    var fileName = !string.IsNullOrWhiteSpace(request.AttachmentFileName)
                        ? request.AttachmentFileName
                        : $"{request.OrderId}_Order.pdf";
                    builder.Attachments.Add(fileName, fileBytes);
                }
                catch (Exception ex)
                {
                    logger.LogWarning(ex, "Failed to attach base64 document for Order #{OrderId}", request.OrderId);
                }
            }

            message.Body = builder.ToMessageBody();

            await ConnectAndSendAsync(message, smtpServer, smtpPort, smtpUser, smtpPass, enableSsl);
            logger.LogInformation("✅ Order acknowledgment email sent successfully to {Email} for Order #{OrderId}",
                recipientEmail, request.OrderId);

            return (true, $"Order acknowledgment email sent successfully to {recipientEmail}");
        }
        catch (Exception ex)
        {
            var innerMsg = ex.InnerException?.Message;
            var fullErr = !string.IsNullOrWhiteSpace(innerMsg)
                ? $"{ex.Message} (Inner: {innerMsg})"
                : ex.Message;
            logger.LogError(ex, "❌ Failed to send order acknowledgment for Order #{OrderId}. Error: {Error}",
                request.OrderId, fullErr);
            return (false, $"Email delivery failed: {fullErr}");
        }
    }

    private static string BuildOrderAcknowledgmentHtml(
        long orderId,
        CustomerDetailsDto customer,
        List<OrderItemEmailDto> items,
        string ipAddress,
        string acceptanceDate,
        string acceptanceStatus)
    {
        var sbRows = new StringBuilder();
        decimal totalUnitPrice = 0;
        decimal totalPrice = 0;
        decimal totalDiscountPrice = 0;
        decimal totalGstPrice = 0;
        decimal grandTotal = 0;

        foreach (var item in items)
        {
            totalUnitPrice += item.UnitPrice;
            totalPrice += item.Price;
            totalDiscountPrice += item.DiscountPrice;
            totalGstPrice += item.GstPrice;
            grandTotal += item.TotalPrice;

            sbRows.Append($"""
                <tr>
                    <td style="border: 1px solid #ddd; padding: 6px; text-align: center;"><a href="#" style="color: #1a5276; text-decoration: underline;">{item.OrderNo}</a></td>
                    <td style="border: 1px solid #ddd; padding: 6px; text-align: center;">{item.ItemCode}</td>
                    <td style="border: 1px solid #ddd; padding: 6px; text-align: center;">{item.HsnCode}</td>
                    <td style="border: 1px solid #ddd; padding: 6px; text-align: center;">{item.GstRate}</td>
                    <td style="border: 1px solid #ddd; padding: 6px; text-align: center;">{item.CasNo}</td>
                    <td style="border: 1px solid #ddd; padding: 6px;">{item.ChemicalName}</td>
                    <td style="border: 1px solid #ddd; padding: 6px; text-align: center;">{item.PackSize}</td>
                    <td style="border: 1px solid #ddd; padding: 6px; text-align: center;">{item.Quantity:N0}</td>
                    <td style="border: 1px solid #ddd; padding: 6px; text-align: right;">{item.UnitPrice:N2}</td>
                    <td style="border: 1px solid #ddd; padding: 6px; text-align: right;">{item.Price:N2}</td>
                    <td style="border: 1px solid #ddd; padding: 6px; text-align: right;">{item.DiscountPercent:N2}</td>
                    <td style="border: 1px solid #ddd; padding: 6px; text-align: right;">{item.DiscountPrice:N2}</td>
                    <td style="border: 1px solid #ddd; padding: 6px; text-align: right;">{item.GstPrice:N2}</td>
                    <td style="border: 1px solid #ddd; padding: 6px; text-align: right; font-weight: bold;">{item.TotalPrice:N2}</td>
                </tr>
                """);
        }

        var commentsVal = !string.IsNullOrWhiteSpace(customer.Comments) ? customer.Comments : "—";
        var gstVal = !string.IsNullOrWhiteSpace(customer.GstNo) ? customer.GstNo : "—";
        var phoneVal = !string.IsNullOrWhiteSpace(customer.ContactNo) ? customer.ContactNo : "—";
        var cityVal = !string.IsNullOrWhiteSpace(customer.City) ? customer.City : "—";

        return $$"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8" />
                <style>
                    body { font-family: Arial, sans-serif; font-size: 13px; color: #222; line-height: 1.5; margin: 15px; }
                    table { border-collapse: collapse; width: 100%; margin-top: 10px; font-size: 12px; }
                    th { background-color: #1a5276; color: white; padding: 6px 8px; text-align: center; font-size: 12px; font-weight: bold; border: 1px solid #1a5276; }
                    td { border: 1px solid #ddd; padding: 6px 8px; }
                    .table-header { background-color: #f2f2f2; color: #333; font-weight: bold; font-size: 13px; text-align: left; }
                    .footer { margin-top: 20px; font-size: 12px; color: #333; }
                    a { color: #1a5276; }
                </style>
            </head>
            <body>
                <p>Dear Customer ,</p>
                <p>Thanks for your order.</p>
                <p>We acknowledge the receipt of the order copy. The material ordered against the Order No: <a href="#" style="color: #1a5276; text-decoration: underline;"><strong>{{orderId}}</strong></a> will be processed against the availability.</p>

                <!-- Customer Details Table -->
                <table style="margin-top: 15px; margin-bottom: 20px;">
                    <tr class="table-header">
                        <td colspan="2" style="padding: 6px 10px; font-weight: bold; background-color: #f2f2f2; border: 1px solid #ddd;">Customer Details</td>
                    </tr>
                    <tr>
                        <td style="width: 220px; font-weight: bold; border: 1px solid #ddd;">Customer Company Name</td>
                        <td style="border: 1px solid #ddd;">: {{customer.CompanyName}}</td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; border: 1px solid #ddd;">Customer Name</td>
                        <td style="border: 1px solid #ddd;">: {{customer.CustomerName}}</td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; border: 1px solid #ddd;">Customer Email</td>
                        <td style="border: 1px solid #ddd;">: <a href="mailto:{{customer.Email}}">{{customer.Email}}</a></td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; border: 1px solid #ddd;">Customer Contact No.</td>
                        <td style="border: 1px solid #ddd;">: {{phoneVal}}</td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; border: 1px solid #ddd;">Customer City</td>
                        <td style="border: 1px solid #ddd;">: {{cityVal}}</td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; border: 1px solid #ddd;">GST No.</td>
                        <td style="border: 1px solid #ddd;">: {{gstVal}}</td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; border: 1px solid #ddd;">Comments</td>
                        <td style="border: 1px solid #ddd;">: {{commentsVal}}</td>
                    </tr>
                </table>

                <!-- Order Details Table -->
                <table style="margin-top: 15px;">
                    <thead>
                        <tr>
                            <th>Order No</th>
                            <th>Item Code</th>
                            <th>HSN Code</th>
                            <th>GST %</th>
                            <th>CAS NO</th>
                            <th>Chemical Name</th>
                            <th>Pack Size</th>
                            <th>Quantity</th>
                            <th>Unit Price (Rs.)</th>
                            <th>Price (Rs.)</th>
                            <th>Discount %</th>
                            <th>Discount Price</th>
                            <th>GST Price</th>
                            <th>Total Price</th>
                        </tr>
                    </thead>
                    <tbody>
                        {{sbRows}}
                    </tbody>
                    <tfoot>
                        <tr style="font-weight: bold; background-color: #fff;">
                            <td colspan="8" style="text-align: right; border: 1px solid #ddd; padding: 6px;">Total:</td>
                            <td style="text-align: right; border: 1px solid #ddd; padding: 6px;">{{totalUnitPrice:N2}}</td>
                            <td style="text-align: right; border: 1px solid #ddd; padding: 6px;">{{totalPrice:N2}}</td>
                            <td style="text-align: right; border: 1px solid #ddd; padding: 6px;"></td>
                            <td style="text-align: right; border: 1px solid #ddd; padding: 6px;">{{totalDiscountPrice:N2}}</td>
                            <td style="text-align: right; border: 1px solid #ddd; padding: 6px;">{{totalGstPrice:N2}}</td>
                            <td style="text-align: right; border: 1px solid #ddd; padding: 6px;">{{grandTotal:N2}}</td>
                        </tr>
                    </tfoot>
                </table>

                <!-- Contact & Follow-up Section -->
                <div class="footer">
                    <p style="margin-bottom: 4px;">We will get back to you in case of any clarification required / post you a mail in case of discrepancy.</p>
                    <p style="margin-top: 0; margin-bottom: 4px;">You can contact:</p>
                    <p style="margin-top: 0; line-height: 1.4;">
                        <a href="mailto:sales@hymasynthesis.com">sales@hymasynthesis.com</a><br />
                        <a href="mailto:enquiry@hymasynthesis.com">enquiry@hymasynthesis.com</a>
                    </p>
                </div>

                <!-- Product Sale, End-Use and Misuse Disclaimer -->
                <div style="margin-top: 25px; font-size: 11px; color: #444; line-height: 1.5;">
                    <p style="font-weight: bold; margin-bottom: 6px; font-size: 12px; color: #222;">Product Sale, End-Use and Misuse Disclaimer</p>
                    <ol style="padding-left: 20px; margin-top: 4px;">
                        <li style="margin-bottom: 4px;">Products supplied by HSPL (Hyma Synthesis Private Limited) to an authorized distributor, company, university, research institution, academic/scientific organization, laboratory, or any other approved customer/end user are strictly intended for legitimate institutional, academic, scientific, research, development, testing or laboratory purposes only.</li>
                        <li style="margin-bottom: 4px;">The products shall not be sold, transferred, supplied, resold or otherwise made available to any individual person for personal use, or to any unauthorized person, entity or organization. Authorized distributors and customers shall ensure that the products are supplied only to genuine and duly identified institutional or professional end users and are used strictly for the declared and legitimate purpose.</li>
                        <li style="margin-bottom: 4px;">The distributor/customer/end user shall be solely responsible for ensuring compliance with all applicable laws, regulations, licenses, permits, approvals, storage requirements, handling requirements, safety requirements and end-use restrictions applicable to the products in their possession or control.</li>
                        <li style="margin-bottom: 4px;">The distributor/customer/end user shall not divert, resell, transfer, modify, misuse or permit the use of the products for any unlawful, unauthorized or undeclared purpose. Where applicable, HSPL reserves the right to request end-use information, institutional details, declarations or supporting documents before accepting or fulfilling an order.</li>
                        <li style="margin-bottom: 4px;">HSPL shall not be responsible or liable for any misuse, unauthorized use, diversion, resale, transfer, improper handling, improper storage or unlawful use of the products by any distributor, customer, end user or any subsequent recipient after the products have been supplied by HSPL.</li>
                        <li style="margin-bottom: 4px;">Any violation of the above conditions may result in rejection or cancellation of the order, suspension or termination of the business relationship and/or such other action as may be permissible under applicable law.</li>
                        <li style="margin-bottom: 4px;">By placing an order or accepting delivery of the products, the distributor/customer/end user acknowledges and agrees to comply with the above conditions and accepts responsibility for the proper and lawful end use of the products.</li>
                    </ol>
                </div>

                <!-- Customer Acceptance (Digital) Table -->
                <table style="margin-top: 20px; border: 1px solid #ddd;">
                    <tr class="table-header">
                        <td colspan="2" style="padding: 6px 10px; font-weight: bold; background-color: #f2f2f2; border: 1px solid #ddd; text-transform: uppercase;">CUSTOMER ACCEPTANCE (DIGITAL)</td>
                    </tr>
                    <tr>
                        <td colspan="2" style="padding: 6px 10px; font-size: 11px; color: #555; border: 1px solid #ddd;">
                            By placing this web order, the customer confirms that they have read, understood and agree to the above Product Sale, End-Use and Misuse Disclaimer.
                        </td>
                    </tr>
                    <tr>
                        <td style="width: 220px; font-weight: bold; border: 1px solid #ddd;">Customer Company</td>
                        <td style="border: 1px solid #ddd;">: {{customer.CompanyName}}</td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; border: 1px solid #ddd;">Customer Name</td>
                        <td style="border: 1px solid #ddd;">: {{customer.CustomerName}}</td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; border: 1px solid #ddd;">IP Address</td>
                        <td style="border: 1px solid #ddd;">: {{ipAddress}}</td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; border: 1px solid #ddd;">Date of Digital Acceptance</td>
                        <td style="border: 1px solid #ddd;">: {{acceptanceDate}}</td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; border: 1px solid #ddd;">Acceptance Status</td>
                        <td style="border: 1px solid #ddd;">: {{acceptanceStatus}}</td>
                    </tr>
                </table>
            </body>
            </html>
            """;
    }

    private sealed class ClientOrderDbRow
    {
        public long OrderID { get; set; }
        public int? PersonID { get; set; }
        public string? ItemCode { get; set; }
        public string? HSNCode { get; set; }
        public int? GSTTAX { get; set; }
        public string? CASNo { get; set; }
        public string? ChemicalName { get; set; }
        public string? PackSize { get; set; }
        public decimal Quantity { get; set; }
        public string? UnitPrice { get; set; }
        public decimal Price { get; set; }
        public int Discount { get; set; }
        public decimal DiscountPrice { get; set; }
        public decimal GstPrice { get; set; }
        public string? IPAddress { get; set; }
        public DateTime? OrderDate { get; set; }
    }

    private sealed class RegistrationDbRow
    {
        public int PersonID { get; set; }
        public string? CompanyName { get; set; }
        public string? ContPerson { get; set; }
        public string? EMailID { get; set; }
        public string? Phone1 { get; set; }
        public string? City { get; set; }
        public string? GSTNo { get; set; }
    }

    private sealed class CommentDbRow
    {
        public string? Comment { get; set; }
    }
}
