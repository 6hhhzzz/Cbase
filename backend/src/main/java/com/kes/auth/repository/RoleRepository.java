package com.kes.auth.repository;

import com.kes.auth.model.Role;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RoleRepository extends JpaRepository<Role, String> {

    /** 按名称精确查找 */
    Role findByName(String name);
}
