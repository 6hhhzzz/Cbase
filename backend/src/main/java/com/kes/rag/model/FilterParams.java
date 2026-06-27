package com.kes.rag.model;

import java.util.List;

/**
 * 权限过滤器参数 — v4 ACE + 文档级权限。
 * Java 计算好用户有权访问的所有 kb_id 和需排除的 doc_id，传入列表。
 * Python 机械构建 WHERE 查询。
 *
 * <p>安全边界：Java 决定谁能看什么，Python 只负责执行。
 *
 * @param kbIds 用户有权访问的 KB ID 列表（必填）
 * @param docIds 需排除的文档 ID 列表。null 表示无文档级限制（默认），
 *               非 null 时 Python 端按 doc_id 过滤
 */
public record FilterParams(List<String> kbIds, List<String> docIds) {
    public FilterParams(List<String> kbIds) {
        this(kbIds, null);
    }

    public FilterParams() {
        this(List.of(), null);
    }
}
