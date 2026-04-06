# Shared Protocol — SDLC Agent Suite

> This file defines the shared vocabulary, data formats, status codes, and communication protocols
> used by ALL agents in the GenPlatform SDLC Agent Suite. Every agent embeds the applicable
> sections from this file into its own Layer 1 static constraints.

---

## A. Workspace Directory Convention

All agents read from and write to a canonical workspace rooted at:
```
project_workspace/{project_name}/
```

```
project_workspace/
└── {project_name}/
    ├── phase_status.md                    ← PM-owned tracking file
    ├── requirements/
    │   ├── requirements_spec.md           ← sub_agent_requirement_analyst output
    │   └── user_stories.md                ← sub_agent_requirement_analyst output
    ├── architecture/
    │   ├── architecture_design.md         ← sub_agent_system_architect output
    │   ├── module_design.md               ← sub_agent_system_architect output
    │   └── tech_stack.md                  ← sub_agent_system_architect output
    ├── development/
    │   ├── implementation_plan.md         ← sub_agent_software_developer output
    │   └── code_review_report.md          ← sub_agent_software_developer output
    ├── src/                               ← sub_agent_software_developer code output
    ├── testing/
    │   ├── test_plan.md                   ← sub_agent_test_engineer output
    │   ├── unit_test_report.md            ← sub_agent_test_engineer output
    │   ├── integration_test_report.md     ← sub_agent_test_engineer output
    │   └── e2e_test_report.md             ← sub_agent_test_engineer output
    └── deployment/
        ├── cicd_pipeline.md               ← sub_agent_devops_engineer output
        ├── deployment_plan.md             ← sub_agent_devops_engineer output
        └── deployment_report.md           ← sub_agent_devops_engineer output
```

**Rules:**
- Each sub-agent may ONLY write to its designated directory (see ownership table above).
- No sub-agent may modify files owned by another agent without explicit PM authorization.
- The PM may read any file in the workspace; it writes only `phase_status.md` and `delivery_report.md`.

---

## B. Mandatory Output File Header

**Every file written by any agent MUST begin with this header block. No exceptions.**

```xml
<file_header>
  <author_agent>{AGENT_ID}</author_agent>
  <timestamp>{ISO8601}</timestamp>
  <project_name>{PROJECT_NAME}</project_name>
  <version>{SEMVER}</version>
  <input_files>
    <file>{relative path of each input file consumed}</file>
  </input_files>
  <phase>{PHASE_ID}</phase>
  <status>DRAFT | APPROVED | REJECTED | SUPERSEDED</status>
</file_header>
```

**Version lifecycle:**
- Initial draft: `0.1.0`
- After PM gate PASS (approved): `1.0.0`
- After revision due to gate FAIL: increment MINOR (e.g., `0.2.0`)
- After PM re-approval of a revision: increment MAJOR (e.g., `2.0.0`)

**Status transitions (PM is sole authority to change status to APPROVED):**
```
DRAFT → APPROVED  (PM gate PASS)
DRAFT → REJECTED  (PM gate FAIL, no retry remaining)
APPROVED → SUPERSEDED  (file replaced by newer version)
```

---

## C. Phase Definitions

| Phase ID | Phase Name | Owner Agent | Invocation Group |
|----------|-----------|-------------|-----------------|
| PHASE_01 | REQUIREMENTS_ANALYSIS | sub_agent_requirement_analyst | GROUP_A |
| PHASE_02 | USER_STORY_BREAKDOWN | sub_agent_requirement_analyst | GROUP_A |
| PHASE_03 | ARCHITECTURE_SELECTION | sub_agent_system_architect | GROUP_B |
| PHASE_04 | MODULE_DESIGN | sub_agent_system_architect | GROUP_B |
| PHASE_05 | SOFTWARE_DEVELOPMENT | sub_agent_software_developer | GROUP_C |
| PHASE_06 | CODE_REVIEW | sub_agent_software_developer | GROUP_C |
| PHASE_07 | UNIT_TESTING | sub_agent_test_engineer | GROUP_D |
| PHASE_08 | INTEGRATION_TESTING | sub_agent_test_engineer | GROUP_D |
| PHASE_09 | E2E_TESTING | sub_agent_test_engineer | GROUP_D |
| PHASE_10 | CICD_SETUP | sub_agent_devops_engineer | GROUP_E |
| PHASE_11 | PRODUCTION_DEPLOYMENT | sub_agent_devops_engineer | GROUP_E |

