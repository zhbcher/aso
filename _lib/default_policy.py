"""state/evolution-policy.yaml — Evolution approval policy for ASO v2.

Defines which delta operations are auto-approved, require review, or are denied.
This file must not be modified by evolution itself.
"""

_default_policy = """# Evolution Policy — ASO v2
# NOT editable by evolution itself (protected in evolution-policy.yaml deny list)

policy:
  default: require_review

  by_operation_type:
    instruction_add:     auto_approve
    instruction_remove:  require_review
    instruction_modify:  require_review
    constraint_add:      auto_approve
    constraint_remove:   require_review
    constraint_modify:   require_review
    step_add:            require_review
    step_remove:         require_review
    step_modify:         require_review
    workflow_reorder:    require_review
    tool_call_add:       require_review
    tool_call_remove:    require_review
    tool_call_modify:    require_review

  by_risk:
    low:    auto_approve
    medium: require_review
    high:   require_review

  deny:
    operations:
      - tool_call_remove
    targets:
      - runtime
      - gateway
      - scheduler
      - kernel
      - openclaw.json
      - secret.json
      - AGENTS.md
      - SOUL.md
      - USER.md
      - MEMORY.md
      - evolution-policy.yaml
      - trace_schema.yaml

  compound_rules:
    - if:
        risk: low
        target: [planner, router]
        operation_type: [instruction_add, constraint_add]
      then: auto_approve
    - if:
        risk: high
        session_count: 0
      then: require_review
    - if:
        target: any
        consecutive_successes: ">= 3"
        risk: [low, medium]
      then: auto_approve
"""