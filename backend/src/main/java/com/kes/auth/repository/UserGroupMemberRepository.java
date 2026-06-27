package com.kes.auth.repository;

import com.kes.auth.model.UserGroupMember;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface UserGroupMemberRepository extends JpaRepository<UserGroupMember, String> {

    /** 查询用户所属的所有组 ID（直接归属，不含嵌套） */
    @Query("SELECT m.groupId FROM UserGroupMember m WHERE m.userId = :userId")
    List<String> findGroupIdsByUserId(String userId);

    /** 查询组内所有成员 */
    List<UserGroupMember> findByGroupId(String groupId);

    /** 查询用户是否是某个组的成员 */
    boolean existsByGroupIdAndUserId(String groupId, String userId);

    /** 移除组成员 */
    void deleteByGroupIdAndUserId(String groupId, String userId);

    /** 统计组成员数量 */
    long countByGroupId(String groupId);
}
