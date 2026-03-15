import os
import re
import subprocess

from common import truncate_text

try:
    from tree_sitter import Language, Parser
    import tree_sitter_javascript
    import tree_sitter_typescript

    TREE_SITTER_AVAILABLE = True
except ImportError:
    Language = None
    Parser = None
    tree_sitter_javascript = None
    tree_sitter_typescript = None
    TREE_SITTER_AVAILABLE = False


SUPPORTED_SYMBOL_FILE_TYPES = {"js", "jsx", "ts", "tsx", "vue"}
AST_SUPPORTED_FILE_TYPES = {"js", "jsx", "ts", "tsx"}
CONTROL_FLOW_RE = re.compile(r"^(if|else|for|while|switch|catch|try|finally|do)\b")
DECLARATION_RE = re.compile(
    r"^(export\s+)?(default\s+)?(async\s+)?"
    r"(function|class|interface|type|enum)\b"
)
VARIABLE_SYMBOL_RE = re.compile(
    r"^(export\s+)?(const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(async\s+)?(function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)"
)
METHOD_RE = re.compile(
    r"^(async\s+)?(get\s+|set\s+)?[A-Za-z_$][\w$]*\s*\([^;=]*\)\s*\{?$"
)
SCRIPT_TAG_RE = re.compile(r"<script\b([^>]*)>", re.IGNORECASE)
SCRIPT_LANG_RE = re.compile(r"lang=[\"']([A-Za-z0-9_+-]+)[\"']", re.IGNORECASE)

AST_SYMBOL_NODE_TYPES = {
    "js": {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "method_definition",
        "arrow_function",
        "function_expression",
        "lexical_declaration",
        "variable_declaration",
        "variable_declarator"
    },
    "jsx": {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "method_definition",
        "arrow_function",
        "function_expression",
        "lexical_declaration",
        "variable_declaration",
        "variable_declarator"
    },
    "ts": {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "abstract_class_declaration",
        "method_definition",
        "arrow_function",
        "function_expression",
        "lexical_declaration",
        "variable_declaration",
        "variable_declarator",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration"
    },
    "tsx": {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "abstract_class_declaration",
        "method_definition",
        "arrow_function",
        "function_expression",
        "lexical_declaration",
        "variable_declaration",
        "variable_declarator",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration"
    }
}

PARSER_CACHE = {}


def read_text_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def read_git_file(repo_path: str, revision: str, file_path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "show", f"{revision}:{file_path}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True
        )
        return result.stdout
    except Exception:
        return ""


def create_tree_sitter_language(factory):
    if factory is None:
        return None

    try:
        return Language(factory())
    except TypeError:
        return factory()


def create_parser(language):
    try:
        return Parser(language)
    except TypeError:
        parser = Parser()
        try:
            parser.language = language
        except AttributeError:
            parser.set_language(language)
        return parser


def get_parser(file_type: str):
    if not TREE_SITTER_AVAILABLE:
        return None

    if file_type in PARSER_CACHE:
        return PARSER_CACHE[file_type]

    factory = None
    if file_type in {"js", "jsx"}:
        factory = getattr(tree_sitter_javascript, "language", None)
    elif file_type == "ts":
        factory = getattr(tree_sitter_typescript, "language_typescript", None)
    elif file_type == "tsx":
        factory = getattr(tree_sitter_typescript, "language_tsx", None)

    language = create_tree_sitter_language(factory)
    if language is None:
        PARSER_CACHE[file_type] = None
        return None

    parser = create_parser(language)
    PARSER_CACHE[file_type] = parser
    return parser


def detect_file_type(file_path: str) -> str:
    if file_path.endswith(".tsx"):
        return "tsx"
    if file_path.endswith(".ts"):
        return "ts"
    if file_path.endswith(".vue"):
        return "vue"
    if file_path.endswith(".jsx"):
        return "jsx"
    if file_path.endswith(".js"):
        return "js"
    return "other"


