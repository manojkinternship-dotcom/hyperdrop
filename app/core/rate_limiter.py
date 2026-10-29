import time
from collections import deque
from app.config import settings

class ExceptionRateLimiter:
    """In-memory sliding window rate limiter for exception creation."""
    def __init__(self, max_requests: int = settings.EXCEPTION_RATE_LIMIT_PER_MINUTE, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()

    def allow_request(self) -> bool:
        now = time.time()
        # Evict timestamps older than window
        while self.requests and self.requests[0] <= now - self.window_seconds:
            self.requests.popleft()
        
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        return False

rate_limiter = ExceptionRateLimiter()
