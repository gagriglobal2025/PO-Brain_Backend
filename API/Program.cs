using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using Microsoft.OpenApi.Models;
using POBrain.API.Data;
using POBrain.API.Hubs;
using POBrain.API.Services;
using Serilog;
using System.Text;

var builder = WebApplication.CreateBuilder(args);

// ── Serilog ──────────────────────────────────────────────────────────────────
Log.Logger = new LoggerConfiguration()
    .ReadFrom.Configuration(builder.Configuration)
    .Enrich.FromLogContext()
    .CreateLogger();

builder.Host.UseSerilog();

// ── EF Core ──────────────────────────────────────────────────────────────────
builder.Services.AddDbContext<PoBrainDbContext>(options =>
    options.UseSqlServer(builder.Configuration.GetConnectionString("DefaultConnection")));

// ── JWT Auth ─────────────────────────────────────────────────────────────────
var jwt = builder.Configuration.GetSection("JwtSettings");
var secretKey = Encoding.UTF8.GetBytes(jwt["SecretKey"]!);

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer           = true,
            ValidateAudience         = true,
            ValidateLifetime         = true,
            ValidateIssuerSigningKey = true,
            ValidIssuer              = jwt["Issuer"],
            ValidAudience            = jwt["Audience"],
            IssuerSigningKey         = new SymmetricSecurityKey(secretKey),
            ClockSkew                = TimeSpan.Zero
        };
        options.Events = new JwtBearerEvents
        {
            OnMessageReceived = ctx =>
            {
                // SignalR via query string
                var token = ctx.Request.Query["access_token"].ToString();
                if (!string.IsNullOrEmpty(token) && ctx.HttpContext.Request.Path.StartsWithSegments("/hubs"))
                {
                    ctx.Token = token;
                    return Task.CompletedTask;
                }

                // Accept token without "Bearer " prefix
                var authHeader = ctx.Request.Headers["Authorization"].ToString();
                if (!string.IsNullOrEmpty(authHeader))
                {
                    if (authHeader.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
                        ctx.Token = authHeader["Bearer ".Length..];
                    else
                        ctx.Token = authHeader;
                }
                return Task.CompletedTask;
            }
        };
    });

builder.Services.AddAuthorization();

// ── CORS ─────────────────────────────────────────────────────────────────────
var origins = builder.Configuration
    .GetSection("CorsSettings:AllowedOrigins")
    .Get<string[]>() ?? [];

builder.Services.AddCors(o =>
    o.AddPolicy("AllowFrontend", p =>
        p.WithOrigins(origins)
         .AllowAnyHeader()
         .AllowAnyMethod()
         .AllowCredentials()
         .WithExposedHeaders("Content-Disposition", "Content-Type", "Content-Length")));

// ── SignalR ───────────────────────────────────────────────────────────────────
builder.Services.AddSignalR();

// ── Application Services ─────────────────────────────────────────────────────
builder.Services.AddScoped<IEmailService, EmailService>();
builder.Services.AddScoped<IAuthService, AuthService>();
builder.Services.AddScoped<IDashboardService, DashboardService>();
builder.Services.AddScoped<IExtractionService, ExtractionService>();
builder.Services.AddScoped<ILogService, LogService>();
builder.Services.AddScoped<IFailedTransactionService, FailedTransactionService>();
builder.Services.AddScoped<INotificationService, NotificationService>();

// ── MVC + Swagger ─────────────────────────────────────────────────────────────
builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(c =>
{
    c.SwaggerDoc("v1", new OpenApiInfo
    {
        Title   = "PO-Brain API",
        Version = "v1",
        Description = "Enterprise Purchase Order Extraction & Monitoring API"
    });
    c.AddSecurityDefinition("Bearer", new OpenApiSecurityScheme
    {
        Name        = "Authorization",
        Type        = SecuritySchemeType.ApiKey,
        Scheme      = "Bearer",
        BearerFormat = "JWT",
        In          = ParameterLocation.Header,
        Description = "Enter your JWT token (with or without 'Bearer ' prefix)"
    });
    c.AddSecurityRequirement(new OpenApiSecurityRequirement
    {
        {
            new OpenApiSecurityScheme
            {
                Reference = new OpenApiReference { Type = ReferenceType.SecurityScheme, Id = "Bearer" }
            },
            Array.Empty<string>()
        }
    });
});

// ── Health Checks ─────────────────────────────────────────────────────────────
builder.Services.AddHealthChecks()
    .AddDbContextCheck<PoBrainDbContext>();

// ── Background Services ───────────────────────────────────────────────────────
builder.Services.AddHostedService<HealthBroadcastService>();

// ═════════════════════════════════════════════════════════════════════════════
var app = builder.Build();

app.UseSwagger();
// Relative endpoint (no leading slash) so Swagger UI resolves the spec against the
// current page — works at the domain root locally AND under a reverse-proxy sub-path
// (e.g. https://host/coreapiv1pob/swagger/) on the server.
app.UseSwaggerUI(c => c.SwaggerEndpoint("v1/swagger.json", "PO-Brain API v1"));

app.UseSerilogRequestLogging();
app.UseCors("AllowFrontend");
app.UseAuthentication();
app.UseAuthorization();

app.MapControllers();
app.MapHub<LogStreamHub>("/hubs/logs");
app.MapHub<HealthStreamHub>("/hubs/health");
app.MapHealthChecks("/health");

app.Run();
