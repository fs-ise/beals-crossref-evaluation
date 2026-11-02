import asyncio
import flet as ft
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

    query_input_field = ft.TextField(label="Query")
    timer_status = ft.Text()
    parse_status = ft.Text()
    yield_status = ft.Text()
    retrieval_status = ft.Text()

    progress_bar = ft.ProgressBar(value=0, width=400)
    remaining_status = ft.Text()

    start_date_field = ft.TextField(
        label="Start date (optional)",
        hint_text="YYYY-MM-DD",
    )

    end_date_field = ft.TextField(
        label="End date (optional)",
        hint_text="YYYY-MM-DD",
    )

    journal_choice = ft.RadioGroup(
        value="global",
        content=ft.Column(
            controls=[
                ft.Radio(value="global", label="Global scope"),
                ft.Radio(value="M", label="LitBasket M"),
                ft.Radio(value="S", label="LitBasket S"),
                ft.Radio(value="XS", label="LitBasket XS"),
                ft.Radio(value="2XS", label="LitBasket 2XS (AIS Basket of Eight)"),
            ]
        ),
    )

    # Start the prototype
    async def start():
        # Lock in go button and reset status values before a new run
        # TODO: implement termination button
        go_button.disabled = True
        parse_status.value = ""
        yield_status.value = ""
        progress_bar.value = 0
        remaining_status.value = ""
        timer_status.value = ""
        retrieval_status.value = ""
        page.update()

        start_date = read_date(start_date_field)
        end_date = read_date(end_date_field)

        if start_date_field.error or end_date_field.error:
            page.update()
            return

        user_query = query_input_field.value or ""

        # Query field should not be blank
        if not user_query.strip():
            query_input_field.error = "Blank query field."
            page.update()
            return

        query_input_field.error = None

        # Parse query string
        try:
            query_obj = parse(user_query)
            query_obj.field = Fields.TITLE
            parse_status.value = f"Parsed: {user_query}."
        except QuerySyntaxError:
            query_input_field.error = "Invalid query syntax."
            page.update()
            return

        selected_scope = journal_choice.value
        api_filters = format_api_filters(scopes.get(selected_scope, None), start_date, end_date)

        yield_status.value = "Estimating yield..."
        page.update()

        beals = BEALSCrossref(query_obj)
        beals.api_filters = api_filters

        estimated_total_yield = beals.estimate_total_yield()
        yield_status.value = f"Estimated records: {estimated_total_yield}"

        # TODO: Replace with exact API rate limits
        requests_per_second = 5
        records_per_request = 100

        estimated_requests = math.ceil(estimated_total_yield / records_per_request)
        estimated_seconds = estimated_requests / requests_per_second

        started_at = time.perf_counter()

        work = asyncio.create_task(
            asyncio.to_thread(beals.run_beals)
        )

        while not work.done():
            # Periodically update page during run to display elapsed time, remaining time and progress bar
            elapsed = time.perf_counter() - started_at
            timer_status.value = f"Elapsed: {elapsed:.1f} s"

            progress_bar.value = (
                min(elapsed / estimated_seconds, 0.99)
                if estimated_seconds > 0
                else None
            )

            remaining = max(0, math.ceil(estimated_seconds - elapsed))
            minutes, seconds = divmod(remaining, 60)
            remaining_status.value = (
                f"Estimated remaining: {minutes}m {seconds:02d}s"
                if remaining > 0
                else "Record retrieval is taking longer than estimated."
            )

            page.update()
            await asyncio.sleep(0.1)

        try:
            records = await work
            progress_bar.value = 1.0
            remaining_status.value = "Complete."
            elapsed = time.perf_counter() - started_at
            retrieval_status.value = f"Filtered records: {len(records)}"
            timer_status.value = f"Completed in: {elapsed:.1f} s"
        finally:
            go_button.disabled = False
            page.update()


    query_input_field.on_submit = start
    go_button = ft.Button(content="Go", on_click=start)

    page.add(
        query_input_field,
        journal_choice,
        start_date_field,
        end_date_field,
        go_button,
        parse_status,
        yield_status,
        progress_bar,
        remaining_status,
        timer_status,
        retrieval_status,
    )


if __name__ == "__main__":
    ft.run(main)