def detect_vue_script_type(tag_line: str) -> str:
    match = SCRIPT_TAG_RE.search(tag_line)
    if match is None:
        return "js"

    lang_match = SCRIPT_LANG_RE.search(match.group(1))
    if lang_match is None:
        return "js"

    lang = lang_match.group(1).lower()
    if lang in {"ts", "tsx", "js", "jsx"}:
        return lang
    return "js"


def extract_vue_script_blocks(lines: list[str]) -> list[dict]:
    blocks = []
    current_block = None

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if current_block is None and stripped.startswith("<script"):
            current_block = {
                "tag_start": line_number,
                "content_start": line_number + 1,
                "file_type": detect_vue_script_type(stripped)
            }
            continue

        if current_block is not None and stripped.startswith("</script"):
            blocks.append({
                **current_block,
                "content_end": line_number - 1,
                "tag_end": line_number
            })
            current_block = None

    if current_block is not None:
        blocks.append({
            **current_block,
            "content_end": len(lines),
            "tag_end": len(lines)
        })

    return blocks


def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []

    merged = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
            continue
        merged[-1][1] = max(merged[-1][1], end)

    return [(start, end) for start, end in merged]


def extract_node_label(source_bytes: bytes, node) -> str:
    snippet = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")
    first_line = snippet.strip().splitlines()[0] if snippet.strip() else node.type
    return first_line[:160]


def build_ast_symbol_blocks(lines: list[str], file_type: str, line_offset: int = 0) -> list[dict]:
    if file_type not in AST_SUPPORTED_FILE_TYPES:
        return []

    parser = get_parser(file_type)
    if parser is None:
        return []

    source_text = "\n".join(lines)
    if not source_text.strip():
        return []

    source_bytes = source_text.encode("utf-8")
    tree = parser.parse(source_bytes)
    stack = [tree.root_node]
    blocks = []
    node_types = AST_SYMBOL_NODE_TYPES[file_type]

    while stack:
        node = stack.pop()
        children = getattr(node, "children", [])
        if children:
            stack.extend(reversed(children))

        if node.type not in node_types:
            continue

        start = node.start_point[0] + 1 + line_offset
        end = max(start, node.end_point[0] + 1 + line_offset)
        blocks.append({
            "kind": "ast-symbol",
            "start": start,
            "end": end,
            "label": extract_node_label(source_bytes, node)
        })

    return blocks


def build_vue_ast_symbol_blocks(lines: list[str]) -> list[dict]:
    blocks = []
    for script_block in extract_vue_script_blocks(lines):
        content_start = script_block["content_start"]
        content_end = script_block["content_end"]
        if content_end < content_start:
            continue
        block_lines = lines[content_start - 1:content_end]
        blocks.extend(build_ast_symbol_blocks(block_lines, script_block["file_type"], content_start - 1))
    return blocks


def classify_symbol_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None
    if CONTROL_FLOW_RE.match(stripped):
        return None
    if DECLARATION_RE.match(stripped):
        return stripped
    if VARIABLE_SYMBOL_RE.match(stripped):
        return stripped
    if METHOD_RE.match(stripped) and not stripped.startswith(("return ", "import ")):
        return stripped
    return None


