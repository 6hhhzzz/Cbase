package com.kes.auth.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "model_assignments")
public class ModelAssignmentEntity {

    @Id
    @Column(length = 36)
    private String id;

    @Column(nullable = false, length = 32, unique = true)
    private String purpose;  // "chat"|"rewrite"|"intent"|"embedding"|"reranker"|"rerank_llm"

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "model_id", nullable = true)
    private ModelConfigEntity model;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        if (updatedAt == null) updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    public ModelAssignmentEntity() {}

    public ModelAssignmentEntity(String id, String purpose, ModelConfigEntity model) {
        this.id = id;
        this.purpose = purpose;
        this.model = model;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getPurpose() { return purpose; }
    public void setPurpose(String purpose) { this.purpose = purpose; }
    public ModelConfigEntity getModel() { return model; }
    public void setModel(ModelConfigEntity model) { this.model = model; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
}
