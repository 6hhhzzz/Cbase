package com.kes.auth.repository;

import com.kes.auth.model.UserGroup;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.Optional;

public interface UserGroupRepository extends JpaRepository<UserGroup, String> {

    /** 按名称查找组 */
    Optional<UserGroup> findByName(String name);

    /** 查询所有根组（无父组） */
    List<UserGroup> findByParentGroupIdIsNull();

    /** 查询指定父组下的子组 */
    List<UserGroup> findByParentGroupId(String parentGroupId);

    /** 查询父组 ID（用于层级展开） */
    @Query("SELECT g.parentGroupId FROM UserGroup g WHERE g.id = :groupId")
    Optional<String> findParentId(String groupId);

}