**Invocation Group**: Phases in the same group are handled by the same agent invocation.
The PM invokes one agent per group and the gate review covers all group outputs collectively.

**Phase dependency chain (FULL_FLOW):**
```
GROUP_A → [gate] → GROUP_B → [gate] → GROUP_C → [gate] → GROUP_D → [gate] → GROUP_E → [gate] → DELIVERY
```

---

## D. Status Codes

```xml
<!-- Phase status values -->
PHASE_STATUS: PENDING | IN_PROGRESS | AWAITING_REVIEW | APPROVED | REJECTED | FAILED

<!-- Gate decision values -->
GATE_DECISION: PASS | FAIL | PASS_WITH_CONDITIONS

<!-- Individual file status values -->
FILE_STATUS: DRAFT | APPROVED | REJECTED | SUPERSEDED

<!-- Agent invocation result values -->
AGENT_RESULT: SUCCESS | PARTIAL_SUCCESS | FAILURE | BLOCKED

<!-- Finding severity levels -->
SEVERITY: CRITICAL | MAJOR | MINOR

<!-- Test result values -->
TEST_RESULT: PASS | FAIL | SKIP | BLOCKED
```

---

## E. Agent Invocation Protocol (PM → Sub-Agent)

### PM sends invocation:
```xml
<agent_invocation>
  <invocation_id>{UUID}</invocation_id>
  <target_agent>{AGENT_ID}</target_agent>
  <project_name>{PROJECT_NAME}</project_name>
  <phases>
    <phase>{PHASE_ID}</phase>
  </phases>
  <mode>FULL_FLOW | PARTIAL_FLOW</mode>
  <input_files>
    <file>{relative path}</file>
  </input_files>
  <expected_output_files>
    <file>{relative path}</file>
  </expected_output_files>
  <special_instructions>{optional free text}</special_instructions>
  <quality_thresholds>
    <threshold key="unit_test_pass_rate" value="0.80"/>
    <threshold key="integration_test_pass_rate" value="0.90"/>
  </quality_thresholds>
</agent_invocation>
```

### Sub-agent responds:
```xml
<agent_response>
  <invocation_id>{same UUID as invocation}</invocation_id>
  <agent_id>{AGENT_ID}</agent_id>
  <status>SUCCESS | PARTIAL_SUCCESS | FAILURE | BLOCKED</status>
  <output_files>
    <file path="{relative path}" status="WRITTEN | FAILED">{one-line summary of content}</file>
  </output_files>
  <blockers>
    <blocker>{description of what is missing or blocking, if status=BLOCKED or FAILURE}</blocker>
  </blockers>
  <notes>{optional additional information}</notes>
</agent_response>
```

---

## F. Gate Review Format

```xml
<gate_review>
  <review_id>GR-{PHASE_ID}-{ISO8601_timestamp}</review_id>
  <invocation_id>{UUID of the triggering invocation}</invocation_id>
  <phase_group>{GROUP_A | GROUP_B | GROUP_C | GROUP_D | GROUP_E}</phase_group>
  <reviewed_files>
    <file path="{relative path}" version="{SEMVER}"/>
  </reviewed_files>
  <decision>PASS | FAIL | PASS_WITH_CONDITIONS</decision>
  <findings>
    <finding id="FIND-{review_id}-001" severity="CRITICAL | MAJOR | MINOR">
      {Specific, actionable description of the finding}
    </finding>
  </findings>
  <conditions>
    <!-- Only present when decision=PASS_WITH_CONDITIONS -->
    <condition>{Description of condition that must be addressed in next phase}</condition>
  </conditions>
  <feedback_to_agent>
    <!-- Only present when decision=FAIL -->
    {Specific corrective instructions for the agent to re-execute}
  </feedback_to_agent>
  <timestamp>{ISO8601}</timestamp>
</gate_review>
```

