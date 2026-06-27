package com.kes.auth.event;

import com.kes.auth.repository.AceRepository;
import com.kes.common.event.DocumentPermanentlyDeletedEvent;
import com.kes.common.event.KbPermanentlyDeletedEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * KB/文档清理事件监听器。
 * 响应永久删除事件，清理 ACE 条目。
 */
@Component
public class KbCleanupEventListeners {

    private static final Logger log = LoggerFactory.getLogger(KbCleanupEventListeners.class);

    private final AceRepository aceRepo;

    public KbCleanupEventListeners(AceRepository aceRepo) {
        this.aceRepo = aceRepo;
    }

    @Transactional
    @EventListener
    public void onKbPermanentlyDeleted(KbPermanentlyDeletedEvent event) {
        aceRepo.deleteBySpaceIdAndResourceTypeAndResourceId(event.spaceId(), "kb", event.kbId());
        log.info("KB ACE 条目已清理: kbId={}", event.kbId());
    }

    @Transactional
    @EventListener
    public void onDocumentPermanentlyDeleted(DocumentPermanentlyDeletedEvent event) {
        aceRepo.deleteByResource("document", event.docId());
        log.info("文档 ACE 条目已清理: docId={}", event.docId());
    }
}
