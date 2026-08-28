# doc-parser real fixtures (FC9 U1)

실제 한화생명 약관 PDF를 doc-parser(Docling+TableFormer, Opus 4.8 us-west-2)로 추출한 **real fixture**.
acceptance gate: synthetic 아님 — U1 파서는 이 실제 출력 형식에 맞춰 구현.

| fixture | 카테고리 | 상품 | summary | 표 |
|---|---|---|---|---|
| real_P_signature_cancer_opus_full.md | P 가입조건 | 시그니처H암보험 | Opus 4.8 | 98 tables (category: pricing 48/reference 48/statistics 1/configuration 1) |
| real_P_signature_cancer_opus_excerpt.md | P | 〃 발췌(가입나이 표) | Opus | 첫 표=가입나이(만15~80세) |
| real_G_h_whole_life.md | G 계산 | H종신보험 | no-summary | 24 tables (해약환급금/환급률) |
| real_J_h_diabetes.md | J 납입면제 | H당뇨보험 | no-summary | 29 tables (장해50%↑ 납입면제) |
| real_signature_h_cancer_full.md | (no-summary 비교본) | 시그니처H암보험 | no-summary | category 전부 other |

## 실제 출력 형식 (ground truth)
- `<page-NNN>` 래핑 + `<table class="page-meta">` (멀티라인 <tr><td>)
- `<table class="table-meta">`: table_id/category/page_number/table_summary/entities/bbox/img_source
  - bbox = **표 단위만** (l/t/r/b), cell-bbox 없음 → cell provenance는 gap
  - category: --no-summary면 'other', summary 있으면 pricing/reference/statistics/configuration (일반 유형)
- table-meta **아래에 markdown 파이프 표**(`| ... |`)가 실제 데이터 — 다단헤더/병합셀(빈 셀) 존재
- → U1 _parse_meta_tables는 (meta + 뒤따르는 markdown 표)를 함께 파싱. U4 classify_table이 category+summary로 도메인 재매핑.
