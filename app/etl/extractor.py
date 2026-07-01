from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile


SPREADSHEET_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
OFFICE_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


@dataclass(frozen=True)
class ExtractedMaster:
    source_path: Path
    source_filename: str
    file_sha256: str
    file_size_bytes: int
    uploaded_at: datetime
    row_count: int
    raw_fields: dict[str, list[str]]
    rated_entity_name: str | None
    sector: str | None
    country: str | None
    currency: str | None
    accounting_principles: str | None
    business_year_end_month: str | None
    rating_methodologies: list[str]
    industry_risks: list[dict[str, str | float | None]]
    business_risk_profile: str | None
    blended_industry_risk_profile: str | None
    competitive_positioning: str | None


def extract_master(path: Path) -> ExtractedMaster:
    rows = _read_master_rows(path)
    fields: dict[str, list[str]] = {}
    for row in rows:
        if len(row) < 2:
            continue
        label = _clean(row[1])
        if not label:
            continue
        values = [_clean(value) for value in row[2:] if _clean(value) is not None]
        fields[label] = values

    industry_names = fields.get("Industry risk", [])
    industry_scores = fields.get("Industry risk score", [])
    industry_weights = fields.get("Industry weight", [])
    risks: list[dict[str, str | float | None]] = []
    for index, name in enumerate(industry_names):
        risks.append(
            {
                "name": name,
                "score": industry_scores[index] if index < len(industry_scores) else None,
                "weight": _to_float(industry_weights[index]) if index < len(industry_weights) else None,
            }
        )

    stat = path.stat()
    return ExtractedMaster(
        source_path=path,
        source_filename=path.name,
        file_sha256=_sha256(path),
        file_size_bytes=stat.st_size,
        uploaded_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        row_count=len(rows),
        raw_fields=fields,
        rated_entity_name=_first(fields, "Rated entity"),
        sector=_first(fields, "CorporateSector"),
        country=_first(fields, "Country of origin"),
        currency=_first(fields, "Reporting Currency/Units"),
        accounting_principles=_first(fields, "Accounting principles"),
        business_year_end_month=_first(fields, "End of business year"),
        rating_methodologies=fields.get("Rating methodologies applied", []),
        industry_risks=risks,
        business_risk_profile=_first(fields, "Business risk profile"),
        blended_industry_risk_profile=_first(fields, "(Blended) Industry risk profile"),
        competitive_positioning=_first(fields, "Competitive Positioning"),
    )


def _read_master_rows(path: Path) -> list[list[str | None]]:
    with ZipFile(path) as archive:
        shared_strings = _shared_strings(archive)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationship_targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in relationships}
        master_rid = None
        sheets = workbook.find("a:sheets", SPREADSHEET_NS)
        if sheets is None:
            raise ValueError(f"{path.name} workbook does not contain sheet metadata")
        for sheet in sheets:
            if sheet.attrib.get("name") == "MASTER":
                master_rid = sheet.attrib[OFFICE_REL]
                break
        if master_rid is None:
            raise ValueError(f"{path.name} does not contain a MASTER sheet")
        target = relationship_targets[master_rid].lstrip("/")
        sheet_path = target if target.startswith("xl/") else f"xl/{target}"
        worksheet = ET.fromstring(archive.read(sheet_path))

    rows: list[list[str | None]] = []
    for row in worksheet.findall(".//a:sheetData/a:row", SPREADSHEET_NS):
        cells: dict[int, str | None] = {}
        for cell in row.findall("a:c", SPREADSHEET_NS):
            cells[_column_index(cell.attrib["r"])] = _cell_text(cell, shared_strings)
        if cells:
            width = max(cells)
            rows.append([cells.get(index) for index in range(1, width + 1)])
    return rows


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall("a:si", SPREADSHEET_NS):
        strings.append("".join(node.text or "" for node in item.findall(".//a:t", SPREADSHEET_NS)))
    return strings


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str | None:
    if cell.attrib.get("t") == "inlineStr":
        text_node = cell.find("a:is/a:t", SPREADSHEET_NS)
        return text_node.text if text_node is not None else None
    value = cell.find("a:v", SPREADSHEET_NS)
    if value is None or value.text is None:
        return None
    if cell.attrib.get("t") == "s":
        return shared_strings[int(value.text)]
    return value.text


def _column_index(cell_reference: str) -> int:
    letters = re.match(r"[A-Z]+", cell_reference)
    if not letters:
        return 1
    result = 0
    for char in letters.group(0):
        result = result * 26 + ord(char) - ord("A") + 1
    return result


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first(fields: dict[str, list[str]], key: str) -> str | None:
    values = fields.get(key, [])
    return values[0] if values else None


def _to_float(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
