package com.kes.common.dto;

import java.util.Map;

public class ModelAssignmentRequest {
    private Map<String, String> assignments;  // purpose → modelId

    public Map<String, String> getAssignments() { return assignments; }
    public void setAssignments(Map<String, String> assignments) { this.assignments = assignments; }
}
