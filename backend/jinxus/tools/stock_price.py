"""주식/코인 시세 조회 도구 - Yahoo Finance + CoinGecko (API 키 불필요)"""
import logging

import httpx

from .base import JinxTool, ToolResult

logger = logging.getLogger("jinxus.tools.stock_price")

# 자주 쓰는 코인 ID 단축키 (CoinGecko ID)
COIN_ALIASES: dict[str, str] = {
    "btc": "bitcoin", "bitcoin": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum",
    "sol": "solana", "solana": "solana",
    "bnb": "binancecoin",
    "xrp": "ripple",
    "ada": "cardano",
    "doge": "dogecoin",
    "dot": "polkadot",
    "matic": "matic-network",
    "avax": "avalanche-2",
    "link": "chainlink",
    "ltc": "litecoin",
}

# 한국 주식 단축키 (티커)
KR_STOCK_ALIASES: dict[str, str] = {
    "삼성": "005930.KS",
    "삼성전자": "005930.KS",
    "sk하이닉스": "000660.KS",
    "카카오": "035720.KS",
    "네이버": "035420.KS",
    "lg에너지": "373220.KS",
    "현대차": "005380.KS",
    "셀트리온": "068270.KS",
}


class StockPrice(JinxTool):
    """주식/코인 시세 조회 도구"""

    name = "stock_price"
    description = (
        "주식(국내/미국) 및 암호화폐 시세를 조회합니다. "
        "예: 'AAPL', 'TSLA', '삼성전자', 'BTC', 'ETH'"
    )
    allowed_agents = []  # 모든 에이전트 허용
    input_schema = {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "조회할 심볼 목록. "
                    "주식: 'AAPL', 'TSLA', '005930.KS', '삼성전자' / "
                    "코인: 'BTC', 'ETH', 'SOL'"
                )
            },
            "currency": {
                "type": "string",
                "description": "코인 시세 통화 (기본: krw, 선택: usd)",
                "default": "krw"
            }
        },
        "required": ["symbols"]
    }

    async def run(self, input_data: dict) -> ToolResult:
        self._start_timer()

        symbols: list[str] = input_data.get("symbols", [])
        currency = input_data.get("currency", "krw").lower()

        if not symbols:
            return ToolResult(
                success=False,
                output=None,
                error="symbols 목록이 필요합니다",
                duration_ms=self._get_duration_ms(),
            )

        coins = []
        stocks = []

        for sym in symbols:
            sym_lower = sym.lower()
            if sym_lower in COIN_ALIASES or sym_lower in [v for v in COIN_ALIASES.values()]:
                coins.append(sym_lower)
            else:
                stocks.append(sym)

        results = []
        errors = []

        # 코인 조회 (CoinGecko)
        if coins:
            try:
                coin_results = await self._fetch_coins(coins, currency)
                results.extend(coin_results)
            except Exception as e:
                logger.warning(f"코인 시세 조회 실패: {e}")
                errors.append({"type": "coin", "error": str(e)})

        # 주식 조회 (Yahoo Finance)
        if stocks:
            for sym in stocks:
                try:
                    stock_result = await self._fetch_stock(sym)
                    results.append(stock_result)
                except Exception as e:
                    logger.warning(f"주식 시세 조회 실패 ({sym}): {e}")
                    errors.append({"symbol": sym, "error": str(e)})

        if not results and errors:
            return ToolResult(
                success=False,
                output=None,
                error=f"모든 조회 실패: {errors}",
                duration_ms=self._get_duration_ms(),
            )

        # 요약 텍스트 생성
        lines = []
        for r in results:
            if r.get("type") == "coin":
                cur_sym = "₩" if currency == "krw" else "$"
                price = r.get("price", 0)
                change = r.get("change_24h", 0)
                change_str = f"+{change:.2f}%" if change >= 0 else f"{change:.2f}%"
                lines.append(f"{r['name']} ({r['symbol'].upper()}): {cur_sym}{price:,.0f} ({change_str} 24h)")
            elif r.get("type") == "stock":
                price = r.get("price", 0)
                change = r.get("change_pct", 0)
                change_str = f"+{change:.2f}%" if change >= 0 else f"{change:.2f}%"
                currency_sym = r.get("currency_sym", "$")
                lines.append(f"{r['name']} ({r['symbol']}): {currency_sym}{price:,.2f} ({change_str})")

        return ToolResult(
            success=True,
            output={
                "results": results,
                "summary": "\n".join(lines),
                "errors": errors,
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _fetch_coins(self, coins: list[str], currency: str) -> list[dict]:
        """CoinGecko API로 코인 시세 조회"""
        # 코인 ID 변환
        coin_ids = []
        id_map = {}  # id → original symbol
        for c in coins:
            coin_id = COIN_ALIASES.get(c, c)
            coin_ids.append(coin_id)
            id_map[coin_id] = c

        ids_str = ",".join(set(coin_ids))
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": ids_str,
            "vs_currencies": currency,
            "include_24hr_change": "true",
            "include_market_cap": "true",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = []
        for coin_id, prices in data.items():
            results.append({
                "type": "coin",
                "symbol": coin_id,
                "name": coin_id.replace("-", " ").title(),
                "price": prices.get(currency, 0),
                "change_24h": prices.get(f"{currency}_24h_change", 0),
                "market_cap": prices.get(f"{currency}_market_cap", 0),
                "currency": currency.upper(),
            })
        return results

    async def _fetch_stock(self, symbol: str) -> dict:
        """Yahoo Finance API로 주식 시세 조회"""
        # 한국 주식 별칭 변환
        ticker = KR_STOCK_ALIASES.get(symbol.lower(), symbol.upper())
        if not ticker.endswith(".KS") and not ticker.endswith(".KQ") and not ticker.isalpha():
            ticker = symbol  # 그대로 사용

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {"interval": "1d", "range": "5d"}
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice", 0)
        prev_close = meta.get("previousClose") or meta.get("chartPreviousClose", price)
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0
        curr = meta.get("currency", "USD")
        currency_sym = "₩" if curr in ("KRW", "KRW=X") else "$"

        return {
            "type": "stock",
            "symbol": ticker,
            "name": meta.get("shortName") or meta.get("symbol", ticker),
            "price": price,
            "prev_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "currency": curr,
            "currency_sym": currency_sym,
            "market_state": meta.get("marketState", ""),
            "exchange": meta.get("exchangeName", ""),
        }
