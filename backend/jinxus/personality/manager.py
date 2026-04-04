"""PersonalityManager — agethos 기반 에이전트 인격 관리

각 에이전트의 OCEAN 성격, 감정 상태, 말투 스타일을 관리하고
TTS 감정 파라미터와 연동한다.
"""
import logging
from typing import Optional, Dict
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# agethos가 설치되어 있으면 PersonaSpec 사용, 없으면 자체 데이터클래스로 fallback
try:
    from agethos.models import OceanTraits, EmotionalState
    HAS_AGETHOS = True
except ImportError:
    HAS_AGETHOS = False

    @dataclass
    class OceanTraits:
        openness: float = 0.5
        conscientiousness: float = 0.5
        extraversion: float = 0.5
        agreeableness: float = 0.5
        neuroticism: float = 0.5

    @dataclass
    class EmotionalState:
        pleasure: float = 0.0
        arousal: float = 0.0
        dominance: float = 0.0


def _ocean_to_dict(ocean) -> dict:
    """OceanTraits → dict (agethos pydantic / fallback dataclass 모두 지원)"""
    if hasattr(ocean, "model_dump"):
        return ocean.model_dump()
    return asdict(ocean)


def _emotion_to_dict(emotion) -> dict:
    """EmotionalState → dict (agethos pydantic / fallback dataclass 모두 지원)"""
    if hasattr(emotion, "model_dump"):
        # EMOTION_MAP 등 class var 제외
        return {
            "pleasure": emotion.pleasure,
            "arousal": emotion.arousal,
            "dominance": emotion.dominance,
        }
    return asdict(emotion)


@dataclass
class PersonalityProfile:
    agent: str
    name: str = ""
    role: str = ""
    team: str = ""
    mbti: str = ""
    ocean: object = None  # OceanTraits (agethos or fallback)
    emotion: object = None  # EmotionalState (agethos or fallback)
    speech_style: str = ""
    tone: str = ""
    values: list = field(default_factory=list)
    voice_id: str = "ko-KR-SunHiNeural"
    base_rate: str = "+0%"
    base_pitch: str = "+0Hz"

    def __post_init__(self):
        if self.ocean is None:
            self.ocean = OceanTraits()
        if self.emotion is None:
            self.emotion = EmotionalState()


def _make_ocean(o, c, e, a, n):
    return OceanTraits(openness=o, conscientiousness=c, extraversion=e, agreeableness=a, neuroticism=n)


# MBTI → OCEAN 기본 매핑 (심리학 연구 기반)
# McCrae & Costa (1989): MBTI-Big Five 상관관계
MBTI_OCEAN = {
    # (O, C, E, A, N)
    "INTJ": (0.75, 0.85, 0.25, 0.35, 0.30),
    "INTP": (0.85, 0.50, 0.30, 0.45, 0.40),
    "ENTJ": (0.70, 0.85, 0.80, 0.30, 0.25),
    "ENTP": (0.90, 0.45, 0.75, 0.40, 0.35),
    "INFJ": (0.80, 0.75, 0.35, 0.80, 0.45),
    "INFP": (0.90, 0.45, 0.30, 0.75, 0.55),
    "ENFJ": (0.70, 0.75, 0.85, 0.85, 0.35),
    "ENFP": (0.90, 0.40, 0.85, 0.70, 0.40),
    "ISTJ": (0.35, 0.90, 0.30, 0.50, 0.30),
    "ISFJ": (0.40, 0.85, 0.35, 0.80, 0.40),
    "ESTJ": (0.35, 0.90, 0.75, 0.40, 0.25),
    "ESFJ": (0.40, 0.80, 0.80, 0.85, 0.35),
    "ISTP": (0.55, 0.55, 0.30, 0.35, 0.30),
    "ISFP": (0.70, 0.45, 0.30, 0.70, 0.50),
    "ESTP": (0.50, 0.40, 0.80, 0.35, 0.30),
    "ESFP": (0.55, 0.35, 0.85, 0.70, 0.35),
}

# 역할 보정값 — MBTI 기본값에 가감
ROLE_OCEAN_ADJUST = {
    "CTO":       (0.05, 0.05, 0.05, -0.05, -0.05),
    "COO":       (0.0,  0.05, 0.10, 0.0,   -0.05),
    "CFO":       (-0.05, 0.10, -0.05, -0.05, 0.0),
    "팀장":      (0.0,  0.05, 0.10, 0.05,  -0.05),
    "실장":      (0.05, 0.05, 0.0,  0.0,   -0.05),
    "백엔드":    (0.0,  0.10, -0.10, 0.0,   -0.05),
    "프론트엔드": (0.10, 0.0,  0.05, 0.05,  0.0),
    "인프라":    (-0.05, 0.10, -0.10, -0.05, 0.05),
    "보안":      (0.0,  0.10, -0.10, -0.10, 0.10),
    "QA":        (-0.05, 0.10, -0.05, -0.10, 0.05),
    "리서치":    (0.10, 0.05, -0.05, 0.05,  0.0),
    "비서":      (-0.05, 0.10, 0.05, 0.15,  -0.10),
    "마케팅":    (0.05, 0.0,  0.10, 0.05,  0.0),
    "PM":        (0.05, 0.05, 0.05, 0.10,  0.0),
}


