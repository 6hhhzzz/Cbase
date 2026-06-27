package com.kes.conversation.repository;

import com.kes.conversation.model.Conversation;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface ConversationRepository extends JpaRepository<Conversation, String> {

    /** 按用户查询所有对话 */
    List<Conversation> findByUserIdOrderByUpdatedAtDesc(String userId);

    /** v3: 按用户 + KB 查询 */
    List<Conversation> findByUserIdAndKbIdOrderByUpdatedAtDesc(String userId, String kbId);

    /** v3.1: 按用户 + Space 查询（跨KB联合查询） */
    List<Conversation> findByUserIdAndSpaceIdOrderByUpdatedAtDesc(String userId, String spaceId);
}
