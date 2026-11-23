"""Single administrator login, revocable sessions, and login throttling."""
from collections import defaultdict, deque
import time

from pydantic import BaseModel, ConfigDict, Field

COOKIE_NAME = "batch_session"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256, repr=False)


class HistoryEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    archived: bool | None = None


class LoginLimiter:
    def __init__(self):
        self.attempts = defaultdict(deque)

    def allow(self, host):
        now = time.monotonic()
        # Bound memory even if this service is exposed directly to the internet.
        for key in list(self.attempts):
            queue = self.attempts[key]
            while queue and queue[0] <= now - 900:
                queue.popleft()
            if not queue:
                del self.attempts[key]
        queue = self.attempts[host]
        if len(queue) >= 10 or sum(map(len, self.attempts.values())) >= 100:
            return False
        queue.append(now)
        return True

    def clear(self, host):
        self.attempts.pop(host, None)
