"""날씨 조회 도구 - OpenWeatherMap API 기반"""
import logging
from typing import Optional
from datetime import datetime, timedelta

import httpx

from .base import JinxTool, ToolResult
from jinxus.config import get_settings

logger = logging.getLogger("jinxus.tools.weather")

# 서울 주요 지역 좌표
SEOUL_DISTRICTS = {
    "종로구": (37.5735, 126.9790),
    "중구": (37.5641, 126.9979),
    "용산구": (37.5326, 126.9910),
    "성동구": (37.5636, 127.0369),
    "광진구": (37.5384, 127.0822),
    "동대문구": (37.5744, 127.0396),
    "중랑구": (37.6063, 127.0928),
    "성북구": (37.5894, 127.0167),
    "강북구": (37.6396, 127.0257),
    "도봉구": (37.6688, 127.0471),
    "노원구": (37.6542, 127.0568),
    "은평구": (37.6027, 126.9291),
    "서대문구": (37.5791, 126.9368),
    "마포구": (37.5664, 126.9018),
    "양천구": (37.5170, 126.8666),
    "강서구": (37.5510, 126.8495),
    "구로구": (37.4955, 126.8876),
    "금천구": (37.4569, 126.8955),
    "영등포구": (37.5264, 126.8963),
    "동작구": (37.5124, 126.9393),
    "관악구": (37.4781, 126.9516),
    "서초구": (37.4837, 127.0324),
    "강남구": (37.4979, 127.0276),
    "송파구": (37.5146, 127.1066),
    "강동구": (37.5301, 127.1238),
    # 기본값
    "서울": (37.5665, 126.9780),
}

# 하늘 상태 이모지
WEATHER_EMOJI = {
    "clear sky": "☀️",
    "few clouds": "🌤️",
    "scattered clouds": "⛅",
    "broken clouds": "☁️",
    "overcast clouds": "☁️",
    "shower rain": "🌧️",
    "rain": "🌧️",
    "light rain": "🌦️",
    "thunderstorm": "⛈️",
    "snow": "❄️",
    "mist": "🌫️",
}


