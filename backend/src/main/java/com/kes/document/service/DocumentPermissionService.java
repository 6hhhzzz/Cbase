package com.kes.document.service;

import com.kes.document.model.DocumentMeta;
import com.kes.document.repository.DocumentMetaRepository;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 文档权限查询服务 — document 模块对外暴露的权限查询门面。
 *
 * <p>为 auth 模块的 {@code PermissionQueryService} 提供文档级权限数据，
 * 替代直接跨模块访问 {@link DocumentMetaRepository}。
 * auth 模块通过注入本 Service（而非 Repository）实现符合 DDD 分层的跨模块通信。
 */
@Service
public class DocumentPermissionService {

    private final DocumentMetaRepository docMetaRepo;

    public DocumentPermissionService(DocumentMetaRepository docMetaRepo) {
        this.docMetaRepo = docMetaRepo;
    }

    /**
     * 获取指定 KB 中具有自定义权限（inherit_permissions = false）的文档 ID 列表。
     * 用于 auth 模块的文档级权限解析。
     *
     * @param kbIds 知识库 ID 列表
     * @return 需要独立 ACE 检查的文档 ID 列表
     */
    public List<String> getCustomPermissionDocIds(List<String> kbIds) {
        if (kbIds == null || kbIds.isEmpty()) {
            return List.of();
        }
        return docMetaRepo.findCustomPermissionDocs(kbIds).stream()
            .map(DocumentMeta::getId)
            .toList();
    }
}
