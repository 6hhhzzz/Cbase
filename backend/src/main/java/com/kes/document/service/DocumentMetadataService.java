package com.kes.document.service;

import com.kes.common.exception.BusinessException;
import com.kes.document.model.DocumentMeta;
import com.kes.document.repository.DocumentMetaRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.LocalDate;

/**
 * 文档元数据服务 — 更新文档的时效性/版本/权限继承等元数据字段。
 *
 * <p>从 {@link DocumentService} 提取，职责聚焦于文档 metadata 的修改。</p>
 */
@Service
public class DocumentMetadataService {

    private static final Logger log = LoggerFactory.getLogger(DocumentMetadataService.class);

    private final DocumentMetaRepository docRepo;

    public DocumentMetadataService(DocumentMetaRepository docRepo) {
        this.docRepo = docRepo;
    }

    /** 更新文档元数据（effective_date, expiry_date, version, inherit_permissions） */
    public DocumentMeta updateMetadata(String docId, String effectiveDate,
                                       String expiryDate, String version,
                                       Boolean inheritPermissions) {
        DocumentMeta meta = docRepo.findById(docId)
            .orElseThrow(() -> BusinessException.documentNotFound(docId));

        if (effectiveDate != null && !effectiveDate.isBlank()) {
            meta.setDocEffectiveDate(LocalDate.parse(effectiveDate));
        }
        if (expiryDate != null && !expiryDate.isBlank()) {
            meta.setDocExpiryDate(LocalDate.parse(expiryDate));
        } else if (expiryDate != null && expiryDate.isBlank()) {
            meta.setDocExpiryDate(null);
        }
        if (version != null) {
            meta.setDocVersion(version.isBlank() ? null : version);
        }
        if (inheritPermissions != null) {
            meta.setInheritPermissions(inheritPermissions);
        }

        docRepo.save(meta);
        log.info("文档元数据已更新: docId={}, inheritPermissions={}", docId, meta.isInheritPermissions());
        return meta;
    }
}
