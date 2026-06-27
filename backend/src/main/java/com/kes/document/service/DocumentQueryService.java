package com.kes.document.service;

import com.kes.common.exception.BusinessException;
import com.kes.document.model.DocumentMeta;
import com.kes.document.repository.DocumentMetaRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 文档查询服务 — 只读查询操作，无写副作用。
 *
 * <p>从 {@link DocumentService} 提取，职责聚焦于文档数据的检索。
 * 包含列表查询、单条查询、权限验证、回收站文档查询等只读方法。</p>
 */
@Service
public class DocumentQueryService {

    private final DocumentMetaRepository docRepo;

    public DocumentQueryService(DocumentMetaRepository docRepo) {
        this.docRepo = docRepo;
    }

    /** 查询 KB 下的文档列表 */
    public Page<DocumentMeta> list(String kbId, String userId, String status, int page, int size) {
        PageRequest pageRequest = PageRequest.of(page - 1, size, Sort.by(Sort.Direction.DESC, "createdAt"));
        if (status != null && !status.isBlank()) {
            return docRepo.findByKbIdAndApprovalStatus(kbId, status, pageRequest);
        }
        return docRepo.findByKbIdAndStatus(kbId, "active", pageRequest);
    }

    /** 根据 ID 获取文档，不存在则抛出异常 */
    public DocumentMeta getById(String docId) {
        return docRepo.findById(docId)
            .orElseThrow(() -> BusinessException.documentNotFound(docId));
    }

    /** 验证文档属于指定 KB */
    public DocumentMeta validateKbAccess(String docId, String kbId) {
        DocumentMeta meta = getById(docId);
        if (!meta.getKbId().equals(kbId)) {
            throw BusinessException.accessDenied();
        }
        return meta;
    }

    /**
     * 查询指定活跃 KB 下已软删除的文档。
     * 由 KbService.getTrashData() 调用。
     */
    public List<DocumentMeta> getDeletedDocsInKbs(List<String> activeKbIds) {
        if (activeKbIds == null || activeKbIds.isEmpty()) return List.of();
        return docRepo.findByKbIdInAndStatus(activeKbIds, "soft_deleted");
    }
}
