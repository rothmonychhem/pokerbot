#!/usr/bin/env python3
"""Append a lightweight epic implementation check-in from a BMad story file."""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path


STATUS_RE = re.compile(r"^Status:\s*(?P<status>\S+)", re.IGNORECASE)
STORY_KEY_RE = re.compile(r"^(?P<epic>\d+)-(?P<story>\d+)-")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def story_key_from_path(path: Path) -> str:
    match = STORY_KEY_RE.match(path.name)
    if not match:
        raise ValueError(f"Cannot infer story key from {path}")
    return f"{match.group('epic')}-{match.group('story')}"


def epic_number_from_story_key(story_key: str) -> str:
    return story_key.split("-", 1)[0]


def extract_section_lines(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    in_section = False
    section_lines: list[str] = []

    for line in lines:
        if line.strip() == heading:
            in_section = True
            continue

        if in_section and line.startswith("### "):
            break

        if in_section:
            section_lines.append(line)

    return section_lines


def extract_bullets(text: str, heading: str) -> list[str]:
    bullets: list[str] = []
    for line in extract_section_lines(text, heading):
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets


def extract_status(text: str) -> str:
    for line in text.splitlines():
        match = STATUS_RE.match(line)
        if match:
            return match.group("status")
    return "unknown"


def parse_development_status(text: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    in_status = False

    for line in text.splitlines():
        if line.strip() == "development_status:":
            in_status = True
            continue

        if in_status and line and not line.startswith(" "):
            break

        if not in_status:
            continue

        match = re.match(r"^\s{2}([^:#]+):\s*(\S+)\s*$", line)
        if match:
            statuses[match.group(1).strip()] = match.group(2).strip()

    return statuses


def epic_progress(statuses: dict[str, str], epic_number: str) -> tuple[int, int, int, str, str]:
    epic_key = f"epic-{epic_number}"
    prefix = f"{epic_number}-"
    story_items = {
        key: value
        for key, value in statuses.items()
        if key.startswith(prefix) and not key.endswith("-retrospective")
    }

    total = len(story_items)
    done = sum(1 for value in story_items.values() if value == "done")
    remaining = total - done
    next_story = next((key for key, value in story_items.items() if value != "done"), "none")
    return done, total, remaining, statuses.get(epic_key, "unknown"), next_story


def summarize_completion(notes: list[str], fallback: str | None) -> str:
    if fallback:
        return fallback.strip()
    if not notes:
        return "No completion notes found."
    return notes[0]


def build_checkin(
    story_path: Path,
    sprint_status_path: Path,
    summary: str | None,
    now: datetime,
) -> tuple[str, str, str]:
    story_text = read_text(story_path)
    sprint_text = read_text(sprint_status_path)

    story_key = story_key_from_path(story_path)
    epic_number = epic_number_from_story_key(story_key)
    status = extract_status(story_text)
    notes = extract_bullets(story_text, "### Completion Notes List")
    debug_logs = extract_bullets(story_text, "### Debug Log References")
    statuses = parse_development_status(sprint_text)
    done, total, remaining, epic_status, next_story = epic_progress(statuses, epic_number)

    shipped = summarize_completion(notes, summary)
    tests = "; ".join(debug_logs[-4:]) if debug_logs else "No debug log references found."
    timestamp = now.strftime("%Y-%m-%d %H:%M")

    block = "\n".join(
        [
            f"## {timestamp} - story {story_key}",
            "",
            f"- Outcome: {status}",
            f"- Shipped: {shipped}",
            f"- Tests: {tests}",
            f"- Epic: {done}/{total} stories done; {remaining} remaining; status `{epic_status}`.",
            f"- Next: {next_story}",
            "",
        ]
    )
    return story_key, epic_number, block


def append_checkin(output_path: Path, story_key: str, block: str, force: bool) -> None:
    existing = read_text(output_path) if output_path.exists() else ""
    marker = f"- story {story_key}"

    if marker in existing and not force:
        raise ValueError(
            f"{output_path} already contains a check-in for story {story_key}. "
            "Use --force to append another one."
        )

    if not existing:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        title = f"# Epic {story_key.split('-', 1)[0]} implementation check-ins\n\n"
        output_path.write_text(title + block, encoding="utf-8")
        return

    separator = "" if existing.endswith("\n") else "\n"
    output_path.write_text(existing + separator + block, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Append a persistent BMad epic check-in from a story artifact."
    )
    parser.add_argument("--story", required=True, type=Path, help="Story markdown file.")
    parser.add_argument(
        "--sprint-status",
        default=Path("_bmad-output/implementation-artifacts/sprint-status.yaml"),
        type=Path,
        help="Sprint status YAML file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Check-ins markdown file. Defaults to epic-N-checkins.md beside sprint status.",
    )
    parser.add_argument("--summary", help="Override the shipped summary line.")
    parser.add_argument("--dry-run", action="store_true", help="Print the block without writing.")
    parser.add_argument("--force", action="store_true", help="Allow duplicate story check-ins.")
    args = parser.parse_args()

    story_path = args.story
    sprint_status_path = args.sprint_status
    if not story_path.exists():
        raise FileNotFoundError(story_path)
    if not sprint_status_path.exists():
        raise FileNotFoundError(sprint_status_path)

    story_key, epic_number, block = build_checkin(
        story_path=story_path,
        sprint_status_path=sprint_status_path,
        summary=args.summary,
        now=datetime.now(),
    )
    output_path = args.output or sprint_status_path.parent / f"epic-{epic_number}-checkins.md"

    if args.dry_run:
        print(block, end="")
        return 0

    append_checkin(output_path, story_key, block, args.force)
    print(f"Appended story {story_key} check-in to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
