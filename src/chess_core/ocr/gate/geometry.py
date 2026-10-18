"""Printed / margin zones from stage12 meta. No learning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class SheetGeometry:
    skipped_columns: tuple[int, ...]
    skipped_rows: tuple[int, ...]
    first_data_row: int
    grid_rows: int
    grid_cols: int
    h_lines: tuple[int, ...]
    v_lines: tuple[int, ...]

    @classmethod
    def from_meta(cls, meta: Mapping[str, Any] | None, *, report: Mapping[str, Any] | None = None) -> "SheetGeometry":
        payload = dict(meta or {})
        detect = payload.get("line_detect") or {}
        report = report or {}
        skipped_columns = payload.get("skipped_columns")
        skipped_rows = payload.get("skipped_rows")
        first_data = payload.get("first_data_row")
        return cls(
            skipped_columns=tuple(int(x) for x in skipped_columns)
            if skipped_columns is not None
            else (0, 3, 6),
            skipped_rows=tuple(int(x) for x in skipped_rows)
            if skipped_rows is not None
            else (0,),
            first_data_row=int(first_data) if first_data is not None else 1,
            grid_rows=int(payload.get("grid_rows") or report.get("grid_rows") or 0),
            grid_cols=int(payload.get("grid_cols") or report.get("grid_cols") or 0),
            h_lines=tuple(int(x) for x in (detect.get("h_lines") or ())),
            v_lines=tuple(int(x) for x in (detect.get("v_lines") or ())),
        )


class GeometryPrefilter:
    """Mark №-columns, table header row, and fields as printed/noise."""

    def zone(self, geometry: SheetGeometry, *, row: int | None, col: int | None) -> str | None:
        if row is None or col is None:
            return None
        if col in geometry.skipped_columns:
            return "printed_index"
        if row in geometry.skipped_rows or row < geometry.first_data_row:
            return "printed_header"
        return None

    def is_printed(self, geometry: SheetGeometry, *, row: int | None, col: int | None) -> bool:
        return self.zone(geometry, row=row, col=col) is not None
