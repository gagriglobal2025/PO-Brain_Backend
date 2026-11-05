using POBrain.API.Models.Common;
using POBrain.API.Models.Extractions;

namespace POBrain.API.Services;

public interface IExtractionService
{
    Task<PagedResponse<ExtractionDto>> GetAllAsync(string? search, int page, int pageSize);
    Task<PagedResponse<ExtractionDto>> GetAllWithFiltersAsync(ExtractionFilterRequest filter);
    Task<byte[]> ExportToCsvAsync(ExtractionFilterRequest filter);
}
