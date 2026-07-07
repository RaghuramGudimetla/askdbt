"""Parse dbt manifest.json (and optionally catalog.json) into model chunks."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ColumnInfo:
    name: str
    description: str
    data_type: str


@dataclass
class ModelChunk:
    """One chunk per dbt model — the unit that gets embedded."""

    model_id: str          # e.g. "model.banking.dim_customers"
    model_name: str        # e.g. "dim_customers"
    schema: str
    database: str
    description: str
    columns: list[ColumnInfo]
    tags: list[str]
    materialization: str
    owner: str
    refresh_frequency: str
    depends_on: list[str]
    child_ids: list[str]              # immediate downstream unique_ids (one hop)
    all_downstream_ids: list[str]     # transitive closure — every descendant unique_id
    file_path: str
    row_count: Optional[int] = None
    size_bytes: Optional[int] = None
    last_modified: Optional[str] = None
    raw_sql: Optional[str] = None
    compiled_sql: Optional[str] = None

    def to_text(self) -> str:
        """Render chunk as a flat prose string for embedding."""
        lines = [
            f"Model: {self.model_name}",
            f"Schema: {self.database}.{self.schema}",
            f"Materialization: {self.materialization}",
            f"Owner: {self.owner}",
            f"Refresh: {self.refresh_frequency}",
            f"Tags: {', '.join(self.tags) if self.tags else 'none'}",
            f"Description: {self.description}",
        ]
        if self.row_count is not None:
            lines.append(f"Row count: {self.row_count:,}")
        if self.size_bytes is not None:
            lines.append(f"Size: {self.size_bytes / 1_073_741_824:.2f} GB" if self.size_bytes >= 1_073_741_824 else f"Size: {self.size_bytes / 1_048_576:.1f} MB")
        if self.last_modified:
            lines.append(f"Last modified: {self.last_modified}")
        lines += ["", "Columns:"]
        for col in self.columns:
            col_line = f"  - {col.name} ({col.data_type}): {col.description}"
            lines.append(col_line)

        if self.depends_on:
            lines.append("")
            lines.append(f"Depends on: {', '.join(self.depends_on)}")

        if self.raw_sql:
            lines.append("")
            lines.append("SQL:")
            lines.append(self.raw_sql)

        return "\n".join(lines)

    def to_metadata(self) -> dict:
        return {
            "model_id": self.model_id,
            "model_name": self.model_name,
            "schema": self.schema,
            "database": self.database,
            "tags": self.tags,
            "materialization": self.materialization,
            "owner": self.owner,
        }


def _transitive_descendants(node_id: str, child_map: dict[str, list[str]]) -> list[str]:
    """BFS to compute every transitive downstream model unique_id."""
    visited: set[str] = set()
    queue: list[str] = list(child_map.get(node_id, []))
    while queue:
        n = queue.pop(0)
        if n in visited:
            continue
        visited.add(n)
        queue.extend(child_map.get(n, []))
    return [n for n in visited if n.startswith("model.")]


class ManifestParser:
    def __init__(self, manifest_path: str | Path, catalog_path: Optional[str | Path] = None):
        self.manifest_path = Path(manifest_path)
        self.catalog_path = Path(catalog_path) if catalog_path else None

    def parse(self) -> list[ModelChunk]:
        manifest = json.loads(self.manifest_path.read_text())
        catalog = {}
        if self.catalog_path and self.catalog_path.exists():
            catalog = json.loads(self.catalog_path.read_text())

        # Build child_map: unique_id → [child unique_ids] from manifest if present,
        # otherwise derive it by inverting depends_on across all model nodes.
        child_map: dict[str, list[str]] = manifest.get("child_map", {})
        if not child_map:
            for node_id, node in manifest.get("nodes", {}).items():
                if node.get("resource_type") != "model":
                    continue
                for parent in node.get("depends_on", {}).get("nodes", []):
                    child_map.setdefault(parent, []).append(node_id)

        chunks = []
        for node_id, node in manifest.get("nodes", {}).items():
            if node.get("resource_type") != "model":
                continue
            child_ids = [c for c in child_map.get(node_id, []) if c.startswith("model.")]
            all_downstream = _transitive_descendants(node_id, child_map)
            chunks.append(self._parse_node(node, catalog, child_ids, all_downstream))

        return chunks

    def _parse_node(
        self,
        node: dict,
        catalog: dict,
        child_ids: list[str] | None = None,
        all_downstream_ids: list[str] | None = None,
    ) -> ModelChunk:
        catalog_cols = {}
        if catalog:
            cat_node = catalog.get("nodes", {}).get(node["unique_id"], {})
            for col_name, col_data in cat_node.get("columns", {}).items():
                catalog_cols[col_name.lower()] = col_data

        manifest_cols = node.get("columns", {})
        columns = []
        if manifest_cols:
            for col_name, col_data in manifest_cols.items():
                cat = catalog_cols.get(col_name.lower(), {})
                data_type = col_data.get("data_type") or cat.get("type", "unknown")
                columns.append(ColumnInfo(
                    name=col_name,
                    description=col_data.get("description", ""),
                    data_type=data_type,
                ))
        elif catalog_cols:
            # Manifest has no documented columns — fall back to catalog schema
            for col_name, col_data in catalog_cols.items():
                columns.append(ColumnInfo(
                    name=col_name,
                    description="",
                    data_type=col_data.get("type", "unknown"),
                ))

        meta = node.get("meta", {})
        config = node.get("config", {})
        depends_on_nodes = node.get("depends_on", {}).get("nodes", [])
        # Shorten to just model names, skip sources
        deps = [n.split(".")[-1] for n in depends_on_nodes if n.startswith("model.")]

        # Extract warehouse stats from catalog
        cat_stats = {}
        if catalog:
            cat_node = catalog.get("nodes", {}).get(node["unique_id"], {})
            for stat in cat_node.get("stats", {}).values():
                if stat.get("include"):
                    cat_stats[stat["id"]] = stat.get("value")

        return ModelChunk(
            model_id=node["unique_id"],
            model_name=node["name"],
            schema=node.get("schema", ""),
            database=node.get("database", ""),
            description=node.get("description", ""),
            columns=columns,
            tags=node.get("tags", []),
            materialization=config.get("materialized", "view"),
            owner=meta.get("owner", ""),
            refresh_frequency=meta.get("refresh_frequency", ""),
            depends_on=deps,
            child_ids=child_ids or [],
            all_downstream_ids=all_downstream_ids or [],
            file_path=node.get("original_file_path", ""),
            row_count=cat_stats.get("row_count"),
            size_bytes=cat_stats.get("bytes"),
            last_modified=cat_stats.get("last_modified"),
            raw_sql=node.get("raw_code") or node.get("raw_sql"),
            compiled_sql=node.get("compiled_code") or node.get("compiled_sql"),
        )