---

## G. phase_status.md Schema

```xml
<phase_status>
  <project_name>{name}</project_name>
  <flow_mode>FULL_FLOW | PARTIAL_FLOW</flow_mode>
  <created_at>{ISO8601}</created_at>
  <last_updated>{ISO8601}</last_updated>

  <phases>
    <phase id="PHASE_01"
           name="REQUIREMENTS_ANALYSIS"
           agent="sub_agent_requirement_analyst"
           group="GROUP_A"
           status="PENDING | IN_PROGRESS | AWAITING_REVIEW | APPROVED | REJECTED | FAILED"
           start_time="{ISO8601}"
           end_time="{ISO8601}"
           gate_decision="PASS | FAIL | PASS_WITH_CONDITIONS | PENDING"
           retry_count="0"/>
    <phase id="PHASE_02" name="USER_STORY_BREAKDOWN" agent="sub_agent_requirement_analyst" group="GROUP_A" status="PENDING" gate_decision="PENDING" retry_count="0"/>
    <phase id="PHASE_03" name="ARCHITECTURE_SELECTION" agent="sub_agent_system_architect" group="GROUP_B" status="PENDING" gate_decision="PENDING" retry_count="0"/>
    <phase id="PHASE_04" name="MODULE_DESIGN" agent="sub_agent_system_architect" group="GROUP_B" status="PENDING" gate_decision="PENDING" retry_count="0"/>
    <phase id="PHASE_05" name="SOFTWARE_DEVELOPMENT" agent="sub_agent_software_developer" group="GROUP_C" status="PENDING" gate_decision="PENDING" retry_count="0"/>
    <phase id="PHASE_06" name="CODE_REVIEW" agent="sub_agent_software_developer" group="GROUP_C" status="PENDING" gate_decision="PENDING" retry_count="0"/>
    <phase id="PHASE_07" name="UNIT_TESTING" agent="sub_agent_test_engineer" group="GROUP_D" status="PENDING" gate_decision="PENDING" retry_count="0"/>
    <phase id="PHASE_08" name="INTEGRATION_TESTING" agent="sub_agent_test_engineer" group="GROUP_D" status="PENDING" gate_decision="PENDING" retry_count="0"/>
    <phase id="PHASE_09" name="E2E_TESTING" agent="sub_agent_test_engineer" group="GROUP_D" status="PENDING" gate_decision="PENDING" retry_count="0"/>
    <phase id="PHASE_10" name="CICD_SETUP" agent="sub_agent_devops_engineer" group="GROUP_E" status="PENDING" gate_decision="PENDING" retry_count="0"/>
    <phase id="PHASE_11" name="PRODUCTION_DEPLOYMENT" agent="sub_agent_devops_engineer" group="GROUP_E" status="PENDING" gate_decision="PENDING" retry_count="0"/>
  </phases>

  <current_active_group>{GROUP_A | GROUP_B | GROUP_C | GROUP_D | GROUP_E | NONE}</current_active_group>

  <gate_reviews>
    <!-- <gate_review> records appended here after each gate review -->
  </gate_reviews>

  <escalations>
    <!-- <escalation> records appended here when retry limit exceeded -->
  </escalations>
</phase_status>
```

---

## H. PM Escalation Record

Written to `project_workspace/{project_name}/pm_escalation_{PHASE_ID}_{timestamp}.md` when retry limit is exceeded:

