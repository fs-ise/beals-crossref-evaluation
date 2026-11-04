#!/usr/bin/env python3
"""BEALS prototype for Crossref"""
from __future__ import annotations

import datetime
import logging
import re
import typing
from urllib.parse import quote

from colrev.packages.crossref.src import crossref_api
from colrev.record.record import Record

from search_query import AndQuery
from search_query import OrQuery
from search_query.constants import Operators
from search_query.query import Query
from search_query.query import SearchField


# pylint: disable=too-many-instance-attributes
class BEALSCrossref:
    """
    BEALS prototype for Crossref
    """

    _api_url = "https://api.crossref.org/v1/"

    def __init__(self, query: Query, api_filters: str = None) -> None:
        self.value: str = query.value
        self.operator: bool = query.operator
        self.search_field: typing.Optional[SearchField] = query.field
        self.children: typing.List[BEALSCrossref] = [
            BEALSCrossref(child, api_filters) for child in query.children
        ]
        self.records: typing.List[Record] = []

        self.api = crossref_api.CrossrefAPI(url="https://api.crossref.org/")
        self.api_filters = api_filters

        self.logger = logging.getLogger(__name__)

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )

        self.path_length = -1

    def retrieve(self) -> typing.List[Record]:
        """Retrieve results from the API."""

        # build query url
        url = self.build_url(self.value)
        self.api.url = url

        num_res = self.api.get_len_total()

        # check the availability of the API
        self.api.check_availability()

        # retrieve records
        self.logger.info("Retrieve %d records", num_res)
        estimated_time = num_res * 0.007 + 5
        estimated_time_formatted = str(datetime.timedelta(seconds=int(estimated_time)))
        self.logger.info("Estimated time: %s", estimated_time_formatted)
        prep_records = list(self.api.get_records())
        records = self._filter_records_by_term(term=self.value, record_list=prep_records)
        self.logger.info("Finished and retrieved %d records.", len(records))

        return records


    def estimate_total_yield(self) -> int:
        """Estimate and return total yield of the query."""
        # Leaf query -> API keyword search
        if not self.operator:
            self.api.url = self.build_url(self.value)

            hits = self.api.get_len_total()

            return hits

        query_yields = [child.estimate_total_yield() for child in self.children]

        # Every OR branch is executed
        if self.value == Operators.OR:
            return sum(query_yields)

        # Only the lowest-yielding AND branch is executed
        elif self.value == Operators.AND:
            return min(query_yields)

        else:
            raise ValueError("Operator not supported.")

    
    def build_url(self, query: str) -> str:
        """Build query url."""

        keywords = quote(query)
        url = (
            f"https://api.crossref.org/v1/works"
            f"?query.title={keywords}"
        )

        if self.api_filters:
            url += self.api_filters

        # Add time range filter
        # filter_date = "filter=from-pub-date:2015-01-01"
        # url = self._api_url + "works?" + "query.title=%22" + query + "%22" + "&" + filter_date

        # Add journal filter
        # filter = "filter=issn:0167-9236,issn:0960-085X"
        # url = self._api_url + "works?" + filter + "&" + "query.title=%22" + query + "%22"

        # URL with journal endpoint
        # url = (
        # self._api_url
        
        # Journal of strategic Information systems
        # + "journals/0963-8687/works?"

        # + "query.title=%22"
        # + query
        # + "%22"

        # Only DOI and title are needed for evaluation
        # + "&select=DOI,title"
        # )

        return url

    def run_beals(self) -> typing.List[Record]:
        """Start BEALS."""

        # base case: call self.retrieve if the query is a simple term
        if not self.operator:
            # assign the results to self.records
            self.records = self.retrieve()

        else:
            # recursive cases
            # call APIXY(x).run_beals() for x in children and combine the results
            if self.value == "AND":
                next_child = self.select_child_with_lowest_yield()
                self.records = next_child.run_beals()

                for c in self.children:
                    if c != next_child:
                        self.records = c.filter_records(self.records)

            elif self.value == "OR":
                for child in self.children:
                    child.run_beals()

                for child in self.children:
                    self.records.extend(child.records)
            else:
                # NotQuery is not implemented
                raise ValueError("Operator is not yet supported.")

        self._remove_duplicates()
        return self.records

    # pylint: disable=inconsistent-return-statements
    def select_child_with_lowest_yield(self) -> BEALSCrossref:
        """Estimate lowest yield."""

        if not self.operator:
            self.api.url = self.build_url(self.value)
            self.path_length = self.api.get_len_total()
            return self

        else:
            if len(self.children) == 0:
                raise ValueError("AndQuery must have at least one child.")

            if self.value == "AND":
                for child in self.children:
                    child.select_child_with_lowest_yield()

                self.path_length = min(
                    child.path_length for child in self.children
                )

            elif self.value == "OR":
                for child in self.children:
                    child.select_child_with_lowest_yield()

                self.path_length = sum(
                    child.path_length for child in self.children
                )

            else:
                # NotQuery is not implemented
                raise ValueError("Operator is not yet supported.")

            min_len = self.children[0].path_length
            min_len_child = self.children[0]

            for child in self.children:
                if min_len > child.path_length:
                    min_len = child.path_length
                    min_len_child = child

            return min_len_child

    def _filter_records_by_term(
        self, term: str, record_list: typing.List[Record]
    ) -> typing.List[Record]:
        """Searches the title of a record for the search term."""

        rec_list = []

        term = term.strip().strip('"').strip()

        for record in record_list:
            if record.data.get("title"):
                if re.search(f"(^|[^a-zA-Z]){term.lower()}([^a-zA-Z]|$)",
                             record.data.get("title").lower(),
                             re.IGNORECASE) is not None:
                    rec_list.append(record)

        return rec_list

    def filter_records(
        self, parent_records: typing.List[Record]
    ) -> typing.List[Record]:
        """Filter record list for AND or OR subquery."""

        if self.operator:
            if self.value == "AND":
                self.records = self._and_filter(parent_records)

            elif self.value == "OR":
                self.records = self._or_filter(parent_records)

            else:
                # NotQuery is not implemented
                raise ValueError("Operator is not yet supported.")

        else:
            self.records = self._filter_records_by_term(self.value, parent_records)

        return self.records

    def _and_filter(self, records: typing.List[Record]) -> typing.List[Record]:
        """Filter record list for AND subqueries."""

        for c in self.children:
            if not c.operator:
                records = self._filter_records_by_term(c.value, records)

        for ch in self.children:
            if ch.operator:
                records = ch.filter_records(records)
        return records

    def _or_filter(self, records: typing.List[Record]) -> typing.List[Record]:
        """Filter record list for OR subqueries."""

        child_records = []
        for c in self.children:
            if not c.operator:
                child_records.extend(self._filter_records_by_term(c.value, records))
            else:
                child_records.extend(c.filter_records(records))

        return child_records

    def _remove_duplicates(self) -> None:
        """Remove dubplicates in record list."""

        # TODO: Use Bib-Dedupe in final implementation.

        no_duplicates = {}
        for record in self.records:
            no_duplicates[record.data.get("doi")] = record

        self.records = list(no_duplicates.values())

        no_dup = {}
        for record in self.records:
            no_dup[record.data.get("title").lower()] = record

        self.records = list(no_dup.values())


