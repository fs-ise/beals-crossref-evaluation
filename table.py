from __future__ import annotations

import json
from pathlib import Path


INPUT_FILE = Path("estimation_results.json")
OUTPUT_FILE = Path("yields_table.md")

GROUPS = ["2xs", "xs", "s", "m", "global"]


def load_data(filename: Path) -> dict:
    with filename.open(encoding="utf-8") as file:
        return json.load(file)


def escape_markdown(value: str) -> str:
    """Escape characters that would break a Markdown table."""
    return str(value).replace("|", r"\|").replace("\n", " ")


def format_number(value: int | float | None) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    return f"{int(value):,}"


def create_table(data: dict, filename: Path) -> None:
    # Sort paper columns by global yield, ascending.
    paper_ids = sorted(
        data.keys(),
        key=lambda paper_id: data[paper_id].get("yields", {}).get(
            "global",
            float("inf"),
        ),
    )

    lines = [
        "| Metric | "
        + " | ".join(f"`{escape_markdown(paper_id)}`" for paper_id in paper_ids)
        + " |",
        "| --- | " + " | ".join(["---"] * len(paper_ids)) + " |",
    ]

    # Yields
    for group in GROUPS:
        values = [
            format_number(data[paper_id].get("yields", {}).get(group))
            for paper_id in paper_ids
        ]
        lines.append(f"| {group} | " + " | ".join(values) + " |")

    filename.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    data = load_data(INPUT_FILE)
    create_table(data, OUTPUT_FILE)
    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()