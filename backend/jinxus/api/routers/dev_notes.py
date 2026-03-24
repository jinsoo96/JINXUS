"""업무 노트 API — docs/dev_notes/*.md CRUD"""
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dev-notes", tags=["dev-notes"])

_NOTES_DIR = Path(os.getenv("PROJECT_ROOT", "/home/jinsookim/jinxus")) / "docs" / "dev_notes"


def _ensure_dir():
    _NOTES_DIR.mkdir(parents=True, exist_ok=True)


def create_work_note(title: str, content: str, filename: str | None = None) -> dict:
    """에이전트 내부에서 직접 호출 가능한 업무 노트 생성 함수 (HTTP 경유 불필요)"""
    _ensure_dir()
    if filename:
        fname = filename if filename.endswith(".md") else f"{filename}.md"
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        fname = f"{today}_{_slug(title)}.md"
    path = _NOTES_DIR / fname
    # 같은 파일명이 이미 있으면 타임스탬프 suffix 추가
    if path.exists():
        ts = datetime.now().strftime("%H%M%S")
        fname = fname.replace(".md", f"_{ts}.md")
        path = _NOTES_DIR / fname
    path.write_text(content, encoding="utf-8")
    logger.info(f"[WorkNotes] 에이전트 자동 생성: {fname}")
    return _parse_note(path)


def _slug(title: str) -> str:
    """제목 → 파일명용 slug"""
    s = re.sub(r"[^\w\s-]", "", title.lower())
    s = re.sub(r"[\s]+", "_", s.strip())
    return s[:60] or "note"


def _parse_note(path: Path) -> dict:
    """마크다운 파일 → 노트 메타데이터"""
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # 제목: 첫 번째 # 헤딩
    title = path.stem
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    # 날짜: 파일명 앞부분 YYYY-MM-DD 또는 **날짜:** 라인
    date_str = ""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", path.stem)
    if m:
        date_str = m.group(1)
    for line in lines:
        m2 = re.match(r"\*\*날짜:\*\*\s*(.+)", line)
        if m2:
            date_str = m2.group(1).strip()
            break

    # 요약: 첫 번째 빈 줄 이후 첫 번째 비어있지 않은 텍스트 줄
    summary = ""
    found_title = False
    for line in lines:
        if line.startswith("# "):
            found_title = True
            continue
        if found_title and line.strip() and not line.startswith("#"):
            summary = line.strip()[:120]
            break

    stat = path.stat()
    return {
        "id": path.stem,
        "filename": path.name,
        "title": title,
        "date": date_str,
        "summary": summary,
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


# ── 목록 ──────────────────────────────────────────────────────────────────────

@router.get("")
async def list_notes():
    _ensure_dir()
    notes = []
    for f in sorted(_NOTES_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            notes.append(_parse_note(f))
        except Exception as e:
            logger.warning(f"[WorkNotes] 노트 파싱 실패 ({f.name}): {e}")
    return {"notes": notes, "count": len(notes)}


# ── 단건 조회 ─────────────────────────────────────────────────────────────────

@router.get("/{note_id}")
async def get_note(note_id: str):
    _ensure_dir()
    path = _NOTES_DIR / f"{note_id}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"노트 없음: {note_id}")
    content = path.read_text(encoding="utf-8")
    meta = _parse_note(path)
    return {**meta, "content": content}


# ── 생성 ──────────────────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    title: str
    content: str
    filename: Optional[str] = None  # 지정하면 그대로, 없으면 날짜_slug 자동 생성


@router.post("", status_code=201)
async def create_note(body: NoteCreate):
    _ensure_dir()
    if body.filename:
        fname = body.filename if body.filename.endswith(".md") else f"{body.filename}.md"
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        fname = f"{today}_{_slug(body.title)}.md"

    path = _NOTES_DIR / fname
    if path.exists():
        raise HTTPException(status_code=409, detail=f"이미 존재: {fname}")

    path.write_text(body.content, encoding="utf-8")
    logger.info(f"[WorkNotes] 생성: {fname}")
    return _parse_note(path)


# ── 수정 ──────────────────────────────────────────────────────────────────────

class NoteUpdate(BaseModel):
    content: str


@router.put("/{note_id}")
async def update_note(note_id: str, body: NoteUpdate):
    _ensure_dir()
    path = _NOTES_DIR / f"{note_id}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"노트 없음: {note_id}")
    path.write_text(body.content, encoding="utf-8")
    logger.info(f"[WorkNotes] 수정: {note_id}")
    return _parse_note(path)


# ── 삭제 ──────────────────────────────────────────────────────────────────────

@router.delete("/{note_id}")
async def delete_note(note_id: str):
    _ensure_dir()
    path = _NOTES_DIR / f"{note_id}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"노트 없음: {note_id}")
    path.unlink()
    logger.info(f"[WorkNotes] 삭제: {note_id}")
    return {"deleted": note_id}