class PersonalityManager:
    def __init__(self):
        self._profiles: Dict[str, PersonalityProfile] = {}
        self._initialized = False

    def invalidate(self):
        """personas 변경 시 호출 — 다음 접근 시 재초기화"""
        self._initialized = False
        self._profiles.clear()

    def initialize(self):
        """personas.py에서 에이전트 정보를 읽어 프로필 생성 (변경 시 재초기화)"""
        if self._initialized:
            return
        try:
            from jinxus.agents.personas import get_all_personas
            personas = get_all_personas()
            for code, p in personas.items():
                # p는 AgentPersona dataclass — attribute 접근
                role = p.role or ""
                ocean = self._compute_ocean(p.mbti or "", role, code)

                # personas.py의 gender 필드 사용 (single source of truth)
                is_female = getattr(p, 'gender', 'M') == 'F'

                # 보이스 할당 — 한국어 3종 + rate/pitch 변조로 전원 구분
                male_voices = ["ko-KR-InJoonNeural", "ko-KR-HyunsuMultilingualNeural"]
                female_voices = ["ko-KR-SunHiNeural"]
                voice_hash = hash(code) & 0xFFFFFFFF
                if is_female:
                    voice = female_voices[voice_hash % len(female_voices)]
                else:
                    voice = male_voices[voice_hash % len(male_voices)]

                # OCEAN 기반 rate/pitch — 에이전트마다 확실히 다르게
                e_val = ocean.extraversion
                n_val = ocean.neuroticism
                a_val = ocean.agreeableness
                o_val = ocean.openness
                # rate: E 높으면 빠름(-10~+15%), 에이전트 해시로 ±3% 추가 분산
                rate_pct = int((e_val - 0.5) * 30) + (voice_hash % 7 - 3)
                # pitch: N 높으면 높음, A 낮으면 낮음, O 높으면 약간 높음
                pitch_hz = int((n_val - 0.4) * 40 + (1 - a_val) * 15 + (o_val - 0.5) * 10) + (voice_hash % 5 - 2)
                rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"
                pitch_str = f"+{pitch_hz}Hz" if pitch_hz >= 0 else f"{pitch_hz}Hz"

                profile = PersonalityProfile(
                    agent=code,
                    name=p.korean_name,
                    role=role,
                    team=p.team or "",
                    mbti=p.mbti or "",
                    ocean=ocean,
                    speech_style=p.speech_style or "",
                    tone="간결하고 전문적",
                    voice_id=voice,
                    base_rate=rate_str,
                    base_pitch=pitch_str,
                )
                self._profiles[code] = profile
            self._initialized = True
            logger.info(f"[Personality] {len(self._profiles)}명 프로필 초기화 완료")
        except Exception as e:
            logger.error(f"[Personality] 초기화 실패: {e}")

    def _compute_ocean(self, mbti: str, role: str, code: str) -> object:
        """MBTI + 역할 보정으로 에이전트 고유 OCEAN 생성

        1단계: MBTI → 기본 OCEAN (심리학 연구 기반)
        2단계: 역할 보정값 가감
        3단계: 에이전트 코드 해시로 ±0.03 미세 분산 (같은 MBTI+역할이어도 다름)
        """
        # 1) MBTI 기본값
        base = MBTI_OCEAN.get(mbti.upper(), (0.5, 0.5, 0.5, 0.5, 0.5))
        o, c, e, a, n = base

        # 2) 역할 보정
        role_lower = role.lower()
        for key, adj in ROLE_OCEAN_ADJUST.items():
            if key.lower() in role_lower or key.lower() in code.lower():
                o += adj[0]; c += adj[1]; e += adj[2]; a += adj[3]; n += adj[4]
                break

        # 3) 에이전트별 미세 분산 (해시 기반, ±0.03)
        h = hash(code) & 0xFFFFFFFF
        o += ((h % 7) - 3) * 0.01
        c += (((h >> 3) % 7) - 3) * 0.01
        e += (((h >> 6) % 7) - 3) * 0.01
        a += (((h >> 9) % 7) - 3) * 0.01
        n += (((h >> 12) % 7) - 3) * 0.01

        # 클래핑 (0.05 ~ 0.95)
        clamp = lambda v: max(0.05, min(0.95, v))
        return _make_ocean(clamp(o), clamp(c), clamp(e), clamp(a), clamp(n))

    def get_profile(self, agent: str) -> Optional[PersonalityProfile]:
        self.initialize()
        return self._profiles.get(agent)

    def get_all_profiles(self) -> Dict[str, PersonalityProfile]:
        self.initialize()
        return dict(self._profiles)

    def update_ocean(self, agent: str, **kwargs) -> Optional[PersonalityProfile]:
        """OCEAN 값 업데이트"""
        profile = self.get_profile(agent)
        if not profile:
            return None
        for k, v in kwargs.items():
            if hasattr(profile.ocean, k):
                setattr(profile.ocean, k, max(0.0, min(1.0, float(v))))
        return profile

    def update_emotion(self, agent: str, pleasure: float = 0, arousal: float = 0, dominance: float = 0) -> Optional[PersonalityProfile]:
        profile = self.get_profile(agent)
        if not profile:
            return None
        profile.emotion = EmotionalState(
            pleasure=max(-1, min(1, pleasure)),
            arousal=max(-1, min(1, arousal)),
            dominance=max(-1, min(1, dominance)),
        )
        return profile

    def get_emotion_label(self, agent: str) -> str:
        """현재 감정 라벨 (joy/anger/sadness 등)"""
        profile = self.get_profile(agent)
        if not profile:
            return "neutral"
        e = profile.emotion
        # PAD → 감정 매핑 (간단 버전)
        if e.pleasure > 0.3 and e.arousal > 0.3:
            return "excitement"
        if e.pleasure > 0.3:
            return "joy"
        if e.pleasure < -0.3 and e.arousal > 0.3:
            return "anger"
        if e.pleasure < -0.3:
            return "sadness"
        if e.arousal > 0.5:
            return "surprise"
        return "neutral"


# 싱글톤
_manager: Optional[PersonalityManager] = None


def get_personality_manager() -> PersonalityManager:
    global _manager
    if _manager is None:
        _manager = PersonalityManager()
    return _manager
