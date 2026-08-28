#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from colrev.packages.crossref.src import crossref_api

from search_query.query import Query
from search_query.parser import parse
from search_query.constants import Operators


api = crossref_api.CrossrefAPI(
    url="https://api.crossref.org/",
)


basket_2XS = {
    "0960-085X",
    "1476-9344",
    "1350-1917",
    "1365-2575",
    "1047-7047",
    "1526-5536",
    "1536-9323",
    "0268-3962",
    "1466-4437",
    "0742-1222",
    "0963-8687",
    "0276-7783"
}


basket_XS = {
    "0167-9236",
    "0378-7206",
    "1387-3326",
    "1572-9419",
    "1471-7727",
    "1529-3181",
    "0957-4174",
    "0197-2243",
    "1087-6537",
    "1532-0936"
}


basket_S = {
    "1047-7039",
    "1526-5455",
    "0950-7051",
    "2330-1643",
    "0164-1212",
    "1091-9392",
    "1532-7744",
    "0888-7985",
    "0268-4012",
    "1071-5819",
    "1095-9300",
    "0959-3845",
    "0306-4573",
    "1041-4347",
    "0011-7315",
    "1540-5915",
    "0001-0782"
}


basket_M = {
    "0905-0167",
    "1468-4527",
    "1468-4535",
    "0305-0483",
    "1097-198X",
    "0025-1909",
    "1526-5501",
    "1062-7375",
    "1533-7995",
    "1741-0398",
    "0887-4417",
    "1935-5688",
    "1935-5696",
    "1063-8016",
    "1533-8010",
    "1615-5262",
    "1615-5270",
    "1746-0972",
    "1746-0980",
    "1548-1115",
    "1548-1123",
    "1058-0530",
    "1617-9846",
    "0377-2217",
    "1091-9856",
    "1526-5528",
    "0747-5632",
    "0925-9724",
    "1573-7551",
    "0937-6429",
    "1449-8618",
    "1326-2238",
    "1046-8188"
}

def estimate_yield(query: Query, journals: set = None, time_filter: bool = False) -> tuple[int, Query]:
    """Estimate total retrieved results and return minimal query structure that is executed."""
    # Leaf query -> API keyword search
    if not query.operator:
        keywords = quote(query.value)

        filters = []

        if journals:
            filters.extend(f"issn:{issn}" for issn in journals)

        if time_filter:
            filters.append(f"from-pub-date:2025-01-01,until-pub-date:2025-12-31")


        api.url = (
            f"https://api.crossref.org/v1/works"
            f"?query.title={keywords}"
        )

        if filters:
            api.url += f"&filter={','.join(filters)}"

        hits = api.get_len_total()

        return hits, query

    results = [estimate_yield(child, journals, time_filter) for child in query.children]

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
    elif query.value == Operators.AND:
        return min(results, key=lambda result: result[0])

    else:
        raise ValueError("Operator not supported.")


test_queries = {
    # 'Jones2008': 'Giddens AND Information*',
    # 'Kappos2008': '("culture" OR "cultural") AND ("IS" OR "IT")',
    'Krogh2012': 'open source AND motivation',
    'HeKing2008': '"user participation" OR "user involvement" OR "user engagement"',
    #'MouCohenBhattacherjeeEtAl2022': '"Protection motivation" AND ("information security" OR "information systems")',
    #'SchermannDongusYettonEtAl2016': '("software" OR "information system" OR "information technology" OR "outsourcing") AND ("contract" OR "fixed price" OR "fixed-price" OR "time and materials" OR "cost plus")',
    #'Eisend2019': '("file sharing" OR "piracy" OR pirat*) AND ("digital" OR "software" OR "music" OR "movie")',
    #'MandrellaTrangKolbe2020': '("value cocreation" OR "relational value" OR "IT value") AND ("interorganizational" OR "interfirm" OR "collaborative network" OR "corporate network" OR "cluster" OR "alliance")',
    'OesterreichAntonTeuteberg2022': '(analytics OR "business intelligence") AND (performance OR value OR benefit OR advantage) AND (firm OR company OR organisation OR organization)',
    'RobertsJeyarajPullinEtAl2023': '("information systems" OR "information technology") AND ("assimilation" OR "routinization" OR "infusion" OR "management support" OR "performance")',
    'ZazaJosephArmstrong2022a': '("turnover" OR "turnover intention" OR "intention to leave" OR "intention to quit") AND ("information technology" OR "information systems" OR "IT" OR "IS") AND ("professionals" OR "workers" OR "employees" OR "personnel")',
    'ZazaJosephArmstrong2022b': '("meta-analysis" OR "meta analysis" OR "meta-analyses") AND ("turnover" OR "turnover intention" OR "intention to leave" OR "intention to quit")',
}

# Run evaluation
results = dict()
for query_id, query_str in test_queries.items():
    query = parse(query_str)

    xxs_yield = estimate_yield(query, basket_2XS)[0]

    xs_yield = estimate_yield(query, basket_XS)[0]
    cumulative_xs_yield = xxs_yield + xs_yield

    s_yield = estimate_yield(query, basket_S)[0]
    cumulative_s_yield = cumulative_xs_yield + s_yield

    m_yield = estimate_yield(query, basket_M)[0]
    cumulative_m_yield = cumulative_s_yield + m_yield

    xxs_yield_time = estimate_yield(query, basket_2XS, True)[0]

    xs_yield_time = estimate_yield(query, basket_XS, True)[0]
    cumulative_xs_yield_time = xxs_yield_time + xs_yield_time

    s_yield_time = estimate_yield(query, basket_S, True)[0]
    cumulative_s_yield_time = cumulative_xs_yield_time + s_yield_time

    m_yield_time = estimate_yield(query, basket_M, True)[0]
    cumulative_m_yield_time = cumulative_s_yield_time + m_yield_time

    global_yield, executed_query = estimate_yield(query)

    results[query_id] = {
        "query": query_str,
        "executed_query": executed_query.to_generic_string(),
        "yields": {
            "2xs": xxs_yield,
            "xs": cumulative_xs_yield,
            "s": cumulative_s_yield,
            "m": cumulative_m_yield,
            "2xs_time": xxs_yield_time,
            "xs_time": cumulative_xs_yield_time,
            "s_time": cumulative_s_yield_time,
            "m_time": cumulative_m_yield_time,
            "global": global_yield,
        },
    }

# Save results to file
result_dir = Path(__file__).resolve().parent
result_file = result_dir / "estimation_results.json"
with result_file.open("w", encoding="utf-8") as f:
    json.dump(results, f, indent=4, ensure_ascii=False)
