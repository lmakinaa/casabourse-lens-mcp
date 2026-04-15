from __future__ import annotations

import io

import openpyxl
import pytest

from trading_tools.providers.world_bank import parse_phosphate_series


def _build_fixture_xlsx() -> bytes:
    """
    Emit a minimal XLSX that mirrors the Pink Sheet layout:
    row 0-3: preamble, row 4: headers, row 5: units, row 6+: data.
    """
    wb = openpyxl.Workbook()
    default = wb.active
    wb.remove(default)
    sheet = wb.create_sheet("Monthly Prices")

    sheet.append(["World Bank Commodity Price Data (The Pink Sheet)"])
    sheet.append(["monthly prices"])
    sheet.append([None])
    sheet.append(["Updated on April 02, 2026"])
    # Header row (index 4).
    sheet.append([None, "Crude oil, Brent", "Phosphate rock", "Gold"])
    sheet.append([None, "($/bbl)", "($/mt)", "($/toz)"])
    # Data rows start at index 6.
    sheet.append(["2025M12", 70.0, 150.0, 2700.0])
    sheet.append(["2026M01", 72.0, 150.0, 2750.0])
    sheet.append(["2026M02", 74.0, 152.5, 2800.0])
    sheet.append(["2026M03", 75.0, 157.625, 2850.0])  # 157.625/152.5 - 1 = 3.3607%

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_phosphate_series_returns_ordered_points():
    points = parse_phosphate_series(_build_fixture_xlsx())

    assert len(points) == 4
    # Ascending by date.
    assert [p[0].isoformat() for p in points] == [
        "2025-12-31",
        "2026-01-31",
        "2026-02-28",
        "2026-03-31",
    ]
    assert points[-1][1] == pytest.approx(157.625)


def test_parse_phosphate_series_missing_column_returns_empty():
    wb = openpyxl.Workbook()
    default = wb.active
    wb.remove(default)
    sheet = wb.create_sheet("Monthly Prices")

    sheet.append(["preamble"])
    sheet.append(["preamble"])
    sheet.append(["preamble"])
    sheet.append(["preamble"])
    sheet.append([None, "Crude oil, Brent"])  # no phosphate column
    sheet.append([None, "($/bbl)"])
    sheet.append(["2026M03", 75.0])

    buf = io.BytesIO()
    wb.save(buf)

    points = parse_phosphate_series(buf.getvalue())
    assert points == []


def test_parse_phosphate_series_ignores_non_numeric_cells():
    wb = openpyxl.Workbook()
    default = wb.active
    wb.remove(default)
    sheet = wb.create_sheet("Monthly Prices")

    sheet.append(["preamble"])
    sheet.append(["preamble"])
    sheet.append(["preamble"])
    sheet.append(["preamble"])
    sheet.append([None, "Phosphate rock"])
    sheet.append([None, "($/mt)"])
    sheet.append(["2026M02", "…"])  # placeholder used in real data
    sheet.append(["2026M03", 150.0])

    buf = io.BytesIO()
    wb.save(buf)

    points = parse_phosphate_series(buf.getvalue())
    assert len(points) == 1
    assert points[0][1] == 150.0
