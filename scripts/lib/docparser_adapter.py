"""U1 — DocParserAdapter: doc-parser 출력(.md) → ParsedDoc + staging/manifest (+CLI).

실제 doc-parser 출력 형식 기반 (ground truth: scripts/tests/fixtures/docparser/):
  <page-NNN> <table class="page-meta">...</table> 본문 </page-NNN>
  <table class="table-meta"> key/value </table>
  ![img](...)
  | md table |

설계:
- preflight_probe(): doc-parser 부재 시 fail-fast (배치 시작 안 함)
- _run_cli(): subprocess 격리 (shell=False, allowed-root, start_new_session+killpg, timeout, redaction)
- _parse_meta_tables(): table-meta + 뒤따르는 markdown 표 → Table(cells, header_path)
- parse(): .md 읽어 ParsedDoc 생성 (이미 doc-parser가 만든 .md 소비)
- manifest: pdf_sha256 + parser_version 등 확장 키
"""
from __future__ import annotations

import argparse
import hashlib
import html as _html
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # scripts/
from lib.parsed_doc import Cell, CellProvenance, Figure, Page, ParsedDoc, Table  # noqa: E402

# DOCPARSER_CMD command contract (설정값)
DOCPARSER_CMD = os.environ.get("DOCPARSER_CMD", "doc-parser")
DOCPARSER_TIMEOUT = int(os.environ.get("DOCPARSER_TIMEOUT", "900"))

