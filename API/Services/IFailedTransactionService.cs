using POBrain.API.Models.Common;
using POBrain.API.Models.FailedTransactions;

namespace POBrain.API.Services;

public interface IFailedTransactionService
{
    Task<PagedResponse<FailedTransactionDto>> GetAllAsync(string? search, int page, int pageSize);
    Task<PagedResponse<FailedTransactionDto>> GetAllWithFiltersAsync(FailedTransactionFilterRequest filter);
    Task<byte[]> ExportToCsvAsync(FailedTransactionFilterRequest filter);
}
