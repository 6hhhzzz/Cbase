package com.kes.auth.repository;

import com.kes.auth.model.User;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;
import java.util.Optional;

/**
 * 用户 JPA Repository。
 */
public interface UserRepository extends JpaRepository<User, String> {
    Optional<User> findByUsername(String username);
    boolean existsByUsername(String username);
    /** 按用户名前缀模糊搜索（用于添加成员时查找用户） */
    List<User> findTop10ByUsernameStartingWith(String prefix);
}
