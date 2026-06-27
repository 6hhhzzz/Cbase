package com.kes.auth.repository;

import com.kes.auth.model.GroupAdmin;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.Optional;

public interface GroupAdminRepository extends JpaRepository<GroupAdmin, String> {

    List<GroupAdmin> findByGroupId(String groupId);

    Optional<GroupAdmin> findByGroupIdAndUserId(String groupId, String userId);

    boolean existsByGroupIdAndUserId(String groupId, String userId);

    void deleteByGroupIdAndUserId(String groupId, String userId);

    /** 查询用户管理的所有组 */
    @Query("SELECT ga.groupId FROM GroupAdmin ga WHERE ga.userId = :userId")
    List<String> findGroupIdsByUserId(String userId);
}
