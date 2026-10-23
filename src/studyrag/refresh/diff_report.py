"""A readable diff report for whichever pages changed, not just a bare
list of page numbers -- someone deciding whether a change matters needs
to see the actual wording.
"""

from __future__ import annotations

import difflib


def changed_page_numbers(old_hashes: list[str], new_hashes: list[str]) -> list[int]:
    """1-indexed page numbers where the hash differs, including pages
    added or removed at the end (a shorter/longer hash list on either
    side still counts every page past the shared length as changed).
    """
    n = max(len(old_hashes), len(new_hashes))
    changed = []
    for i in range(n):
        old = old_hashes[i] if i < len(old_hashes) else None
        new = new_hashes[i] if i < len(new_hashes) else None
        if old != new:
            changed.append(i + 1)
    return changed


def build_diff_report(
    source_id: str,
    old_pages: list[str],
    new_pages: list[str],
    changed_pages: list[int],
    retrieved_at_old: str,
    retrieved_at_new: str,
) -> str:
    """Markdown report: one unified diff per changed page. A page that
    only exists on one side (added/removed) is shown as a whole-page
    addition/removal rather than a diff against nothing.
    """
    lines = [
        f"# Change report: {source_id}",
        "",
        f"Previous version retrieved: {retrieved_at_old}",
        f"New version retrieved: {retrieved_at_new}",
        f"Pages changed: {len(changed_pages)} of {max(len(old_pages), len(new_pages))}",
        "",
    ]

    for page_num in changed_pages:
        old_text = old_pages[page_num - 1] if page_num - 1 < len(old_pages) else ""
        new_text = new_pages[page_num - 1] if page_num - 1 < len(new_pages) else ""

        lines.append(f"## Page {page_num}")
        lines.append("")
        if not old_text:
            lines.append("_Page added in the new version._")
            lines.append("")
            lines.append("```")
            lines.append(new_text)
            lines.append("```")
        elif not new_text:
            lines.append("_Page removed in the new version._")
            lines.append("")
            lines.append("```")
            lines.append(old_text)
            lines.append("```")
        else:
            diff = difflib.unified_diff(
                old_text.splitlines(),
                new_text.splitlines(),
                fromfile="old",
                tofile="new",
                lineterm="",
            )
            lines.append("```diff")
            lines.extend(diff)
            lines.append("```")
        lines.append("")

    return "\n".join(lines)