class WeatherTool(JinxTool):
    """OpenWeatherMap 기반 날씨 조회 도구"""

    name = "weather"
    description = "날씨 예보를 조회합니다 (서울 구별 지원)"
    allowed_agents = []
    input_schema = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "지역명 (예: '종로구', '강남구', '서울')",
                "default": "서울"
            },
            "mode": {
                "type": "string",
                "description": "조회 모드: 'current'(현재) 또는 'forecast'(예보)",
                "enum": ["current", "forecast"],
                "default": "forecast"
            }
        },
        "required": []
    }

    def __init__(self):
        super().__init__()
        settings = get_settings()
        self._api_key = settings.openweathermap_api_key

    async def run(self, input_data: dict) -> ToolResult:
        self._start_timer()

        if not self._api_key:
            return ToolResult(
                success=False,
                output=None,
                error="OPENWEATHERMAP_API_KEY가 설정되지 않았습니다",
                duration_ms=self._get_duration_ms(),
            )

        location = input_data.get("location", "서울")
        mode = input_data.get("mode", "forecast")

        # 좌표 매핑
        lat, lon = self._get_coordinates(location)

        try:
            if mode == "current":
                result = await self._get_current(lat, lon, location)
            else:
                result = await self._get_forecast(lat, lon, location)

            return ToolResult(
                success=True,
                output=result,
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            logger.error(f"날씨 조회 실패: {e}")
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    def _get_coordinates(self, location: str) -> tuple[float, float]:
        """지역명 → 좌표 변환"""
        # 정확한 매칭
        if location in SEOUL_DISTRICTS:
            return SEOUL_DISTRICTS[location]

        # 부분 매칭 (예: "종로" → "종로구")
        for name, coords in SEOUL_DISTRICTS.items():
            if location in name or name in location:
                return coords

        # 기본값: 서울 중심
        return SEOUL_DISTRICTS["서울"]

    async def _get_current(self, lat: float, lon: float, location: str) -> dict:
        """현재 날씨 조회"""
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "lat": lat, "lon": lon,
            "appid": self._api_key,
            "units": "metric",
            "lang": "kr",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        weather_desc = data["weather"][0]["description"]
        emoji = self._get_emoji(data["weather"][0].get("main", ""))

        return {
            "location": location,
            "type": "current",
            "temperature": data["main"]["temp"],
            "feels_like": data["main"]["feels_like"],
            "humidity": data["main"]["humidity"],
            "weather": weather_desc,
            "emoji": emoji,
            "wind_speed": data["wind"]["speed"],
            "summary": f"{emoji} {location} 현재 날씨: {weather_desc}, {data['main']['temp']}°C (체감 {data['main']['feels_like']}°C), 습도 {data['main']['humidity']}%",
        }

    async def _get_forecast(self, lat: float, lon: float, location: str) -> dict:
        """5일 예보 (3시간 간격) → 내일 날씨 중심으로 정리"""
        url = "https://api.openweathermap.org/data/2.5/forecast"
        params = {
            "lat": lat, "lon": lon,
            "appid": self._api_key,
            "units": "metric",
            "lang": "kr",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        now = datetime.now()
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        today_str = now.strftime("%Y-%m-%d")

        # 오늘 남은 시간 + 내일 예보
        today_forecasts = []
        tomorrow_forecasts = []

        for item in data["list"]:
            dt_txt = item["dt_txt"]
            date_str = dt_txt.split(" ")[0]

            forecast_entry = {
                "time": dt_txt.split(" ")[1][:5],
                "temp": item["main"]["temp"],
                "feels_like": item["main"]["feels_like"],
                "weather": item["weather"][0]["description"],
                "humidity": item["main"]["humidity"],
                "pop": round(item.get("pop", 0) * 100),
                "wind_speed": item["wind"]["speed"],
            }

            if date_str == today_str:
                today_forecasts.append(forecast_entry)
            elif date_str == tomorrow:
                tomorrow_forecasts.append(forecast_entry)

        # 내일 최저/최고 기온
        if tomorrow_forecasts:
            temps = [f["temp"] for f in tomorrow_forecasts]
            temp_min = min(temps)
            temp_max = max(temps)
            # 대표 날씨 (낮 12시~15시 기준, 없으면 전체 중 가장 많은)
            day_weather = "맑음"
            for f in tomorrow_forecasts:
                if f["time"] in ("12:00", "15:00"):
                    day_weather = f["weather"]
                    break
            avg_pop = round(sum(f["pop"] for f in tomorrow_forecasts) / len(tomorrow_forecasts))
        else:
            temp_min = temp_max = 0
            day_weather = "정보 없음"
            avg_pop = 0

        tomorrow_date = (now + timedelta(days=1)).strftime("%m월 %d일")
        emoji = self._get_emoji(day_weather)

        summary = f"{emoji} {location} 내일({tomorrow_date}) 날씨: {day_weather}\n"
        summary += f"최저 {temp_min}°C / 최고 {temp_max}°C, 강수확률 {avg_pop}%"

        return {
            "location": location,
            "type": "forecast",
            "tomorrow_date": tomorrow,
            "temp_min": temp_min,
            "temp_max": temp_max,
            "weather": day_weather,
            "avg_pop": avg_pop,
            "emoji": emoji,
            "hourly": tomorrow_forecasts,
            "today_remaining": today_forecasts,
            "summary": summary,
        }

    @staticmethod
    def _get_emoji(weather: str) -> str:
        weather_lower = weather.lower()
        for key, emoji in WEATHER_EMOJI.items():
            if key in weather_lower:
                return emoji
        if "맑" in weather:
            return "☀️"
        if "구름" in weather:
            return "☁️"
        if "비" in weather or "rain" in weather_lower:
            return "🌧️"
        if "눈" in weather or "snow" in weather_lower:
            return "❄️"
        return "🌤️"
