"""Neural Fingerprint SVG 생성

agethos의 _generate_fingerprint_svg를 우선 사용하고,
설치되지 않은 환경에서는 자체 SVG 생성으로 fallback.
"""
import math
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# agethos 사용 가능 여부
try:
    from agethos.export.brain_file import _generate_fingerprint_svg as _agethos_fingerprint
    from agethos.models import PersonaSpec, OceanTraits as AgethoOcean, EmotionalState as AgethoEmotion
    HAS_AGETHOS = True
except ImportError:
    HAS_AGETHOS = False

from .manager import PersonalityProfile


def generate_fingerprint_svg(profile: PersonalityProfile, team_color: Optional[str] = None) -> str:
    """PersonalityProfile로부터 Neural Fingerprint SVG 생성.

    Args:
        profile: PersonalityManager의 프로필 객체
        team_color: 팀 대표 hex 색상 (예: '#3b82f6'). 없으면 기본 인디고 사용
    """
    # agethos가 있으면 PersonaSpec 변환 후 사용
    if HAS_AGETHOS:
        try:
            ocean = profile.ocean
            persona = PersonaSpec(
                name=profile.name or profile.agent,
                ocean=AgethoOcean(
                    openness=ocean.openness,
                    conscientiousness=ocean.conscientiousness,
                    extraversion=ocean.extraversion,
                    agreeableness=ocean.agreeableness,
                    neuroticism=ocean.neuroticism,
                ),
            )
            # emotion 매핑
            if profile.emotion:
                persona.emotion = AgethoEmotion(
                    pleasure=profile.emotion.pleasure,
                    arousal=profile.emotion.arousal,
                    dominance=profile.emotion.dominance,
                )
            svg = _agethos_fingerprint(persona, [])
            # 팀 색상 적용 — agethos SVG의 기본 인디고를 팀 색상으로 치환
            if team_color:
                svg = _apply_team_color(svg, team_color)
            return svg
        except Exception as e:
            logger.warning(f"[Fingerprint] agethos 호출 실패, fallback 사용: {e}")

    # fallback — 자체 SVG 생성
    return _generate_fallback_svg(profile, team_color)


def _apply_team_color(svg: str, team_color: str) -> str:
    """SVG 내 기본 인디고 색상(#6366f1)을 팀 색상으로 치환"""
    # hex to rgba 변환
    r = int(team_color[1:3], 16)
    g = int(team_color[3:5], 16)
    b = int(team_color[5:7], 16)
    rgba_fill = f"rgba({r}, {g}, {b}, 0.25)"
    svg = svg.replace("rgba(99, 102, 241, 0.25)", rgba_fill)
    svg = svg.replace("#6366f1", team_color)
    return svg


# ── 팀 색상 매핑 (백엔드용, personas.py에서 가져올 수 없으므로 별도 정의) ──
TEAM_COLORS = {
    "경영": "#fbbf24",
    "개발팀": "#3b82f6",
    "플랫폼팀": "#8b5cf6",
    "프로덕트팀": "#22c55e",
    "마케팅팀": "#ec4899",
    "경영지원팀": "#f97316",
}


def get_team_color(team: str) -> str:
    """팀 이름으로 대표 색상 조회"""
    return TEAM_COLORS.get(team, "#6366f1")


def _generate_fallback_svg(profile: PersonalityProfile, team_color: Optional[str] = None) -> str:
    """agethos 없이 자체 OCEAN 레이더 차트 SVG 생성.

    400x400 뷰박스, 5축(O/C/E/A/N) 레이더 + 감정 상태 점 + 팀 색상.
    """
    color = team_color or "#6366f1"
    r_int = int(color[1:3], 16)
    g_int = int(color[3:5], 16)
    b_int = int(color[5:7], 16)

    width, height = 400, 400
    cx, cy = 200, 200
    radius = 140

    ocean = profile.ocean
    traits = [ocean.openness, ocean.conscientiousness, ocean.extraversion,
              ocean.agreeableness, ocean.neuroticism]
    labels = ["O", "C", "E", "A", "N"]

    def polar(angle_deg: float, r: float) -> tuple:
        rad = math.radians(angle_deg - 90)
        return cx + r * math.cos(rad), cy + r * math.sin(rad)

    angles = [i * 72 for i in range(5)]

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}">',
        '<style>',
        '  .grid { stroke: #e0e0e0; stroke-width: 0.5; fill: none; }',
        f'  .shape {{ fill: rgba({r_int}, {g_int}, {b_int}, 0.25); stroke: {color}; stroke-width: 2; }}',
        '  .label { font: bold 12px sans-serif; fill: #374151; text-anchor: middle; }',
        '  .value { font: 10px sans-serif; fill: #6b7280; text-anchor: middle; }',
        '  .title { font: bold 14px sans-serif; fill: #111827; text-anchor: middle; }',
        '  .emotion-dot { fill: #ef4444; }',
        '</style>',
        f'<rect width="{width}" height="{height}" fill="white" rx="16"/>',
    ]

    # 그리드 (3단계)
    for scale in (0.33, 0.66, 1.0):
        r = radius * scale
        points = " ".join(f"{polar(a, r)[0]},{polar(a, r)[1]}" for a in angles)
        svg_parts.append(f'<polygon points="{points}" class="grid"/>')

    # 축선
    for a in angles:
        x2, y2 = polar(a, radius)
        svg_parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x2}" y2="{y2}" class="grid"/>')

    # OCEAN 다각형
    trait_points = []
    for i, val in enumerate(traits):
        x, y = polar(angles[i], radius * val)
        trait_points.append(f"{x},{y}")
    svg_parts.append(f'<polygon points="{" ".join(trait_points)}" class="shape"/>')

    # 꼭짓점 + 라벨 + 값
    for i, (val, label) in enumerate(zip(traits, labels)):
        lx, ly = polar(angles[i], radius + 20)
        svg_parts.append(f'<text x="{lx}" y="{ly}" class="label">{label}</text>')
        vx, vy = polar(angles[i], radius + 34)
        svg_parts.append(f'<text x="{vx}" y="{vy}" class="value">{val:.2f}</text>')
        px, py = polar(angles[i], radius * val)
        svg_parts.append(f'<circle cx="{px}" cy="{py}" r="4" fill="{color}"/>')

    # 감정 상태 점
    if profile.emotion:
        ex = cx + profile.emotion.pleasure * 30
        ey = cy - profile.emotion.arousal * 30
        svg_parts.append(f'<circle cx="{ex}" cy="{ey}" r="6" class="emotion-dot" opacity="0.7"/>')
        # 감정 라벨 (간단 PAD 매핑)
        e = profile.emotion
        if e.pleasure > 0.3 and e.arousal > 0.3:
            emo = "excitement"
        elif e.pleasure > 0.3:
            emo = "joy"
        elif e.pleasure < -0.3 and e.arousal > 0.3:
            emo = "anger"
        elif e.pleasure < -0.3:
            emo = "sadness"
        elif e.arousal > 0.5:
            emo = "surprise"
        else:
            emo = "neutral"
        svg_parts.append(f'<text x="{ex}" y="{ey - 10}" class="value" fill="#ef4444">{emo}</text>')

    # 타이틀
    name = profile.name or profile.agent
    svg_parts.append(f'<text x="{cx}" y="30" class="title">{name}</text>')

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)
