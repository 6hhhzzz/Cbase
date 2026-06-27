package com.kes.auth.repository;

import com.kes.auth.model.SpaceGroup;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface SpaceGroupRepository extends JpaRepository<SpaceGroup, String> {

    /** 查询 Space 的所有准入组 */
    List<SpaceGroup> findBySpaceId(String spaceId);

    /** 查询某个组被分配到了哪些 Space */
    List<SpaceGroup> findByGroupId(String groupId);

    /** 判断组是否已分配到 Space */
    boolean existsBySpaceIdAndGroupId(String spaceId, String groupId);

    /** 查询 Space 中所有组的 group_id 列表 */
    @Query("SELECT sg.groupId FROM SpaceGroup sg WHERE sg.spaceId = :spaceId")
    List<String> findGroupIdsBySpaceId(String spaceId);

    /** 移除准入组 */
    void deleteBySpaceIdAndGroupId(String spaceId, String groupId);
}
