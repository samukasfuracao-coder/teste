"""Retry a collection hold if the prompt remains after a full hold window."""


class CollectionHold:
    def __init__(self, interval=8.0, release_time=0.2, max_retries=3):
        self.interval = interval
        self.release_time = release_time
        self.max_retries = max_retries
        self.reset()

    def reset(self):
        self.started = None
        self.release_until = None
        self.retries = 0

    def step(self, now, requested, prompt_visible):
        if not requested:
            self.reset()
            return False, False
        if self.started is None:
            self.started = now
        if self.release_until is not None:
            if now < self.release_until:
                return False, False
            self.release_until = None
            self.started = now
        if (prompt_visible and now - self.started >= self.interval
                and self.retries < self.max_retries):
            self.retries += 1
            self.release_until = now + self.release_time
            return False, True
        return True, False