def build_symbol_blocks(lines: list[str], file_type: str) -> list[dict]:
    blocks = []
    stack = []
    pending_symbol = None
    pending_symbol_ttl = 0
    script_start = None

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()

        if file_type == "vue":
            if script_start is None and stripped.startswith("<script"):
                script_start = line_number
            elif script_start is not None and stripped.startswith("</script"):
                blocks.append({
                    "kind": "script",
                    "start": script_start,
                    "end": line_number,
                    "label": "<script>"
                })
                script_start = None

        symbol_label = classify_symbol_line(line)
        if symbol_label and "{" not in line:
            pending_symbol = {"start": line_number, "label": symbol_label}
            pending_symbol_ttl = 6

        open_count = line.count("{")
        close_count = line.count("}")

        for open_index in range(open_count):
            if open_index == 0:
                if symbol_label and "{" in line:
                    stack.append({
                        "kind": "symbol",
                        "start": line_number,
                        "label": symbol_label
                    })
                    pending_symbol = None
                    pending_symbol_ttl = 0
                elif pending_symbol is not None:
                    stack.append({
                        "kind": "symbol",
                        "start": pending_symbol["start"],
                        "label": pending_symbol["label"]
                    })
                    pending_symbol = None
                    pending_symbol_ttl = 0
                else:
                    stack.append({
                        "kind": "other",
                        "start": line_number,
                        "label": ""
                    })
            else:
                stack.append({
                    "kind": "other",
                    "start": line_number,
                    "label": ""
                })

        for _ in range(close_count):
            if not stack:
                break
            block = stack.pop()
            if block["kind"] in {"symbol", "script"}:
                blocks.append({
                    "kind": block["kind"],
                    "start": block["start"],
                    "end": line_number,
                    "label": block["label"]
                })

        if pending_symbol is not None:
            pending_symbol_ttl -= 1
            if pending_symbol_ttl <= 0 or stripped.endswith(";"):
                pending_symbol = None
                pending_symbol_ttl = 0

    return blocks


def pick_symbol_range(blocks: list[dict], target_line: int, max_symbol_context_lines: int) -> tuple[int, int] | None:
    candidates = []
    for block in blocks:
        if block["start"] <= target_line <= block["end"]:
            span = block["end"] - block["start"] + 1
            if span <= max_symbol_context_lines:
                candidates.append((span, block["start"], block["end"]))

    if not candidates:
        return None

    _, start, end = min(candidates, key=lambda item: item[0])
    return (start, end)


def build_context_ranges(hunks: list[dict], status: str, total_lines: int,
                         context_before: int, context_after: int) -> list[tuple[int, int]]:
    ranges = []
    use_old_lines = status.startswith("D")

    for hunk in hunks:
        start_line = hunk["old_start"] if use_old_lines else hunk["new_start"]
        line_count = hunk["old_count"] if use_old_lines else hunk["new_count"]
        effective_count = max(line_count, 1)
        start = max(1, start_line - context_before)
        end = min(total_lines, start_line + effective_count - 1 + context_after)
        ranges.append((start, end))

    return merge_ranges(ranges)


def build_symbol_context_ranges(lines: list[str], hunks: list[dict], status: str, file_type: str,
                                max_symbol_context_lines: int) -> tuple[list[tuple[int, int]], str | None]:
    if file_type not in SUPPORTED_SYMBOL_FILE_TYPES:
        return [], None

    use_old_lines = status.startswith("D")
    ast_blocks = build_vue_ast_symbol_blocks(lines) if file_type == "vue" else build_ast_symbol_blocks(lines, file_type)
    ast_ranges = []

    for hunk in hunks:
        target_line = hunk["old_start"] if use_old_lines else hunk["new_start"]
        symbol_range = pick_symbol_range(ast_blocks, target_line, max_symbol_context_lines)
        if symbol_range is not None:
            ast_ranges.append(symbol_range)

    if ast_ranges:
        return merge_ranges(ast_ranges), "symbol-ast"

    symbol_blocks = build_symbol_blocks(lines, file_type)
    heuristic_ranges = []

    for hunk in hunks:
        target_line = hunk["old_start"] if use_old_lines else hunk["new_start"]
        symbol_range = pick_symbol_range(symbol_blocks, target_line, max_symbol_context_lines)
        if symbol_range is not None:
            heuristic_ranges.append(symbol_range)

    if heuristic_ranges:
        return merge_ranges(heuristic_ranges), "symbol-heuristic"

    return [], None


def render_ranges(lines: list[str], ranges: list[tuple[int, int]], max_snippets: int) -> str:
    chunks = []
    selected_ranges = ranges[:max_snippets]

    for start, end in selected_ranges:
        chunks.append(f"@@ lines {start}-{end} @@")
        for line_number in range(start, end + 1):
            chunks.append(f"{line_number}: {lines[line_number - 1]}")

    if len(ranges) > len(selected_ranges):
        chunks.append(f"[TRUNCATED_RANGES] omitted={len(ranges) - len(selected_ranges)}")

    return "\n".join(chunks)


