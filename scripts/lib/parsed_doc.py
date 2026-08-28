"""U1 — ParsedDoc data model + JSON serialization.

doc-parser(Docling) 출력 메타테이블을 정규화한 중간 구조. U4 TableMapper의 입력 계약.
실제 doc-parser 출력 형식 기반 (scripts/tests/fixtures/docparser/ ground truth):
  <table class="table-meta"> key/value rows </table>
  ![img](...)
  | md table header |
  |---|
  | data rows |

provenance 모델 (피드백 반영):
  Table.bbox = 표 단위 좌표 (doc-parser 제공)
  Cell.bbox  = 셀 좌표 (doc-parser 미제공 → None, gap 집계)
  Cell.provenance = {page_no, source_pdf, parser_version, run_id}
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class CellProvenance:
    page_no: int | None = None
    source_pdf: str = ""
    parser_version: str = ""
    run_id: str = ""


@dataclass
class Cell:
    row: int
    col: int
    text: str
    rowspan: int = 1
    colspan: int = 1
    bbox: tuple | None = None          # cell 좌표 (doc-parser 미제공 시 None)
    header_path: list[str] = field(default_factory=list)
    is_header: bool = False
    provenance: CellProvenance | None = None


@dataclass
class Table:
    table_id: str
    raw_category: str = "other"        # doc-parser category (pricing/reference/...) — 일반 유형
    caption: str = ""
    summary: str = ""                  # doc-parser table_summary
    entities: list[str] = field(default_factory=list)
    cells: list[Cell] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)
    raw_markdown: str = ""             # 원본 markdown 파이프 표 (fallback)
    page_no: int | None = None
    bbox: tuple | None = None          # 표 단위 좌표


@dataclass
class Figure:
    figure_id: str
    category: str = "other"
    page_no: int | None = None
    summary: str = ""
    bbox: tuple | None = None


@dataclass
class Page:
    page_no: int
    summary: str = ""
    entities: list[str] = field(default_factory=list)


@dataclass
class ParsedDoc:
    document_id: str
    markdown: str = ""                 # 본문 (표 위치엔 {{TABLE:id}} placeholder)
    tables: list[Table] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    pages: list[Page] = field(default_factory=list)
    source_pdf: str = ""
    parser_version: str = ""
    extraction_run_id: str = ""

    # ── 직렬화 ────────────────────────────────────────────
    def to_json(self) -> str:
        return json.dumps(self._to_dict(), ensure_ascii=False, indent=2)

    def _to_dict(self) -> dict:
        # tuple(bbox)은 list로 직렬화됨 → from_json에서 복원
        return asdict(self)

    @classmethod
    def from_json(cls, s: str) -> "ParsedDoc":
        return cls.from_dict(json.loads(s))

    @classmethod
    def from_dict(cls, d: dict) -> "ParsedDoc":
        def _bbox(v):
            return tuple(v) if isinstance(v, list) else v

        tables = []
        for t in d.get("tables", []):
            cells = []
            for c in t.get("cells", []):
                prov = c.get("provenance")
                cells.append(Cell(
                    row=c["row"], col=c["col"], text=c["text"],
                    rowspan=c.get("rowspan", 1), colspan=c.get("colspan", 1),
                    bbox=_bbox(c.get("bbox")), header_path=c.get("header_path", []),
                    is_header=c.get("is_header", False),
                    provenance=CellProvenance(**prov) if prov else None,
                ))
            tables.append(Table(
                table_id=t["table_id"], raw_category=t.get("raw_category", "other"),
                caption=t.get("caption", ""), summary=t.get("summary", ""),
                entities=t.get("entities", []), cells=cells,
                notes=t.get("notes", []), units=t.get("units", {}),
                raw_markdown=t.get("raw_markdown", ""), page_no=t.get("page_no"),
                bbox=_bbox(t.get("bbox")),
            ))
        figures = [Figure(**{**f, "bbox": _bbox(f.get("bbox"))}) for f in d.get("figures", [])]
        pages = [Page(**p) for p in d.get("pages", [])]
        return cls(
            document_id=d["document_id"], markdown=d.get("markdown", ""),
            tables=tables, figures=figures, pages=pages,
            source_pdf=d.get("source_pdf", ""), parser_version=d.get("parser_version", ""),
            extraction_run_id=d.get("extraction_run_id", ""),
        )
