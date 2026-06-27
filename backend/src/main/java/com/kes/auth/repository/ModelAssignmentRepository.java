package com.kes.auth.repository;

import com.kes.auth.model.ModelAssignmentEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface ModelAssignmentRepository extends JpaRepository<ModelAssignmentEntity, String> {
    Optional<ModelAssignmentEntity> findByPurpose(String purpose);
}
