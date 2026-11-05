using POBrain.API.Models.Common;
using POBrain.API.Models.Logs;

namespace POBrain.API.Services;

public interface ILogService
{
    Task<PagedResponse<LogEntryDto>> GetAllAsync(string? level, string? search, int page, int pageSize);
    Task<byte[]> ExportToCsvAsync(string? level, string? search);
}
