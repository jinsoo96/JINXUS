"""WaveNoter 세션 관리

Google이 headless Playwright 로그인을 차단하기 때문에,
수동으로 한 번 로그인 후 Firebase 토큰을 저장하는 방식.

사용법:
  1. 아무 브라우저에서 https://app.wavenote.ai 접속 + Google 로그인
  2. 개발자 도구(F12) → Console에서 아래 실행:

     copy(JSON.stringify({
       apiKey: firebase.app().options.apiKey,
       ...JSON.parse(Object.entries(localStorage).find(([k])=>k.startsWith('firebase:authUser:'))?.[1] || '{}')
     }))

  3. 클립보드 내용을 이 스크립트에 붙여넣기:
     python3 wavenote_login.py --paste

  또는 간단하게:
  4. Console에서 localStorage 중 firebase auth 토큰 키-값 확인 후
     python3 wavenote_login.py --token <refreshToken>

자동 갱신:
  JX_SECRETARY 루틴이 실행될 때 refreshToken으로 idToken을 자동 갱신.
  refreshToken은 만료되지 않으므로 (Google 정책 변경/비밀번호 변경 시에만 만료)
  한 번 저장하면 계속 사용 가능.
"""
import argparse
import json
import os
import sys

import requests

SESSION_DIR = "/home/jinsookim/.wavenote-session"
AUTH_FILE = os.path.join(SESSION_DIR, "firebase_auth.json")

# WaveNoter Firebase API Key
FIREBASE_API_KEY = "AIzaSyCk57IdQReret2B66tvp1sXVkM6jfBMgOQ"


def refresh_id_token(refresh_token: str) -> dict:
    """refreshToken으로 새 idToken 발급"""
    url = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
    resp = requests.post(url, data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    })
    if resp.status_code == 200:
        data = resp.json()
        return {
            "id_token": data["id_token"],
            "refresh_token": data["refresh_token"],
            "user_id": data["user_id"],
            "expires_in": data["expires_in"],
        }
    else:
        print(f"토큰 갱신 실패: {resp.status_code}")
        print(resp.json())
        return {}


def save_token(refresh_token: str):
    """refreshToken 저장 + idToken 갱신 테스트"""
    os.makedirs(SESSION_DIR, exist_ok=True)

    result = refresh_id_token(refresh_token)
    if not result:
        print("❌ 유효하지 않은 refreshToken")
        return False

    auth_data = {
        "refresh_token": result["refresh_token"],
        "id_token": result["id_token"],
        "user_id": result["user_id"],
        "api_key": FIREBASE_API_KEY,
    }

    with open(AUTH_FILE, "w") as f:
        json.dump(auth_data, f, indent=2)

    print(f"✅ Firebase 인증 저장 완료: {AUTH_FILE}")
    print(f"   user_id: {result['user_id']}")
    print(f"   idToken 만료: {result['expires_in']}초")
    print(f"   refreshToken은 자동 갱신됩니다")
    return True


def save_paste(json_str: str):
    """브라우저 Console에서 복사한 JSON 저장"""
    os.makedirs(SESSION_DIR, exist_ok=True)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        print("❌ 유효한 JSON이 아닙니다")
        return False

    refresh_token = data.get("stsTokenManager", {}).get("refreshToken") or data.get("refreshToken", "")
    if not refresh_token:
        print("❌ refreshToken이 없습니다")
        print(f"   받은 키: {list(data.keys())}")
        return False

    return save_token(refresh_token)


def load_auth() -> dict | None:
    """저장된 인증 정보 로드 (다른 모듈에서 import해서 사용)"""
    if not os.path.exists(AUTH_FILE):
        return None
    with open(AUTH_FILE) as f:
        return json.load(f)


def get_valid_id_token() -> str | None:
    """유효한 idToken 반환 (필요 시 자동 갱신)"""
    auth = load_auth()
    if not auth:
        return None

    result = refresh_id_token(auth["refresh_token"])
    if not result:
        return None

    # 갱신된 토큰 저장
    auth["id_token"] = result["id_token"]
    auth["refresh_token"] = result["refresh_token"]
    with open(AUTH_FILE, "w") as f:
        json.dump(auth, f, indent=2)

    return result["id_token"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WaveNoter Firebase 인증 관리")
    parser.add_argument("--token", help="Firebase refreshToken 직접 입력")
    parser.add_argument("--paste", action="store_true", help="브라우저 Console JSON 붙여넣기")
    parser.add_argument("--check", action="store_true", help="현재 저장된 인증 상태 확인")
    args = parser.parse_args()

    if args.check:
        auth = load_auth()
        if auth:
            print(f"✅ 인증 파일 존재: {AUTH_FILE}")
            print(f"   user_id: {auth.get('user_id')}")
            token = get_valid_id_token()
            if token:
                print(f"   idToken 갱신 성공 (유효)")
            else:
                print(f"   ❌ idToken 갱신 실패 (refreshToken 만료)")
        else:
            print(f"❌ 인증 파일 없음: {AUTH_FILE}")
    elif args.token:
        save_token(args.token)
    elif args.paste:
        print("브라우저 Console에서 복사한 JSON을 붙여넣고 Enter 후 Ctrl+D:")
        json_str = sys.stdin.read().strip()
        save_paste(json_str)
    else:
        parser.print_help()
        print("\n빠른 시작:")
        print("  1. 브라우저에서 https://app.wavenote.ai 로그인")
        print("  2. F12 → Console → 아래 실행:")
        print('     JSON.parse(Object.entries(localStorage).find(([k])=>k.startsWith("firebase:authUser:"))?.[1] || "{}").stsTokenManager.refreshToken')
        print("  3. 출력된 토큰 복사 후:")
        print("     python3 wavenote_login.py --token <refreshToken>")
