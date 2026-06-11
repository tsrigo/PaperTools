"""Shared projections for data embedded into published webpages."""

from __future__ import annotations

from typing import Any


EMBEDDED_PAPER_FIELDS = (
    "title",
    "arxiv_id",
    "authors",
    "summary",
    "category",
    "cluster",
    "tags",
    "filter_reason",
    "intro_logic",
    "core_insight",
    "methodology",
    "additional_insights",
    "research_value",
    "research_value_source",
    "research_value_model",
    "research_value_reasoning_effort",
    "affiliations",
    "summary_translation",
)


def embedded_text_value(value: Any, default: str = "") -> str:
    """Return the string value the generated HTML embeds for scalar fields."""
    if value in (None, ""):
        return default
    return str(value)


def project_embedded_paper(paper: dict[str, Any]) -> dict[str, Any]:
    """Project a full paper payload to the first-screen HTML data shape."""
    projected: dict[str, Any] = {}
    for field in EMBEDDED_PAPER_FIELDS:
        if field == "tags":
            tags = paper.get("tags", [])
            projected[field] = tags if isinstance(tags, list) else tags
        elif field == "cluster":
            cluster = paper["cluster"] if "cluster" in paper else "Other"
            projected[field] = embedded_text_value(cluster)
        else:
            projected[field] = embedded_text_value(paper.get(field))
    return projected


def project_embedded_clusters(date_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Project a date payload's clusters to the first-screen HTML data shape."""
    clusters = date_payload.get("clusters")
    if not isinstance(clusters, list):
        return []

    projected_clusters: list[dict[str, Any]] = []
    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        papers = cluster.get("papers")
        paper_list = papers if isinstance(papers, list) else []
        projected_clusters.append(
            {
                "name": cluster.get("name"),
                "count": cluster.get("count"),
                "papers": [
                    project_embedded_paper(paper)
                    for paper in paper_list
                    if isinstance(paper, dict)
                ],
            }
        )
    return projected_clusters
