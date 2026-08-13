#!/usr/bin/env python3
from __future__ import annotations

from colrev.packages.crossref.src import crossref_api

from search_query.query import Query
from search_query.parser import parse
from search_query.constants import Operators

api = crossref_api.CrossrefAPI(
    url="https://api.crossref.org/"
)

def estimate_yield(query: Query) -> tuple[int, Query]:
    """Estimate total retrieved results and return minimal query structure that is executed."""
    # Leaf query -> API keyword search
    if not query.operator:
        keywords = query.value.strip('"')
        api.url = "https://api.crossref.org/v1/works?query.title=" + keywords
        return api.get_len_total(), query

    results = [estimate_yield(child) for child in query.children]

    # Every OR branch is executed
    if query.value == Operators.OR:
        total = sum(count for count, _ in results)

        executed_query = Query.create(
            operator=True,
            value=Operators.OR,
            children=[subquery for _, subquery in results]
        )

        return total, executed_query

    # Only the lowest-yielding AND branch is executed
    if query.value == Operators.AND:
        return min(results, key=lambda result: result[0])

# Example usage
query = parse("(strategy OR strategic) AND (technology OR digital)")
total_yield, smallest_block = estimate_yield(query)
print(total_yield)
print(smallest_block.to_string())
