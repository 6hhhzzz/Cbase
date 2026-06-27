package com.kes.auth.repository;

import com.kes.auth.model.Space;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface SpaceRepository extends JpaRepository<Space, String> {

    /** 查询所有 Space — 用于 Space 选择页 */
    List<Space> findAllByOrderByNameAsc();

    /** 查询所有未删除的 Space（全局管理员视角） */
    @Query("SELECT s FROM Space s WHERE s.deletedAt IS NULL ORDER BY s.status ASC, s.name ASC")
    List<Space> findAllActive();
}
