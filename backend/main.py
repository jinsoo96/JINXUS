"""JINXUS - 진수의 AI 비서 시스템

Just Intelligent Nexus, eXecutes Under Supremacy
"명령만 해. 나머지는 내가 다 한다."
"""
import uvicorn
from dotenv import load_dotenv

from jinxus.config import get_settings
from jinxus.api import app

# 환경 변수 로드
load_dotenv()


def main():
    """메인 진입점"""
    settings = get_settings()

    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║      ██╗██╗███╗   ██╗██╗  ██╗██╗   ██╗███████╗           ║
    ║      ██║██║████╗  ██║╚██╗██╔╝██║   ██║██╔════╝           ║
    ║      ██║██║██╔██╗ ██║ ╚███╔╝ ██║   ██║███████╗           ║
    ║ ██   ██║██║██║╚██╗██║ ██╔██╗ ██║   ██║╚════██║           ║
    ║ ╚█████╔╝██║██║ ╚████║██╔╝ ██╗╚██████╔╝███████║           ║
    ║  ╚════╝ ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝           ║
    ║                                                           ║
    ║         Just Intelligent Nexus,                           ║
    ║         eXecutes Under Supremacy                          ║
    ║                                                           ║
    ║         "명령만 해. 나머지는 내가 다 한다."                    ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)

    print(f"Starting JINXUS server on http://{settings.jinxus_host}:{settings.jinxus_port}")
    print(f"API docs: http://{settings.jinxus_host}:{settings.jinxus_port}/docs")
    print()

    uvicorn.run(
        "jinxus.api:app",
        host=settings.jinxus_host,
        port=settings.jinxus_port,
        reload=settings.jinxus_debug,
    )


if __name__ == "__main__":
    main()
