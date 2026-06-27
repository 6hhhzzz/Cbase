package com.kes.auth.model;

import java.util.List;

/**
 * 批量导入用户结果。
 */
public record BatchImportResult(
    int total,
    int success,
    int failed,
    List<ImportError> errors
) {
    public record ImportError(int row, String username, String reason) {}
}