if __name__ == "__main__":
    # Use Case 1
    # (strategy OR strategic) AND (technology OR digital) 
    sub_search_query01 = OrQuery(["strategy", "strategic"], field="ti")
    sub_search_query02 = OrQuery(["technology", "digital"], field="ti")
    search_query_01 = AndQuery([sub_search_query01, sub_search_query02], field="ti")

    # Use Case 2
    # (("knowledge work" OR "digital labor" OR "services") AND ("platform" OR "market" OR "outsourcing")) OR "microsourcing"  
    sub_search_query03 = OrQuery(["knowledge work", "digital labor", "services"], field="ti")
    sub_search_query04 = OrQuery(["platform", "market", "outsourcing"], field="ti")
    sub_search_query05 = AndQuery([sub_search_query03, sub_search_query04], field="ti")
    search_query_02 = OrQuery([sub_search_query05, "microsourcing"], field="ti")

    # Use Case 2.1 refined query by including plural/ singular forms ("service", "platforms", "markets")
    # (("knowledge work" OR "digital labor" OR "services" OR "service") AND ("platform" OR "platforms" OR "market" OR "markets" OR "outsourcing")) OR "microsourcing"
    sub_search_query20 = OrQuery(["knowledge work", "digital labor", "service", "services"], field="ti")
    sub_search_query21 = OrQuery(["platform", "platforms", "market", "markets", "outsourcing"], field="ti")
    sub_search_query22 = AndQuery([sub_search_query20, sub_search_query21], field="ti")
    search_query_02_1 = OrQuery([sub_search_query22, "microsourcing"], field="ti")

    # Use Case 3
    # (“Artificial Intelligence” OR “substitution” OR “augmentation” OR “assemblage”) AND 
    # (“ethics” OR “transparency” OR “accountability” OR “privacy” OR “maleficence” OR “justice” OR “fairness” OR “beneficence” OR “sustainability” OR “responsibility” OR “autonomy”) AND
    # (“management” OR “strategy” OR “corporate strategy” OR “business strategy” OR “functional strategy” OR “planning processes” OR “strategic processes” OR “tactical processes” OR “operational processes”)
    sub_search_query06 = OrQuery(["Artificial Intelligence", "substitution", "augmentation", "assemblage"], field="ti")
    sub_search_query07 = OrQuery(["ethics", "transparency", "accountability", "privacy", "maleficence", "justice", 
                                "fairness", "beneficence", "sustainability", "responsibility", "autonomy"], field="ti")
    sub_search_query08 = OrQuery(["management", "strategy", "corporate strategy", "business strategy", 
                                "functional strategy", "planning processes", "strategic processes", 
                                "tactical processes", "operational processes"], field="ti")
    search_query_03 = AndQuery([sub_search_query06, sub_search_query07, sub_search_query08], field="ti")

    # Use Case 4
    # (("knowledge work" OR "digital labor" OR "services") AND (("platform" AND "market") OR "outsourcing")) OR "microsourcing"  
    sub_search_query09 = OrQuery(["knowledge work", "digital labor", "services"], field="ti")
    sub_search_query10 = AndQuery(["platform", "market"], field="ti")
    sub_search_query11 = OrQuery([sub_search_query10, "outsourcing"], field="ti")
    sub_search_query12 = AndQuery([sub_search_query09, sub_search_query11], field="ti")
    search_query_04 = OrQuery([sub_search_query12, "microsourcing"], field="ti")

    # Start BEALS
    beals = BEALSCrossref(search_query_01)
    beals.logger.info("Start BEALS")
    results = beals.run_beals()
    beals.logger.info("Finished. All records retrieved.")

    print(f"Final number of results: {len(results)}")

    for rec in results[:4]:
        print(f"\nDOI: {rec.data.get('doi')}\nTitle: {rec.data.get('title')}\n")
