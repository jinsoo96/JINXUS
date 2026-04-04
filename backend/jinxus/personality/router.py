"""Personality API 라우터"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

from .manager import get_personality_manager, _ocean_to_dict, _emotion_to_dict
from .fingerprint import generate_fingerprint_svg, get_team_color

router = APIRouter(prefix="/personality", tags=["Personality"])


class OceanUpdateRequest(BaseModel):
    openness: Optional[float] = None
    conscientiousness: Optional[float] = None
    extraversion: Optional[float] = None
    agreeableness: Optional[float] = None
    neuroticism: Optional[float] = None


class EmotionUpdateRequest(BaseModel):
    pleasure: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0


def _profile_to_dict(mgr, code, p) -> dict:
    """PersonalityProfile → API 응답 dict"""
    return {
        "agent": p.agent,
        "name": p.name,
        "role": p.role,
        "team": p.team,
        "mbti": p.mbti,
        "ocean": _ocean_to_dict(p.ocean),
        "emotion": _emotion_to_dict(p.emotion),
        "emotion_label": mgr.get_emotion_label(code),
        "speech_style": p.speech_style,
        "tone": p.tone,
        "voice_id": p.voice_id,
        "base_rate": p.base_rate,
        "base_pitch": p.base_pitch,
    }


@router.get("/profiles")
async def list_profiles():
    mgr = get_personality_manager()
    profiles = mgr.get_all_profiles()
    result = {}
    for code, p in profiles.items():
        result[code] = _profile_to_dict(mgr, code, p)
    return {"profiles": result}


@router.get("/profiles/{agent}")
async def get_profile(agent: str):
    mgr = get_personality_manager()
    p = mgr.get_profile(agent)
    if not p:
        raise HTTPException(404, "에이전트를 찾을 수 없습니다")
    return _profile_to_dict(mgr, agent, p)


@router.get("/profiles/{agent}/fingerprint")
async def get_fingerprint(agent: str):
    """에이전트의 Neural Fingerprint SVG 반환"""
    mgr = get_personality_manager()
    p = mgr.get_profile(agent)
    if not p:
        raise HTTPException(404, "에이전트를 찾을 수 없습니다")
    team_color = get_team_color(p.team)
    svg = generate_fingerprint_svg(p, team_color)
    return Response(content=svg, media_type="image/svg+xml")


@router.patch("/profiles/{agent}/ocean")
async def update_ocean(agent: str, req: OceanUpdateRequest):
    mgr = get_personality_manager()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    result = mgr.update_ocean(agent, **updates)
    if not result:
        raise HTTPException(404, "에이전트를 찾을 수 없습니다")
    return {"success": True, "ocean": _ocean_to_dict(result.ocean)}


@router.patch("/profiles/{agent}/emotion")
async def update_emotion(agent: str, req: EmotionUpdateRequest):
    mgr = get_personality_manager()
    result = mgr.update_emotion(agent, req.pleasure, req.arousal, req.dominance)
    if not result:
        raise HTTPException(404, "에이전트를 찾을 수 없습니다")
    return {
        "success": True,
        "emotion": _emotion_to_dict(result.emotion),
        "label": mgr.get_emotion_label(agent),
    }
