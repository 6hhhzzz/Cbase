package com.kes.auth.repository;

import com.kes.auth.model.KnowledgeBase;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface KnowledgeBaseRepository extends JpaRepository<KnowledgeBase, String> {

    /** 查询某个 Space 下的所有 KB */
    List<KnowledgeBase> findBySpaceId(String spaceId);

    /** 查询某个 Space 下未删除的 KB */
    List<KnowledgeBase> findBySpaceIdAndDeletedAtIsNull(String spaceId);

    /** 查询 Space 下 space_wide 可见且未删除的 KB ID（用于权限计算） */
    @Query("SELECT kb.id FROM KnowledgeBase kb WHERE kb.spaceId = :spaceId AND kb.visibility = 'space_wide' AND kb.deletedAt IS NULL")
    List<String> findSpaceWideKbIds(String spaceId);

    /** 查询 Space 下已软删除的 KB（回收站用） */
    List<KnowledgeBase> findBySpaceIdAndDeletedAtIsNotNull(String spaceId);
}