```xml
<pm_escalation>
  <escalation_id>ESC-{PHASE_ID}-{timestamp}</escalation_id>
  <phase_group>{GROUP_ID}</phase_group>
  <total_attempts>{number}</total_attempts>
  <gate_review_history>
    <!-- All gate_review records for this phase group -->
  </gate_review_history>
  <last_agent_response>
    <!-- The most recent agent_response received -->
  </last_agent_response>
  <recommended_actions>
    <action>Review the specific CRITICAL findings listed in the gate review history</action>
    <action>Consider clarifying the requirements or architecture constraints</action>
    <action>Optionally restart the phase with revised instructions via PARTIAL_FLOW</action>
  </recommended_actions>
  <awaiting_human_instruction>true</awaiting_human_instruction>
</pm_escalation>
```

---

## I. ID Naming Conventions (All Agents)

| Artifact | Format | Example |
|---------|--------|---------|
| Functional requirement | `REQ-FUNC-NNN` | `REQ-FUNC-001` |
| Non-functional requirement | `REQ-NFUNC-NNN` | `REQ-NFUNC-003` |
| User story | `US-NNN` | `US-012` |
| Acceptance criterion | `AC-NNN-NN` | `AC-012-01` |
| Architecture decision record | `ADR-NNN` | `ADR-005` |
| Module | `MOD-NNN` | `MOD-002` |
| Interface contract | `IFC-NNN` | `IFC-002` |
| Unit test case | `TC-UNIT-NNN` | `TC-UNIT-007` |
| Integration test case | `TC-INT-NNN` | `TC-INT-003` |
| E2E test case | `TC-E2E-NNN` | `TC-E2E-001` |
| Deployment step | `DEPLOY-NNN` | `DEPLOY-004` |
| Gate review | `GR-{PHASE_ID}-{timestamp}` | `GR-PHASE_01-20260406T120000Z` |
| Gate finding | `FIND-{GR_ID}-NNN` | `FIND-GR-PHASE_01-...-001` |
| Escalation | `ESC-{PHASE_ID}-{timestamp}` | `ESC-PHASE_03-20260406T150000Z` |

---

## J. Gate Pass Criteria (PM Reference)

| Phase Group | PASS Criteria | FAIL Triggers (any one = FAIL) |
|-------------|--------------|-------------------------------|
| GROUP_A (PHASE_01-02) | All requirements trace to input text; all ACs use Given/When/Then; no invented requirements; no architecture decisions in output | Missing source traces; ACs not in G/W/T format; [INFERRED] items exceed 10% of total; architecture content found |
| GROUP_B (PHASE_03-04) | All REQ-FUNC-* covered by at least one module; no circular module dependencies; every ADR evaluates ≥2 options; all module interfaces are typed | Requirements not covered; circular deps detected; ADR with single option; untyped interface |
| GROUP_C (PHASE_05-06) | All MOD-* from module_design.md implemented; code_review_report has no CRITICAL findings; implementation order respects dependency graph | Unimplemented modules; CRITICAL severity findings in review; dependency order violation |
| GROUP_D (PHASE_07-09) | Unit pass rate ≥ 80%; integration pass rate ≥ 90%; all US-* have ≥1 test case; test count arithmetic consistent | Below pass rate thresholds; user stories without test cases; arithmetic inconsistency in metrics |
| GROUP_E (PHASE_10-11) | Every DEPLOY-* step has a corresponding rollback step; post-deployment verification checklist passes; deployment_report status = DEPLOYED_SUCCESSFULLY | Missing rollback steps; verification failures; deployment report status ≠ DEPLOYED_SUCCESSFULLY |

---

## K. Quality Thresholds (Defaults, PM-overridable)

| Metric | Default Threshold |
|--------|------------------|
| Unit test pass rate | ≥ 80% |
| Integration test pass rate | ≥ 90% |
| E2E critical path pass rate | 100% |
| Code review CRITICAL findings | 0 (zero tolerance) |
| Code review MAJOR findings | ≤ 3 (must be documented) |
| [INFERRED] requirements ratio | ≤ 10% of total requirements |
| ADR minimum options evaluated | ≥ 2 per decision |
