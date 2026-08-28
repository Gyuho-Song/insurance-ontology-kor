"""U1 — PBT-02: render_meta_table → _parse_meta_tables round-trip.

단순 JSON round-trip이 아니라, doc-parser HTML 메타테이블을 구조 손실 없이
파싱하는 성질을 검증 (cell/header_path/category 보존).
"""
import sys
from pathlib import Path

from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/

from lib.docparser_adapter import _parse_meta_tables  # noqa: E402


def render_meta_table(table_id, category, page_no, summary, headers, rows):
    """doc-parser 출력 형식으로 table-meta + markdown 표를 역렌더 (테스트용)."""
    meta = (
        '<table class="table-meta">\n'
        f"  <tr>\n    <td>table_id</td>\n    <td>{table_id}</td>\n  </tr>\n"
        f"  <tr>\n    <td>category</td>\n    <td>{category}</td>\n  </tr>\n"
        f"  <tr>\n    <td>page_number</td>\n    <td>{page_no}</td>\n  </tr>\n"
        f"  <tr>\n    <td>table_summary</td>\n    <td>{summary}</td>\n  </tr>\n"
        f"  <tr>\n    <td>entities</td>\n    <td></td>\n  </tr>\n"
        f"  <tr>\n    <td>bbox</td>\n    <td>l=1.0 t=2.0 r=3.0 b=4.0</td>\n  </tr>\n"
        "</table>\n\n"
    )
    hdr = "| " + " | ".join(headers) + " |\n"
    sep = "|" + "|".join(["---"] * len(headers)) + "|\n"
    body = "".join("| " + " | ".join(r) + " |\n" for r in rows)
    return meta + hdr + sep + body


# 도메인 생성기: 현실적 표 (PBT-07)
_cell_text = st.text(alphabet="가나다라0123456789세만~ ", min_size=0, max_size=8)
_category = st.sampled_from(["pricing", "reference", "statistics", "configuration", "other"])


@st.composite
def table_spec(draw):
    ncol = draw(st.integers(min_value=1, max_value=4))
    nrow = draw(st.integers(min_value=1, max_value=5))
    headers = [draw(st.text(alphabet="구분ABC세만기", min_size=1, max_size=5)) for _ in range(ncol)]
    rows = [[draw(_cell_text) for _ in range(ncol)] for _ in range(nrow)]
    return {
        "table_id": f"table-{draw(st.integers(1, 99)):03d}",
        "category": draw(_category),
        "page_no": draw(st.integers(1, 50)),
        "summary": draw(st.text(alphabet="가나다 ", max_size=20)),
        "headers": headers, "rows": rows,
    }


@settings(max_examples=150, deadline=None)
@given(spec=table_spec())
def test_render_parse_roundtrip_preserves_structure(spec):
    md = render_meta_table(**spec)
    tables, _ = _parse_meta_tables(md, "doc", "pv", "rid", "src.pdf")
    assert len(tables) == 1
    t = tables[0]
    # 메타 보존
    assert t.table_id == spec["table_id"]
    assert t.raw_category == spec["category"]
    assert t.page_no == spec["page_no"]
    # 셀 구조 보존: 데이터 행×열 수 일치
    data_cells = [c for c in t.cells if not c.is_header]
    assert len(data_cells) == len(spec["rows"]) * len(spec["headers"])
    # 헤더 path 보존 (헤더 텍스트가 있으면 데이터 셀이 참조)
    if any(h.strip() for h in spec["headers"]):
        assert any(c.header_path for c in data_cells)
