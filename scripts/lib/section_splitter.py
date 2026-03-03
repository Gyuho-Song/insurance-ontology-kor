"""Split markdown documents into extraction units.

Products: split on ## N. section headers (7 standard sections).
  - ## ■ rider detail sections are grouped into batches for sub-splitting.
Laws: split on ## 제N장 chapter headers.
Large sections (>50K chars) are sub-split on ### or ## ■ boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_SECTION_CHARS = 50_000

LAW_KEYWORDS = [
    "법률", "시행령", "시행규칙", "세칙", "관리법", "의료법",
    "보호에 관한 법률", "보험업법",
]

# Numbered section pattern: ## 1. or ## 2. etc.
NUMBERED_SECTION_RE = re.compile(r"^## (\d+)\.\s*(.*)$", re.MULTILINE)
# Law chapter pattern: ## 제N장
LAW_CHAPTER_RE = re.compile(r"^## (제\d+장\s*.*)$", re.MULTILINE)
# Rider detail pattern: ## ■
RIDER_SECTION_RE = re.compile(r"^## ■\s*(.*)$", re.MULTILINE)
# Sub-heading for sub-splitting
SUB_HEADING_RE = re.compile(r"^(?:### |## ■ )", re.MULTILINE)


@dataclass
class ExtractionUnit:
    section_id: str
    section_title: str
    content: str
    char_count: int = 0

    def __post_init__(self):
        self.char_count = len(self.content)


def is_law_document(filename: str) -> bool:
    return any(kw in filename for kw in LAW_KEYWORDS)


def split_document(content: str, filename: str) -> list[ExtractionUnit]:
    """Split markdown content into extraction units."""
    if is_law_document(filename):
        return _split_law(content, filename)
    return _split_product(content, filename)


def _split_product(content: str, filename: str) -> list[ExtractionUnit]:
    """Split insurance product markdown by numbered sections.

    Structure:
      ## 1. 상품의 특이사항
      ## 2. 보험가입자격요건
      ## 3. 보험금 지급사유 및 지급제한 사항
        (many ## ■ rider detail sections follow)
      ## 4. 보험료 산출기초 ...
      ## 5. 계약자배당 ...
      ## 6. 해약환급금 ...
      ## 7. 보험가격지수
      (or # 7. for some files)
    """
    units: list[ExtractionUnit] = []

    # Find all ## N. headers
    numbered_matches = list(NUMBERED_SECTION_RE.finditer(content))

    if not numbered_matches:
        # No standard sections found — treat whole file as one unit
        return [ExtractionUnit(
            section_id="full",
            section_title=filename,
            content=content,
        )]

    # Add title/preamble before first section
    preamble = content[:numbered_matches[0].start()].strip()

    # Extract each numbered section's content
    for i, m in enumerate(numbered_matches):
        sec_num = m.group(1)
        sec_title = m.group(2).strip()
        start = m.start()

        # End is next numbered section, or end of file
        if i + 1 < len(numbered_matches):
            end = numbered_matches[i + 1].start()
        else:
            end = len(content)

        sec_content = content[start:end].strip()
        section_id = f"sec{sec_num}"

        # Skip section 4 (보험료 산출기초 — mostly pricing methodology) and
        # section 7 (보험가격지수 — pricing tables) unless they're unusually large
        # indicating rich content. Keep them for completeness.

        units.append(ExtractionUnit(
            section_id=section_id,
            section_title=sec_title,
            content=sec_content,
        ))

    # Sub-split any section that exceeds MAX_SECTION_CHARS
    result = []
    for unit in units:
        if unit.char_count > MAX_SECTION_CHARS:
            sub_units = _subsplit(unit)
            result.extend(sub_units)
        else:
            result.append(unit)

    # Prepend preamble (title) to first unit's content if it has useful info
    if preamble and result:
        result[0] = ExtractionUnit(
            section_id=result[0].section_id,
            section_title=result[0].section_title,
            content=preamble + "\n\n" + result[0].content,
        )

    return result


def _split_law(content: str, filename: str) -> list[ExtractionUnit]:
    """Split law markdown by chapter headers (## 제N장)."""
    units: list[ExtractionUnit] = []

    chapter_matches = list(LAW_CHAPTER_RE.finditer(content))

    if not chapter_matches:
        # Try ## 부칙 or fall back to full
        return [ExtractionUnit(
            section_id="full",
            section_title=filename,
            content=content,
        )]

    # Preamble (title + 총칙 before first chapter)
    preamble = content[:chapter_matches[0].start()].strip()

    for i, m in enumerate(chapter_matches):
        chapter_title = m.group(1).strip()
        start = m.start()

        if i + 1 < len(chapter_matches):
            end = chapter_matches[i + 1].start()
        else:
            end = len(content)

        sec_content = content[start:end].strip()
        # Extract chapter number for section_id
        ch_num = re.search(r"제(\d+)장", chapter_title)
        section_id = f"ch{ch_num.group(1)}" if ch_num else f"ch{i+1}"

        units.append(ExtractionUnit(
            section_id=section_id,
            section_title=chapter_title,
            content=sec_content,
        ))

    # Prepend preamble to first unit
    if preamble and units:
        units[0] = ExtractionUnit(
            section_id=units[0].section_id,
            section_title=units[0].section_title,
            content=preamble + "\n\n" + units[0].content,
        )

    # Sub-split large chapters
    result = []
    for unit in units:
        if unit.char_count > MAX_SECTION_CHARS:
            result.extend(_subsplit(unit))
        else:
            result.append(unit)

    return result


def _subsplit(unit: ExtractionUnit) -> list[ExtractionUnit]:
    """Sub-split a large section on ### or ## ■ boundaries."""
    parts: list[ExtractionUnit] = []
    content = unit.content

    # Find all sub-heading positions
    splits = list(SUB_HEADING_RE.finditer(content))

    if not splits:
        # No sub-headings, return as-is (LLM will handle it)
        return [unit]

    # Build sub-sections by accumulating until MAX_SECTION_CHARS
    current_start = 0
    current_idx = 0
    part_num = 1

    for i, m in enumerate(splits):
        next_pos = splits[i + 1].start() if i + 1 < len(splits) else len(content)
        chunk_so_far = content[current_start:next_pos]

        if len(chunk_so_far) > MAX_SECTION_CHARS and current_start != m.start():
            # Flush what we have up to this split point
            part_content = content[current_start:m.start()].strip()
            if part_content:
                parts.append(ExtractionUnit(
                    section_id=f"{unit.section_id}_part{part_num}",
                    section_title=f"{unit.section_title} (Part {part_num})",
                    content=part_content,
                ))
                part_num += 1
            current_start = m.start()

    # Remaining content
    remaining = content[current_start:].strip()
    if remaining:
        if part_num == 1:
            # Never split — return original
            parts.append(unit)
        else:
            parts.append(ExtractionUnit(
                section_id=f"{unit.section_id}_part{part_num}",
                section_title=f"{unit.section_title} (Part {part_num})",
                content=remaining,
            ))

    return parts if parts else [unit]
