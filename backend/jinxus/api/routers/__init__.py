from .chat import router as chat_router
from .task import router as task_router
from .feedback import router as feedback_router
from .agents import router as agents_router
from .memory import router as memory_router
from .status import router as status_router
from .improve import router as improve_router
from .logs import router as logs_router
from .hr import router as hr_router
from .plugins import router as plugins_router
from .dev_notes import router as dev_notes_router
from .projects import router as projects_router
from .processes import router as processes_router
from .docker_logs import router as docker_logs_router
from .channel import router as channel_router
from .matrix import router as matrix_router
from .mission import router as mission_router
from .command import router as command_router

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
    "plugins_router",
    "dev_notes_router",
    "projects_router",
    "processes_router",
    "docker_logs_router",
    "channel_router",
    "matrix_router",
    "mission_router",
    "command_router",
]