def build_file_context(repo_path: str, target_branch: str, source_branch: str, item: dict,
                       max_context_chars_per_file: int, context_before: int,
                       context_after: int, max_snippets_per_file: int,
                       max_symbol_context_lines: int,
                       warning_max_context_chars_per_file: int | None) -> tuple[str, str, bool, str | None]:
    rel_path = item["path"]
    status = item["status"]
    file_type = detect_file_type(rel_path)
    revision = target_branch if status.startswith("D") else source_branch
    content = read_git_file(repo_path, revision, rel_path)

    if not content and not status.startswith("D"):
        abs_path = os.path.join(repo_path, rel_path)
        content = read_text_file(abs_path)

    if not content:
        return "", "missing", False, f"missing_or_unreadable:{rel_path}"

    lines = content.splitlines()
    if not lines:
        return "", "empty", False, f"empty:{rel_path}"

    hunks = item.get("hunks", [])
    symbol_ranges, symbol_strategy = build_symbol_context_ranges(lines, hunks, status, file_type, max_symbol_context_lines)
    if symbol_ranges:
        ranges = symbol_ranges
        strategy = symbol_strategy
    else:
        ranges = build_context_ranges(hunks, status, len(lines), context_before, context_after)
        strategy = "hunk"

    if not ranges:
        ranges = [(1, min(len(lines), context_before + context_after + 1))]
        strategy = "fallback"

    rendered_snippet = render_ranges(lines, ranges, max_snippets_per_file)
    truncated = len(rendered_snippet) > max_context_chars_per_file
    warning = None
    if warning_max_context_chars_per_file and len(rendered_snippet) > warning_max_context_chars_per_file:
        warning = (
            f"context_warning:{rel_path}: rendered_context_chars={len(rendered_snippet)} > "
            f"warning_max_context_chars_per_file={warning_max_context_chars_per_file}"
        )

    return truncate_text(rendered_snippet, max_context_chars_per_file), strategy, truncated, warning


def main(inputs: dict) -> dict:
    task = inputs["task"]
    diff_result = inputs["diff_result"]
    repo_path = task["repo_path"]
    max_context_chars_per_file = inputs.get("max_context_chars_per_file", 8000)
    context_before = inputs.get("context_lines_before_hunk", 20)
    context_after = inputs.get("context_lines_after_hunk", 20)
    max_snippets_per_file = inputs.get("max_context_snippets_per_file", 6)
    max_symbol_context_lines = inputs.get("max_symbol_context_lines", 160)
    warning_max_context_chars_per_file = inputs.get("warning_max_context_chars_per_file")
    target_branch = task["target_branch"]
    source_branch = task["source_branch"]

    files = []
    skipped_files = []
    truncated_files = []
    warnings = []
    strategy_counts = {}

    for item in diff_result["changed_files"]:
        rel_path = item["path"]
        snippet, context_strategy, truncated, warning = build_file_context(
            repo_path,
            target_branch,
            source_branch,
            item,
            max_context_chars_per_file,
            context_before,
            context_after,
            max_snippets_per_file,
            max_symbol_context_lines,
            warning_max_context_chars_per_file
        )
        if not snippet:
            skipped_files.append({"file": rel_path, "reason": warning or context_strategy})
            continue

        if truncated:
            truncated_files.append(rel_path)
        if warning:
            warnings.append(warning)
        strategy_counts[context_strategy] = strategy_counts.get(context_strategy, 0) + 1

        files.append({
            "file": rel_path,
            "status": item["status"],
            "file_type": detect_file_type(rel_path),
            "hunk_count": len(item.get("hunks", [])),
            "context_strategy": context_strategy,
            "context_truncated": truncated,
            "snippet": snippet
        })

    return {
        "context_bundle": {
            "files": files,
            "summary": {
                "strategy_counts": strategy_counts,
                "skipped_files": skipped_files,
                "truncated_files": truncated_files,
                "warnings": warnings
            }
        }
    }