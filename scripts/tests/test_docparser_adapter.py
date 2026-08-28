"""U1 — DocParserAdapter example-based tests (real fixture 기반)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/

from lib.docparser_adapter import (  # noqa: E402
    DocParserAdapter, DocParserError, preflight_probe, sha256_file, _parse_md_table,
)
from lib.parsed_doc import ParsedDoc  # noqa: E402
from lib.section_splitter import split_parsed_doc, split_document, SplitResult  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "docparser"
P_FULL = FIX / "real_P_signature_cancer_opus_full.md"
G_FULL = FIX / "real_G_h_whole_life.md"
J_FULL = FIX / "real_J_h_diabetes.md"


@pytest.fixture
def adapter():
    return DocParserAdapter(parser_version="docling-2.104", run_id="test")


# ── real fixture 파싱 ───────────────────────────────────────
def test_parse_p_fixture(adapter):
    pd = adapter.parse_file(P_FULL, source_pdf="sig.pdf")
    assert len(pd.tables) == 98
    assert len(pd.pages) == 90
    t0 = pd.tables[0]
    assert t0.table_id == "table-001"
    assert t0.raw_category == "reference"   # Opus summary 분류
    assert t0.page_no == 5
    assert t0.bbox  # 표 단위 bbox 존재

def test_p_table_cells_preserve_header_path(adapter):
    pd = adapter.parse_file(P_FULL)
    t0 = pd.tables[0]
    data = [c for c in t0.cells if not c.is_header and c.text]
    # 가입나이 셀이 header_path(조건 축)를 보존
    age_cells = [c for c in data if "만" in c.text and "세" in c.text]
    assert age_cells
    assert any(c.header_path for c in age_cells)

def test_placeholder_replaces_table_meta(adapter):
    pd = adapter.parse_file(P_FULL)
    assert "{{TABLE:table-001}}" in pd.markdown
    assert 'class="table-meta"' not in pd.markdown  # table-meta는 placeholder로 치환됨

def test_page_meta_preserved_in_body(adapter):
    pd = adapter.parse_file(P_FULL)
    # page-meta는 placeholder 대상 아님 (본문 구조 유지)
    assert 'class="page-meta"' in pd.markdown

def test_cell_provenance_has_no_cell_bbox(adapter):
    # doc-parser는 cell bbox 미제공 → gap (None) 확인
    pd = adapter.parse_file(P_FULL)
    cells = pd.tables[0].cells
    assert all(c.bbox is None for c in cells)
    assert all(c.provenance and c.provenance.page_no == 5 for c in cells)

def test_g_and_j_fixtures(adapter):
    pg = adapter.parse_file(G_FULL)
    pj = adapter.parse_file(J_FULL)
    assert len(pg.tables) >= 20   # H종신 해약환급금 표들
    assert len(pj.tables) >= 20   # H당뇨 납입면제 표들


# ── .parsed.json 직렬화 ─────────────────────────────────────
def test_parsed_json_roundtrip(adapter):
    pd = adapter.parse_file(P_FULL, source_pdf="sig.pdf")
    s = pd.to_json()
    pd2 = ParsedDoc.from_json(s)
    assert pd2.document_id == pd.document_id
    assert len(pd2.tables) == len(pd.tables)
    assert pd2.tables[0].table_id == pd.tables[0].table_id
    assert len(pd2.tables[0].cells) == len(pd.tables[0].cells)


# ── preflight fail-fast (mock) ──────────────────────────────
def test_preflight_fail_fast_when_missing():
    with pytest.raises(DocParserError):
        preflight_probe(cmd="definitely-not-a-real-docparser-binary-xyz")


# ── allowed-root 경로 검사 ──────────────────────────────────
def test_run_cli_rejects_outside_allowed_root(adapter, tmp_path):
    outside = Path("/etc/passwd")
    with pytest.raises(DocParserError):
        adapter.run_cli(outside, tmp_path, allowed_root=tmp_path)


# ── manifest 해시 ───────────────────────────────────────────
def test_sha256_file(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hello")
    h = sha256_file(f)
    assert len(h) == 64


# ── markdown 표 파싱 (다단헤더/빈셀) ───────────────────────
def test_parse_md_table_preserves_empty_cells():
    md = "| A | B |\n|---|---|\n|  | x |\n"
    cells, raw = _parse_md_table(md)
    data = [c for c in cells if not c.is_header]
    assert data[0].text == ""   # 빈 셀 보존
    assert data[1].text == "x"


# ── section_splitter 비파괴 회귀 ────────────────────────────
def test_split_document_unchanged():
    # 기존 split_document은 list[ExtractionUnit] 반환 (시그니처 불변)
    units = split_document("## 1. 가입자격\n내용\n## 2. 보장\n내용2", "테스트.md")
    assert isinstance(units, list)
    assert all(hasattr(u, "section_id") for u in units)

def test_split_parsed_doc_links_tables(adapter):
    pd = adapter.parse_file(P_FULL)
    sr = split_parsed_doc(pd, "시그니처.md")
    assert isinstance(sr, SplitResult)
    assert sr.tables
    # placeholder가 있는 unit은 table_refs 보유
    all_refs = [r for refs in sr.unit_table_refs.values() for r in refs]
    assert any(r.startswith("table-") for r in all_refs)
