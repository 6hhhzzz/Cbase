package com.kes.auth.repository;

import com.kes.auth.model.SpaceAdmin;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.Optional;

public interface SpaceAdminRepository extends JpaRepository<SpaceAdmin, String> {

    /** 查询 Space 的所有管理员 */
    List<SpaceAdmin> findBySpaceId(String spaceId);

    /** 查询用户在 Space 中的管理员身份 */
    Optional<SpaceAdmin> findBySpaceIdAndUserId(String spaceId, String userId);

    /** 判断用户是否是 Space 管理员 */
    boolean existsBySpaceIdAndUserId(String spaceId, String userId);

    /** 判断用户是否是 Space 的 owner */
    boolean existsBySpaceIdAndUserIdAndRole(String spaceId, String userId, String role);

    /** 查询用户管理的所有 Space */
    @Query("SELECT sa.spaceId FROM SpaceAdmin sa WHERE sa.userId = :userId")
    List<String> findSpaceIdsByUserId(String userId);

    /** 移除管理员 */
    void deleteBySpaceIdAndUserId(String spaceId, String userId);
}
