package com.kes.auth.repository;

import com.kes.auth.model.AccessControlEntry;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface AceRepository extends JpaRepository<AccessControlEntry, String> {

    /**
     * 查询 Space 中指定资源类型的所有 ACE 条目（用于构建 ACE 矩阵视图）。
     */
    @Query("SELECT ace FROM AccessControlEntry ace WHERE ace.spaceId = :spaceId AND ace.resourceType = :resourceType")
    List<AccessControlEntry> findBySpaceIdAndResourceType(String spaceId, String resourceType);

    /**
     * 查询某个 principal（组或用户）在 Space 中对所有 KB 的 ACE 条目。
     * 用于权限解析：获取用户的有效组在 Space 中的 KB 访问权。
     */
    @Query("SELECT ace FROM AccessControlEntry ace " +
           "WHERE ace.spaceId = :spaceId " +
           "  AND ace.resourceType = 'kb' " +
           "  AND ace.principalType = :principalType " +
           "  AND ace.principalId IN :principalIds")
    List<AccessControlEntry> findKbAcesByPrincipals(String spaceId, String principalType, List<String> principalIds);

    /**
     * 查询 Space 中某个 KB 的所有 ACE 条目。
     */
    List<AccessControlEntry> findBySpaceIdAndResourceTypeAndResourceId(
            String spaceId, String resourceType, String resourceId);

    /**
     * 检查是否存在指定的 ACE 条目（唯一约束校验）。
     */
    boolean existsBySpaceIdAndResourceTypeAndResourceIdAndPrincipalTypeAndPrincipalId(
            String spaceId, String resourceType, String resourceId,
            String principalType, String principalId);

    /**
     * 查询使用了指定角色的所有 ACE（角色变更/删除时检查引用）。
     */
    List<AccessControlEntry> findByRoleId(String roleId);

    /**
     * 删除 Space 中某个 KB 的所有 ACE（KB 永久删除时）。
     */
    void deleteBySpaceIdAndResourceTypeAndResourceId(String spaceId, String resourceType, String resourceId);

    /**
     * 查询 Space 中文档级别的 ACE（resource_type = 'document'）。
     * 用于文档级权限解析。
     */
    @Query("SELECT ace FROM AccessControlEntry ace " +
           "WHERE ace.spaceId = :spaceId " +
           "  AND ace.resourceType = 'document' " +
           "  AND ace.principalType = :principalType " +
           "  AND ace.principalId IN :principalIds")
    List<AccessControlEntry> findDocAcesByPrincipals(String spaceId, String principalType, List<String> principalIds);

    /**
     * 删除 Space 中某个主体（组/用户）的所有 ACE。
     * 用于准入组移除时级联清理。
     */
    @Modifying
    @Query("DELETE FROM AccessControlEntry ace " +
           "WHERE ace.spaceId = :spaceId " +
           "  AND ace.principalType = :principalType " +
           "  AND ace.principalId = :principalId")
    void deleteBySpaceIdAndPrincipal(String spaceId, String principalType, String principalId);

    /**
     * 删除某个资源（KB/文档）的所有 ACE。
     * 用于 KB 或文档永久删除时级联清理。
     */
    @Modifying
    @Query("DELETE FROM AccessControlEntry ace " +
           "WHERE ace.resourceType = :resourceType " +
           "  AND ace.resourceId = :resourceId")
    void deleteByResource(String resourceType, String resourceId);
}
