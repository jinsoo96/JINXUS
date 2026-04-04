"""WaveNote → Whiteboard 동기화 스크립트

JX_OPS가 수집한 노트 목록을 받아 화이트보드에 미등록 노트만 등록.

사용법:
  # 직접 실행 (노트 목록을 JSON 파일로 입력)
  python3 scripts/wavenote_whiteboard_sync.py --input notes.json

  # stdin으로 JSON 파이프
  echo '[{"title": "회의록", "content": "..."}]' | python3 scripts/wavenote_whiteboard_sync.py

  # 테스트용 샘플 데이터
  python3 scripts/wavenote_whiteboard_sync.py --sample

입력 JSON 형식 (JX_OPS 수집 결과):
  [
    {"title": "노트 제목", "content": "전사 내용"},
    ...
  ]
"""
import argparse
import json
import sys
import urllib.request
import urllib.error

WHITEBOARD_BASE = "http://localhost:19000/whiteboard"


def get_registered_titles() -> set[str]:
    """화이트보드에서 source='wavenote'인 항목의 title 목록 조회."""
    try:
        with urllib.request.urlopen(WHITEBOARD_BASE, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        print(f"[ERROR] 화이트보드 조회 실패: {e}", file=sys.stderr)
        sys.exit(1)

    titles = {
        item["title"]
        for item in data.get("items", [])
        if item.get("source") == "wavenote"
    }
    print(f"[INFO] 기존 wavenote 등록 항목: {len(titles)}건")
    return titles


def post_note(title: str, content: str) -> bool:
    """화이트보드에 노트 1건 등록. 실패 시 False 반환 (재시도 없음)."""
    payload = json.dumps({
        "type": "memo",
        "title": title,
        "content": content,
        "source": "wavenote",
        "tags": ["녹음", "wavenote"],
    }).encode("utf-8")

    req = urllib.request.Request(
        WHITEBOARD_BASE,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            return result.get("success", False)
    except urllib.error.URLError as e:
        print(f"[SKIP] '{title}' 등록 실패 (네트워크 오류): {e}", file=sys.stderr)
        return False


def sync(notes: list[dict]) -> None:
    """중복 체크 후 미등록 노트만 화이트보드에 등록."""
    if not notes:
        print("[RESULT] 입력 노트 없음")
        return

    registered_titles = get_registered_titles()

    new_notes = [n for n in notes if n.get("title") not in registered_titles]
    skipped = len(notes) - len(new_notes)

    if skipped:
        print(f"[INFO] 중복 제외: {skipped}건")

    if not new_notes:
        print("[RESULT] 새 노트 없음")
        return

    success_count = 0
    for note in new_notes:
        title = note.get("title", "").strip()
        content = note.get("content", "").strip()

        if not title or not content:
            print(f"[SKIP] title 또는 content 누락: {note}", file=sys.stderr)
            continue

        if post_note(title, content):
            print(f"[OK] 등록: '{title}'")
            success_count += 1
        # 실패 시 post_note 내부에서 SKIP 로그 출력

    print(f"[RESULT] 새 노트 {success_count}건 등록")


SAMPLE_NOTES = [
    {
        "title": "2026-04-04 팀 미팅 회의록",
        "content": "오전 10시 팀 전체 미팅. AAI 로드맵 2단계 진행상황 공유. "
                   "화이트보드 트리거 엔진 설계 완료, 다음 주 구현 시작 예정. "
                   "JX_SECRETARY 루틴 안정화 필요.",
    },
    {
        "title": "아이디어: PixelOffice 에이전트 이동 애니메이션",
        "content": "에이전트가 다른 자리로 이동할 때 pathfinding 적용. "
                   "A* 알고리즘으로 장애물 우회. 이동 속도는 타입별 차등 적용.",
    },
]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WaveNote → Whiteboard 동기화")
    parser.add_argument("--input", "-i", help="노트 목록 JSON 파일 경로")
    parser.add_argument("--sample", action="store_true", help="샘플 데이터로 테스트 실행")
    args = parser.parse_args()

    if args.sample:
        print("[MODE] 샘플 데이터 사용")
        sync(SAMPLE_NOTES)

    elif args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            notes = json.load(f)
        sync(notes)

    elif not sys.stdin.isatty():
        # stdin에서 JSON 읽기
        raw = sys.stdin.read().strip()
        notes = json.loads(raw)
        sync(notes)

    else:
        parser.print_help()
        print("\n테스트: python3 scripts/wavenote_whiteboard_sync.py --sample")
        sys.exit(0)
