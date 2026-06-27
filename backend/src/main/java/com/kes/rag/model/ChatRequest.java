package com.kes.rag.model;

import java.util.List;

/**
 * 前端聊天请求 DTO — v3.1 跨KB联合查询。
 * kb_ids 由服务端从 JWT 计算，不需要前端传入。
 * kb_id 作为会话归属的 KB（可选，跨KB模式下为空）。
 * excluded_kb_ids 为用户主动排除的 KB 列表。
 */
public class ChatRequest {

    private String query;
    private String conversationId;
    private String kbId;
    private List<String> excludedKbIds;

    public String getQuery() { return query; }
    public void setQuery(String query) { this.query = query; }

    public String getConversationId() { return conversationId; }
    public void setConversationId(String conversationId) { this.conversationId = conversationId; }

    public String getKbId() { return kbId; }
    public void setKbId(String kbId) { this.kbId = kbId; }

    public List<String> getExcludedKbIds() { return excludedKbIds; }
    public void setExcludedKbIds(List<String> excludedKbIds) { this.excludedKbIds = excludedKbIds; }
}