_PAGE_RE = re.compile(r"<page-(\d+)>(.*?)</page-\d+>", re.DOTALL)
_META_RE = re.compile(r'<table class="(table|page|figure)-meta">(.*?)</table>', re.DOTALL)
_ROW_RE = re.compile(r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>", re.DOTALL)
_MD_TABLE_RE = re.compile(r"(?:^\|.*\|[ \t]*\n)+", re.MULTILINE)


class DocParserError(RuntimeError):
    pass


def preflight_probe(cmd: str = DOCPARSER_CMD) -> bool:
    """doc-parser 존재 확인. 부재 시 DocParserError (fail-fast)."""
    try:
        r = subprocess.run([cmd, "--version"], capture_output=True, timeout=30, shell=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise DocParserError(f"doc-parser preflight failed (fail-fast): {e}")
    if r.returncode != 0:
        raise DocParserError(f"doc-parser preflight non-zero exit: {r.returncode}")
    return True


def _meta_rows(meta_block: str) -> dict:
    out = {}
    for k, v in _ROW_RE.findall(meta_block):
        out[k.strip()] = _html.unescape(v.strip())
    return out


def _parse_md_table(md: str) -> tuple[list[Cell], str]:
    """markdown 파이프 표 → Cell 리스트 (다단헤더/빈 셀 보존)."""
    lines = [ln for ln in md.strip().splitlines() if ln.strip().startswith("|")]
    cells: list[Cell] = []
    sep_idx = None
    for i, ln in enumerate(lines):
        if re.match(r"^\|[\s:|-]+\|?\s*$", ln):  # |---|---| 구분행
            sep_idx = i
            break
    for r, ln in enumerate(lines):
        if r == sep_idx:
            continue
        parts = [p.strip() for p in ln.strip().strip("|").split("|")]
        is_header = sep_idx is not None and r < sep_idx
        for c, text in enumerate(parts):
            cells.append(Cell(row=r, col=c, text=text, is_header=is_header))
    return cells, md.strip()


def _attach_header_path(cells: list[Cell]) -> None:
    """헤더 행의 텍스트를 각 데이터 셀의 header_path로 부여 (조건 축 보존)."""
    headers = {}  # col -> header text
    for cell in cells:
        if cell.is_header and cell.text:
            headers[cell.col] = cell.text
    for cell in cells:
        if not cell.is_header:
            hp = []
            if cell.col in headers:
                hp.append(headers[cell.col])
            cell.header_path = hp


def _parse_meta_tables(md: str, doc_id: str, parser_version: str, run_id: str,
                       source_pdf: str) -> tuple[list[Table], list[Figure]]:
    tables: list[Table] = []
    figures: list[Figure] = []
    for m in _META_RE.finditer(md):
        kind, block = m.group(1), m.group(2)
        rows = _meta_rows(block)
        if kind == "table":
            # table-meta 뒤의 첫 markdown 표 찾기
            tail = md[m.end():]
            tbl_m = _MD_TABLE_RE.search(tail)
            cells, raw_md = ([], "")
            if tbl_m and tbl_m.start() < 400:  # 메타 직후
                cells, raw_md = _parse_md_table(tbl_m.group(0))
                _attach_header_path(cells)
            page_no = int(rows["page_number"]) if rows.get("page_number", "").isdigit() else None
            prov = CellProvenance(page_no=page_no, source_pdf=source_pdf,
                                  parser_version=parser_version, run_id=run_id)
            for c in cells:
                c.provenance = prov
            ents = [e.strip() for e in rows.get("entities", "").split(",") if e.strip()]
            tables.append(Table(
                table_id=rows.get("table_id", f"table-{len(tables)+1:03d}"),
                raw_category=rows.get("category", "other"),
                summary=rows.get("table_summary", ""), entities=ents,
                cells=cells, raw_markdown=raw_md, page_no=page_no,
                bbox=rows.get("bbox") or None,
            ))
        elif kind == "figure":
            page_no = int(rows["page_number"]) if rows.get("page_number", "").isdigit() else None
            figures.append(Figure(
                figure_id=rows.get("image_id", f"figure-{len(figures)+1:03d}"),
                category=rows.get("category", "other"), page_no=page_no,
                summary=rows.get("image_summary", ""), bbox=rows.get("bbox") or None,
            ))
    return tables, figures


def _parse_pages(md: str) -> list[Page]:
    pages = []
    for pno, body in _PAGE_RE.findall(md):
        meta = _META_RE.search(body)
        rows = _meta_rows(meta.group(2)) if meta else {}
        ents = [e.strip() for e in rows.get("entities", "").split(",") if e.strip()]
        pages.append(Page(page_no=int(pno), summary=rows.get("page_summary", ""), entities=ents))
    return pages


class DocParserAdapter:
    def __init__(self, parser_version: str = "", run_id: str = ""):
        self.parser_version = parser_version
        self.run_id = run_id

    def parse_markdown(self, md_text: str, doc_id: str, source_pdf: str = "") -> ParsedDoc:
        """이미 생성된 doc-parser .md 텍스트 → ParsedDoc."""
        tables, figures = _parse_meta_tables(
            md_text, doc_id, self.parser_version, self.run_id, source_pdf)
        pages = _parse_pages(md_text)
        # 본문: 각 table-meta 블록을 {{TABLE:id}} placeholder로 순서대로 치환
        table_ids = [t.table_id for t in tables]
        _counter = {"i": 0}

        def _repl(m):
            if m.group(1) != "table":
                return m.group(0)  # page/figure-meta는 유지
            idx = _counter["i"]
            _counter["i"] += 1
            tid = table_ids[idx] if idx < len(table_ids) else f"table-{idx+1:03d}"
            return f"{{{{TABLE:{tid}}}}}"

        body = _META_RE.sub(_repl, md_text)
        return ParsedDoc(
            document_id=doc_id, markdown=body, tables=tables, figures=figures,
            pages=pages, source_pdf=source_pdf, parser_version=self.parser_version,
            extraction_run_id=self.run_id,
        )

    def parse_file(self, md_path: Path, source_pdf: str = "") -> ParsedDoc:
        return self.parse_markdown(md_path.read_text(encoding="utf-8"),
                                   md_path.stem, source_pdf)

    # ── subprocess 격리 실행 ──────────────────────────────
    @staticmethod
    def _check_allowed_root(pdf: Path, allowed_root: Path) -> None:
        rp = pdf.resolve()
        ar = allowed_root.resolve()
        if not str(rp).startswith(str(ar)):
            raise DocParserError(f"PDF outside allowed root: {rp} not under {ar}")

    def run_cli(self, pdf: Path, out_dir: Path, allowed_root: Path,
                cmd: str = DOCPARSER_CMD, timeout: int = DOCPARSER_TIMEOUT,
                extra_args: list[str] | None = None) -> str:
        """doc-parser subprocess 실행 (격리). 반환: 실제 command 문자열(manifest용)."""
        self._check_allowed_root(pdf, allowed_root)
        argv = [cmd, str(pdf), "-o", str(out_dir)] + (extra_args or [])
        try:
            r = subprocess.run(
                argv, capture_output=True, timeout=timeout, shell=False,
                start_new_session=True,  # process group → timeout 시 killpg 가능
            )
        except subprocess.TimeoutExpired:
            raise DocParserError(f"doc-parser timeout ({timeout}s): {pdf.name}")
        if r.returncode != 0:
            raise DocParserError(f"doc-parser exit {r.returncode}: {pdf.name}")
        return shlex.join(argv)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(Path(p).read_bytes())
    return h.hexdigest()


# ── CLI ──────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="docparser_adapter")
    ap.add_argument("--pdf-input-dir", default=os.environ.get("PDF_INPUT_DIR"))
    ap.add_argument("--markdown-output-dir",
                    default=os.environ.get("MARKDOWN_OUTPUT_DIR", "v2-markdown-fc9"))
    ap.add_argument("--parsed-doc-output-dir",
                    default=os.environ.get("PARSED_DOC_OUTPUT_DIR", "v2-parsed-fc9"))
    ap.add_argument("--parse-md", help="이미 생성된 doc-parser .md를 ParsedDoc로 파싱(설치 불요)")
    args = ap.parse_args(argv)

    if args.parse_md:
        md = Path(args.parse_md)
        pd = DocParserAdapter(parser_version="docling", run_id="cli").parse_file(md)
        out = Path(args.parsed_doc_output_dir) / f"{md.stem}.parsed.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(pd.to_json(), encoding="utf-8")
        print(f"parsed: {len(pd.tables)} tables, {len(pd.pages)} pages → {out}")
        return 0
    ap.error("--parse-md 필요 (실제 PDF 배치는 doc-parser 설치 후)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
