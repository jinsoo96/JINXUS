"""TTS API 라우터"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from .engine import get_tts_engine, VoiceProfile, KO_VOICES

router = APIRouter(prefix="/tts", tags=["TTS"])

class SpeakRequest(BaseModel):
    text: str
    agent: str = ""
    emotion: str = "neutral"

class VoiceProfileRequest(BaseModel):
    agent: str
    voice_id: str = "ko-KR-SunHiNeural"
    speed: str = "+0%"
    pitch: str = "+0Hz"

@router.post("/speak")
async def speak(req: SpeakRequest):
    """텍스트 -> 음성 합성 (MP3 바이너리 반환)"""
    engine = get_tts_engine()
    result = await engine.speak(req.text, req.agent, req.emotion)
    if not result.audio_data:
        raise HTTPException(500, "음성 합성 실패")
    return Response(
        content=result.audio_data,
        media_type="audio/mpeg",
        headers={"X-TTS-Cached": str(result.cached).lower()}
    )

@router.get("/voices")
async def list_voices():
    """한국어 보이스 목록"""
    engine = get_tts_engine()
    voices = await engine.get_available_voices()
    return {"voices": voices, "presets": KO_VOICES}

@router.get("/profiles")
async def list_profiles():
    """에이전트별 음성 프로필"""
    engine = get_tts_engine()
    profiles = engine.get_all_profiles()
    return {"profiles": {k: {"voice_id": v.voice_id, "speed": v.speed, "pitch": v.pitch} for k, v in profiles.items()}}

@router.post("/profiles")
async def set_profile(req: VoiceProfileRequest):
    """에이전트 음성 프로필 설정"""
    engine = get_tts_engine()
    profile = VoiceProfile(agent=req.agent, voice_id=req.voice_id, speed=req.speed, pitch=req.pitch)
    engine.set_profile(req.agent, profile)
    return {"success": True}
