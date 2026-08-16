"""NOTES.md changelog helper. Newest entry at top."""

from datetime import datetime, timezone
from pathlib import Path

NOTES_FILE = Path(__file__).parent / "NOTES.md"
HEADER = "# Copytrade activity log\n\n_Auto-generated. Newest entry at top._\n"


def append_entry(title: str, lines: list[str]) -> None:
    now = datetime.now(timezone.utc)
    day_header = f"## {now:%Y-%m-%d}"
    block = f"### {now:%H:%M} UTC — {title}\n" + "".join(f"- {line}\n" for line in lines)

    text = NOTES_FILE.read_text() if NOTES_FILE.exists() else HEADER
    if not text.startswith(HEADER):
        text = HEADER + "\n" + text
    body = text[len(HEADER) :]

    if day_header in body:
        after_header = body.index(day_header) + len(day_header)
        insert_at = body.index("\n", after_header) + 1
        body = body[:insert_at] + "\n" + block + body[insert_at:]
    else:
        body = f"\n{day_header}\n\n" + block + body

    NOTES_FILE.write_text(HEADER + body)
