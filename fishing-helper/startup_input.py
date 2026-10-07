class StartupShift:
    """One startup opportunity per process; never reset on pause/resume."""
    def __init__(self):
        self.done = False
        self.held = False

    def initialize(self, enabled, active, stopped, focused, release_mouse,
                   release_t, press, release, key):
        if self.done or stopped.is_set() or not active.is_set() or not focused():
            return False
        if not enabled:
            self.done = True
            return False
        release_mouse()
        release_t()
        if stopped.is_set() or not active.is_set() or not focused():
            return False
        try:
            self.held = True
            press(key)
            self.done = True
            stopped.wait(0.06)
        finally:
            release(key)
            self.held = False
        # Let the camera/cursor settle before the first fishing click.
        stopped.wait(0.2)
        return True
