"""Edge TTS 기반 음성 합성 엔진

Geny 패턴 참고 — 감정별 speed/pitch 조절, 스트리밍 합성, 캐시
"""
import edge_tts  # pip install edge-tts
import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# 감정별 음성 파라미터 (Geny의 tts_general_config 패턴)
EMOTION_PARAMS = {
    "neutral": {"rate": "+0%", "pitch": "+0Hz"},
    "joy": {"rate": "+10%", "pitch": "+20Hz"},
    "anger": {"rate": "+5%", "pitch": "-10Hz"},
    "sadness": {"rate": "-15%", "pitch": "-30Hz"},
    "fear": {"rate": "+20%", "pitch": "+10Hz"},
    "surprise": {"rate": "+15%", "pitch": "+30Hz"},
    "calm": {"rate": "-10%", "pitch": "-5Hz"},
    "excitement": {"rate": "+20%", "pitch": "+25Hz"},
}

# 한국어 Edge TTS 보이스 목록 (에이전트별 할당용)
KO_VOICES = {
    "male_1": "ko-KR-InJoonNeural",
    "male_2": "ko-KR-HyunsuNeural",
    "female_1": "ko-KR-SunHiNeural",
    "female_2": "ko-KR-YuJinNeural",
}

@dataclass
class VoiceProfile:
    """에이전트별 음성 프로필"""
    agent: str
    voice_id: str = "ko-KR-SunHiNeural"  # Edge TTS voice
    speed: str = "+0%"
    pitch: str = "+0Hz"

@dataclass
class TTSResult:
    audio_data: bytes
    format: str = "mp3"
    duration_ms: int = 0
    cached: bool = False

class TTSEngine:
    """Edge TTS 기반 음성 합성"""

    def __init__(self, cache_dir: str = "/tmp/jinxus_tts_cache"):
        self._cache_dir = cache_dir
        self._profiles: dict[str, VoiceProfile] = {}
        os.makedirs(cache_dir, exist_ok=True)

    def set_profile(self, agent: str, profile: VoiceProfile):
        self._profiles[agent] = profile

    def get_profile(self, agent: str) -> VoiceProfile:
        return self._profiles.get(agent, VoiceProfile(agent=agent))

    def get_all_profiles(self) -> dict[str, VoiceProfile]:
        return dict(self._profiles)

    def _get_agent_voice(self, agent: str) -> tuple[str, str, str]:
        """에이전트별 voice_id, base_rate, base_pitch를 personality에서 가져오기"""
        try:
            from jinxus.personality.manager import get_personality_manager
            mgr = get_personality_manager()
            p = mgr.get_profile(agent)
            if p:
                return p.voice_id, p.base_rate, p.base_pitch
        except Exception:
            pass
        return "ko-KR-InJoonNeural", "+0%", "+0Hz"

    def _combine_rate_pitch(self, base_rate: str, base_pitch: str, emo_rate: str, emo_pitch: str) -> tuple[str, str]:
        """기본 rate/pitch + 감정 rate/pitch 합산"""
        def parse_val(s: str) -> int:
            s = s.replace("%", "").replace("Hz", "").replace("+", "")
            try:
                return int(s)
            except ValueError:
                return 0
        combined_rate = parse_val(base_rate) + parse_val(emo_rate)
        combined_pitch = parse_val(base_pitch) + parse_val(emo_pitch)
        r = f"+{combined_rate}%" if combined_rate >= 0 else f"{combined_rate}%"
        p = f"+{combined_pitch}Hz" if combined_pitch >= 0 else f"{combined_pitch}Hz"
        return r, p

    async def speak(self, text: str, agent: str = "", emotion: str = "neutral") -> TTSResult:
        """텍스트 -> 음성 합성 (에이전트별 voice + 성격별 rate/pitch + 감정 변조)"""
        # 에이전트별 voice/rate/pitch 가져오기
        voice_id, base_rate, base_pitch = self._get_agent_voice(agent)

        # 감정 파라미터
        emo = EMOTION_PARAMS.get(emotion, EMOTION_PARAMS["neutral"])
        rate, pitch = self._combine_rate_pitch(base_rate, base_pitch, emo["rate"], emo["pitch"])

        # 캐시 키 (voice + rate + pitch 포함)
        cache_key = hashlib.sha256(f"{text}:{voice_id}:{rate}:{pitch}".encode()).hexdigest()[:16]
        cache_path = os.path.join(self._cache_dir, f"{cache_key}.mp3")

        # 캐시 히트
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                return TTSResult(audio_data=f.read(), cached=True)

        # Edge TTS 합성
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice_id,
                rate=rate,
                pitch=pitch,
            )
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]

            # 캐시 저장
            if audio_data:
                with open(cache_path, "wb") as f:
                    f.write(audio_data)

            return TTSResult(audio_data=audio_data)

        except Exception as e:
            logger.error(f"[TTS] 합성 실패: {e}")
            return TTSResult(audio_data=b"")

    async def get_available_voices(self) -> list[dict]:
        """사용 가능한 한국어 보이스 목록"""
        try:
            voices = await edge_tts.list_voices()
            return [v for v in voices if v["Locale"].startswith("ko-KR")]
        except Exception as e:
            logger.error(f"[TTS] 보이스 목록 조회 실패: {e}")
            return []

# 싱글톤
_engine: Optional[TTSEngine] = None

def get_tts_engine() -> TTSEngine:
    global _engine
    if _engine is None:
        _engine = TTSEngine()
    return _engine
