package com.kes.auth.repository;

import com.kes.auth.model.Role;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface RoleRepository extends JpaRepository<Role, String> {

    /** 查询所有系统角色 */
    List<Role> findByIsSystemTrue();

    /** 查询所有非系统角色（用户自定义） */
    List<Role> findByIsSystemFalse();

    /** 按名称精确查找 */
    Role findByName(String name);
}
