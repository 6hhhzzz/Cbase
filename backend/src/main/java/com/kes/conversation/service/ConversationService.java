package com.kes.conversation.service;

import com.kes.common.exception.BusinessException;
import com.kes.conversation.model.Conversation;
import com.kes.conversation.model.Message;
import com.kes.conversation.repository.ConversationRepository;
import com.kes.conversation.repository.MessageRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * 会话管理服务 — v3.1 Space/KB 隔离，支持跨KB联合查询。
 */
@Service
public class ConversationService {

    private static final Logger log = LoggerFactory.getLogger(ConversationService.class);

    private final ConversationRepository convRepo;
    private final MessageRepository msgRepo;

    public ConversationService(ConversationRepository convRepo, MessageRepository msgRepo) {
        this.convRepo = convRepo;
        this.msgRepo = msgRepo;
    }

    /** 查询用户在特定 KB 中的会话列表（保留兼容） */
    public List<Conversation> listConversations(String userId, String kbId) {
        return convRepo.findByUserIdAndKbIdOrderByUpdatedAtDesc(userId, kbId);
    }

    /** v3.1: 查询用户在特定 Space 中的会话列表（跨KB联合查询） */
    public List<Conversation> listConversationsBySpace(String userId, String spaceId) {
        return convRepo.findByUserIdAndSpaceIdOrderByUpdatedAtDesc(userId, spaceId);
    }

    public List<Message> getMessages(String conversationId) {
        if (!convRepo.existsById(conversationId)) {
            throw BusinessException.conversationNotFound(conversationId);
        }
        return msgRepo.findByConversationIdOrderByCreatedAtAsc(conversationId);
    }

    @Transactional
    public void deleteConversation(String conversationId, String userId) {
        Conversation conv = convRepo.findById(conversationId)
            .orElseThrow(() -> BusinessException.conversationNotFound(conversationId));
        if (!conv.getUserId().equals(userId)) {
            throw BusinessException.conversationNotFound(conversationId);
        }
        convRepo.delete(conv);
        log.info("会话已删除: convId={}", conversationId);
    }

    @Transactional
    public Conversation getOrCreateConversation(String conversationId, String userId,
                                                 String title, String kbId, String spaceId) {
        return convRepo.findById(conversationId).orElseGet(() -> {
            Conversation conv = new Conversation();
            conv.setId(conversationId);
            conv.setUserId(userId);
            conv.setKbId(kbId);
            conv.setSpaceId(spaceId);
            conv.setTitle(title != null && title.length() > 100 ? title.substring(0, 100) : title);
            conv.setStatus("active");
            conv.setMessageCount(0);
            convRepo.save(conv);
            log.info("新会话创建: convId={}, userId={}, spaceId={}, kbId={}", conversationId, userId, spaceId, kbId);
            return conv;
        });
    }

    @Transactional
    public Message saveMessage(String conversationId, String role, String content, String sources) {
        Message msg = new Message();
        msg.setConversationId(conversationId);
        msg.setRole(role);
        msg.setContent(content);
        msg.setSources(sources);
        msgRepo.save(msg);

        convRepo.findById(conversationId).ifPresent(conv -> {
            conv.setMessageCount(conv.getMessageCount() + 1);
            if (conv.getTitle() == null && "user".equals(role)) {
                String title = content.length() > 50 ? content.substring(0, 50) : content;
                conv.setTitle(title.replace('\n', ' '));
            }
            convRepo.save(conv);
        });

        return msg;
    }
}
