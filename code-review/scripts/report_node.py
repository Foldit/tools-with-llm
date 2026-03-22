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
        evidence = item.get("evidence", {})
        if isinstance(evidence, dict):
            evidence_text = (
                f"{evidence.get('file', item.get('file', ''))}:{evidence.get('line', '')} | "
                f"{evidence.get('snippet', '')}"
            )
        else:
            evidence_text = str(evidence)

        chunks.append(f"### {idx}. [{item.get('severity', 'unknown')}] {item.get('title', '')}")
        chunks.append(f"- Category: {item.get('category', '')}")
        chunks.append(f"- File: {item.get('file', '')}")
        chunks.append(f"- Evidence: {evidence_text}")
        chunks.append(f"- Impact: {item.get('impact', '')}")
        chunks.append(f"- Recommendation: {item.get('recommendation', '')}")
        chunks.append(f"- Needs Manual Confirmation: {item.get('needs_manual_confirmation', False)}")
        chunks.append("")
    return "\n".join(chunks)


def format_context_files(files):
    if not files:
        return "- 无"

    lines = []
    for item in files:
        omitted_ranges = item.get("omitted_ranges", [])
        omitted_text = (
            ", ".join(f"{start}-{end}" for start, end in omitted_ranges)
            if omitted_ranges else "none"
        )
        strategy_chain = " -> ".join(item.get("strategy_chain", [])) or "none"
        lines.append(
            f"- {item.get('file', '')} | strategy={item.get('context_strategy', '')} | "
            f"confidence={item.get('strategy_confidence', 0.0):.2f} | "
            f"fallback_reason={item.get('fallback_reason', 'none') or 'none'} | "
            f"hunks={item.get('hunk_count', 0)} | truncated={item.get('context_truncated', False)} | "
            f"omitted_ranges={omitted_text}"
        )
        lines.append(f"  strategy_chain: {strategy_chain}")

    return "\n".join(lines)


def format_manual_confirmation(findings):
    required = [item for item in findings if item.get("needs_manual_confirmation")]
    if not required:
        return "- 无"

    return "\n".join(
        f"- {item.get('title', '')} ({item.get('file', '')})"
        for item in required
    )


def format_ui_images(images):
    if not images:
        return "- 无"
    return "\n".join(
        f"- [{item.get('index', '')}] {item.get('source', '')} | detail={item.get('detail', 'auto')} | note={item.get('note', '')}"
        for item in images
    )


def main(inputs: dict) -> dict:
    task = inputs["task"]
    requirement_summary = inputs["requirement_summary"]
    diff_result = inputs["diff_result"]
    review_result = inputs["review_result"]
    context_bundle = inputs.get("context_bundle", {"files": [], "summary": {}})
    context_summary = context_bundle.get("summary", {})
    findings = review_result.get("findings", [])

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

### UI Design Inputs
- UI Image Count: {requirement_summary.get("ui_image_count", 0)}
{format_ui_images(requirement_summary.get("ui_images", []))}

## 3. Overall Decision
- Decision: {review_result.get("overall_decision", "")}
- Summary: {review_result.get("summary", "")}

{format_findings(findings)}

## 5. Coverage Assessment

### Covered
{format_list(review_result.get("coverage_assessment", {}).get("covered", []))}

### Possibly Missing
{format_list(review_result.get("coverage_assessment", {}).get("possibly_missing", []))}

### Unclear Points
{format_list(review_result.get("coverage_assessment", {}).get("unclear_points", []))}

## 6. Change Summary
{format_list(diff_result.get("change_summary", []))}

## 7. Context Summary

### Context Strategies
{format_context_files(context_bundle.get("files", []))}

### Skipped Context Files
{format_list([f"{item.get('file', '')}: {item.get('reason', '')}" for item in context_summary.get("skipped_files", [])])}

### Truncated Context Files
{format_list(context_summary.get("truncated_files", []))}

### Fallback Reason Counts
{format_list([f"{reason}: {count}" for reason, count in context_summary.get("fallback_reason_counts", {}).items()])}

## 8. Transparency

### Manual Confirmation Required
{format_manual_confirmation(findings)}

### Diff Warnings
{format_list(diff_result.get("warnings", []))}

### Context Warnings
{format_list(context_summary.get("warnings", []))}

### Review Warnings
{format_list(review_result.get("warnings", []))}

### Requirement Warnings
{format_list(requirement_summary.get("warnings", []))}

### Skipped Diff Files
{format_list(diff_result.get("skipped_files", []))}

## 9. Commits
{format_list(diff_result.get("commit_list", []))}
"""

    output_path = task["output_path"]
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(report, encoding="utf-8")

    return {
        "report_path": output_path,
        "report_markdown": report
    }