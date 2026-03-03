from .chat import router as chat_router
from .task import router as task_router
from .feedback import router as feedback_router
from .agents import router as agents_router
from .memory import router as memory_router
from .status import router as status_router
from .improve import router as improve_router
from .logs import router as logs_router
from .hr import router as hr_router

__all__ = [
    "chat_router",
    "task_router",
    "feedback_router",
    "agents_router",
    "memory_router",
    "status_router",
    "improve_router",
    "logs_router",
    "hr_router",
]
