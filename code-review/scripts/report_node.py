from pathlib import Path


def format_list(items):
    if not items:
        return "- 无"
    return "\n".join(f"- {x}" for x in items)


def format_findings(findings):
    if not findings:
        return "## 4. Findings\n\n- 未发现明确问题。\n"

    chunks = ["## 4. Findings\n"]
    for idx, item in enumerate(findings, 1):
        chunks.append(f"### {idx}. [{item.get('severity', 'unknown')}] {item.get('title', '')}")
        chunks.append(f"- Category: {item.get('category', '')}")
        chunks.append(f"- File: {item.get('file', '')}")
        chunks.append(f"- Evidence: {item.get('evidence', '')}")
        chunks.append(f"- Impact: {item.get('impact', '')}")
        chunks.append(f"- Recommendation: {item.get('recommendation', '')}")
        chunks.append(f"- Needs Manual Confirmation: {item.get('needs_manual_confirmation', False)}")
        chunks.append("")
    return "\n".join(chunks)


def main(inputs: dict) -> dict:
    task = inputs["task"]
    requirement_summary = inputs["requirement_summary"]
    diff_result = inputs["diff_result"]
    review_result = inputs["review_result"]

    report = f"""# Code Review Report

## 1. Basic Info
- Repository Path: {task.get("repo_path", "")}
- Target Branch: {task.get("target_branch", "")}
- Source Branch: {task.get("source_branch", "")}
- DevOps URL: {task.get("devops_url", "")}

## 2. Requirement Summary
- Title: {requirement_summary.get("title", "")}
- Main Source: {requirement_summary.get("main_source", "")}
- Summary: {requirement_summary.get("summary", "")}

### Business Goals
{format_list(requirement_summary.get("business_goal", []))}

### Acceptance Criteria
{format_list(requirement_summary.get("acceptance_criteria", []))}

### Out of Scope
{format_list(requirement_summary.get("out_of_scope", []))}

### Risk Points
{format_list(requirement_summary.get("risk_points", []))}

### Unclear Points
{format_list(requirement_summary.get("unclear_points", []))}

## 3. Overall Decision
- Decision: {review_result.get("overall_decision", "")}
- Summary: {review_result.get("summary", "")}

{format_findings(review_result.get("findings", []))}

## 5. Coverage Assessment

### Covered
{format_list(review_result.get("coverage_assessment", {}).get("covered", []))}

### Possibly Missing
{format_list(review_result.get("coverage_assessment", {}).get("possibly_missing", []))}

### Unclear Points
{format_list(review_result.get("coverage_assessment", {}).get("unclear_points", []))}

## 6. Change Summary
{format_list(diff_result.get("change_summary", []))}

## 7. Commits
{format_list(diff_result.get("commit_list", []))}
"""

    output_path = task["output_path"]
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(report, encoding="utf-8")

    return {
        "report_path": output_path,
        "report_markdown": report
    }