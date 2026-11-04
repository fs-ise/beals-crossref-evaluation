import asyncio

import flet as ft
import json
from search_query.exception import QuerySyntaxError

from search_query.parser import parse
from beals_crossref_evaluation import BEALSCrossref
from search_query.constants import Fields
from datetime import date
import time
from retrieval_estimation import basket_M, basket_S, basket_XS, basket_2XS
import math

scopes = {
    "M": basket_M,
    "S": basket_S,
    "XS": basket_XS,
    "2XS": basket_2XS
}


def format_api_filters(journals: set = None, start_date: date = None, end_date: date = None) -> str:
    """Format filters into string to append to API endpoint."""
    filters = []

    if journals:
        filters.extend(f"issn:{issn}" for issn in journals)

    if start_date:
        time_filter = f"from-pub-date:{start_date}"

        if end_date:
            time_filter += f",until-pub-date:{end_date}"

        filters.append(time_filter)

    if filters:
        return f"&filter={','.join(filters)}"

    return ""


def read_date(field):
    """Read and validate a date field."""
    field.error = None
    value = (field.value or "").strip()

    if not value:
        return None

    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except ValueError:
        field.error = "Enter a valid date as YYYY-MM-DD."
        return None


def main(page: ft.Page):
    page.title = "QuEALS Prototype"

    query_input_field = ft.TextField(label="Query", width=392)
    timer_status = ft.Text("0.0 s")
    yield_status = ft.Text()
    retrieval_status = ft.Text()

    progress_bar = ft.ProgressBar(value=0, width=392)
    remaining_status = ft.Text()

    doi_list = ft.ListView(
        height=250,
        spacing=4,
        padding=10,
    )

    start_date_field = ft.TextField(
        label="Start date (optional)",
        hint_text="YYYY-MM-DD",
        width=190,
    )

    end_date_field = ft.TextField(
        label="End date (optional)",
        hint_text="YYYY-MM-DD",
        width=190,
    )

    journal_choice = ft.Dropdown(
        label="Scope",
        value="global",
        width=190,
        options=[
            ft.DropdownOption(key="global", text="Global"),
            ft.DropdownOption(key="M", text="LitBasket M"),
            ft.DropdownOption(key="S", text="LitBasket S"),
            ft.DropdownOption(key="XS", text="LitBasket XS"),
            ft.DropdownOption(key="2XS", text="LitBasket 2XS (AIS Basket of Eight)"),
        ],
    )

    records = []

    def reset_status():
        yield_status.value = ""
        progress_bar.value = 0
        remaining_status.value = ""
        timer_status.value = f"0.0 s"
        retrieval_status.value = ""
        doi_list.controls.clear()
        download_button.disabled = True
        go_button.disabled = False
        page.update()

    # Start the prototype
    async def start():
        nonlocal records

        reset_status()
        go_button.disabled = True
        page.update()

        start_date = read_date(start_date_field)
        end_date = read_date(end_date_field)

        if start_date_field.error or end_date_field.error:
            reset_status()
            return

        user_query = query_input_field.value or ""

        # Query field should not be blank
        if not user_query.strip():
            query_input_field.error = "Blank query field."
            reset_status()
            return

        query_input_field.error = None

        yield_status.value = "Parsing query..."
        page.update()

        # Parse query string
        try:
            query_obj = parse(user_query)
            query_obj.field = Fields.TITLE
        except QuerySyntaxError:
            query_input_field.error = "Invalid query syntax."
            reset_status()
            return

        selected_scope = journal_choice.value
        api_filters = format_api_filters(scopes.get(selected_scope, None), start_date, end_date)

        yield_status.value = "Estimating yield..."
        page.update()

        beals = BEALSCrossref(query_obj, api_filters)

        estimated_total_yield = beals.estimate_total_yield()
        yield_status.value = f"Estimated records to retrieve: {estimated_total_yield}"

        # setup time + ((estimated total yield / Crossref per-request batch limit) * per-request processing time (including API response time))
        estimated_seconds = 8 + ((estimated_total_yield / 1000) * 3)

        started_at = time.perf_counter()

        work = asyncio.create_task(
            asyncio.to_thread(beals.run_beals)
        )

        try:
            while not work.done():
                # Periodically update page during run to display elapsed time, remaining time and progress bar
                elapsed = time.perf_counter() - started_at
                timer_status.value = f"{elapsed:.1f} s"

                progress_bar.value = (
                    min(elapsed / estimated_seconds, 0.99)
                    if estimated_seconds > 0
                    else None
                )

                remaining = max(0, math.ceil(estimated_seconds - elapsed))
                minutes, seconds = divmod(remaining, 60)
                remaining_status.value = (
                    f"Time left: {minutes}m {seconds:02d}s"
                    if remaining > 0
                    else "Taking longer than expected..."
                )

                page.update()
                await asyncio.sleep(0.1)

            records = await work
            dois = [entry.data.get("doi") for entry in records]
            progress_bar.value = 1.0
            remaining_status.value = "Run complete."
            elapsed = time.perf_counter() - started_at
            timer_status.value = f"{elapsed:.1f} s"
            retrieval_status.value = f"Final results: {len(records)}"

            doi_list.controls = [
                ft.Text(doi, selectable=True) for doi in dois
            ]
            download_button.disabled = False

        finally:
            go_button.disabled = False
            page.update()

    query_input_field.on_submit = start
    go_button = ft.Button(content="Go", on_click=start)

    async def download():
        if not records:
            return

        data = [record.data for record in records]
        result = json.dumps(data, ensure_ascii=False, indent=2)

        await ft.FilePicker().save_file(
            file_name="records.json",
            src_bytes=result.encode("utf-8"),
        )

    download_button = ft.Button(
        content="Save records",
        icon=ft.Icons.DOWNLOAD,
        on_click=download,
        disabled=True,
    )

    # Settings
    settings_card = ft.Container(
        width=440,
        padding=24,
        border_radius=16,
        content=ft.Column(
            spacing=16,
            controls=[
                ft.Text("Settings", size=22, weight=ft.FontWeight.BOLD),
                query_input_field,
                journal_choice,
                ft.Column(
                    spacing=8,
                    controls=[
                        ft.Row(
                            spacing=12,
                            controls=[
                                ft.Container(
                                    expand=True,
                                    content=start_date_field,
                                ),
                                ft.Container(
                                    expand=True,
                                    content=end_date_field,
                                ),
                            ],
                        ),
                    ],
                ),
                go_button,
            ],
        ),
    )

    # Retrieval progress
    progress_card = ft.Container(
        width=440,
        padding=24,
        border_radius=16,
        content=ft.Column(
            spacing=12,
            controls=[
                ft.Text("Retrieval progress", size=22, weight=ft.FontWeight.BOLD),
                yield_status,
                progress_bar,
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    wrap=False,
                    spacing=12,
                    controls=[
                        remaining_status,
                        timer_status,
                    ],
                ),
            ],
        ),
    )

    # Results
    results_card = ft.Container(
        width=440,
        padding=24,
        border_radius=16,
        content=ft.Column(
            spacing=12,
            controls=[
                ft.Text("Results", size=22, weight=ft.FontWeight.BOLD),
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    wrap=False,
                    spacing=12,
                    controls=[
                        ft.Container(content=retrieval_status, expand=True),
                        download_button,
                    ],
                ),
                doi_list,
            ],
        ),
    )

    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.padding = 24

    page.add(
        ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.START,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=24,
            controls=[
                settings_card,
                ft.Container(
                    content=ft.Column(
                        spacing=24,
                        controls=[
                            progress_card,
                            results_card,
                        ],
                    ),
                ),
            ],
        )
    )


if __name__ == "__main__":
    ft.run(main)