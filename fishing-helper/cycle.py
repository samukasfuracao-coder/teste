"""Fishing cycle timing, independent of screen capture and input devices."""
from dataclasses import dataclass


@dataclass
class Decision:
    phase: str
    action: str = ''
    hold_t: bool = False
    reason: str = ''


class FishingCycle:
    def __init__(self, cast_timeout=45, collect_wait=12, collect_timeout=45):
        self.cast_timeout = cast_timeout
        self.collect_wait = collect_wait
        self.collect_timeout = collect_timeout
        self.reset()

    def reset(self):
        self.phase = 'idle'
        self.since = 0.0
        self.next_cast = 0.0
        self.last_bar = 0.0
        self.last_sequence = -1
        self.negative_since = None
        self.negative_count = 0
        self.stale_since = None

    def step(self, now, bar, stamp=0.0, sequence=0, visible=False):
        fresh = stamp > 0 and 0 <= now - stamp <= 5
        new = fresh and sequence != self.last_sequence
        if new:
            self.last_sequence = sequence

        if bar:
            self.phase = 'fishing'
            self.last_bar = now
            self.negative_since = None
            self.negative_count = 0
            self.stale_since = None
            return Decision(self.phase)

        if self.phase == 'fishing':
            self.phase = 'waiting_collect'
            self.since = now

        # Ignore OCR observations captured before the last visible minigame.
        relevant = fresh and stamp >= self.last_bar
        if relevant and visible:
            if self.phase != 'collecting':
                self.phase = 'collecting'
                self.since = now
            self.negative_since = None
            self.negative_count = 0

        if self.phase == 'collecting':
            if now - self.since >= self.collect_timeout:
                return Decision(self.phase, 'pause', reason=f'Coleta não terminou em {self.collect_timeout} segundos.')
            if not relevant:
                if self.stale_since is None:
                    self.stale_since = now
                if now - self.stale_since >= 10:
                    return Decision(self.phase, 'pause', reason='OCR sem atualização durante a coleta.')
                return Decision(self.phase, hold_t=False, reason='Aguardando OCR atualizar.')
            self.stale_since = None
            if new and not visible:
                if self.negative_since is None:
                    self.negative_since = stamp
                self.negative_count += 1
                if (self.negative_count >= 3
                        and stamp - self.negative_since >= 1.5
                        and now - self.since >= 1.0):
                    self.phase = 'cooldown'
                    self.since = now
                    self.next_cast = now + 1.5
                    return Decision(self.phase, 'collection_done')
            # A brief OCR miss must not interrupt a hold-to-collect action.
            return Decision(self.phase, hold_t=True)

        if self.phase == 'waiting_collect':
            if now - self.since >= self.collect_wait:
                if relevant and not visible and stamp >= self.since:
                    self.phase = 'cooldown'
                    self.since = now
                    self.next_cast = now + 1.5
                    return Decision(self.phase, 'no_collection')
                if now - self.since >= self.collect_wait + 10:
                    return Decision(self.phase, 'pause', reason='Sem leitura recente para confirmar o fim da pesca.')
            return Decision(self.phase)

        if self.phase == 'waiting':
            if now - self.since >= self.cast_timeout:
                if relevant and not visible:
                    self.phase = 'cooldown'
                    self.since = now
                    self.next_cast = now + 1.5
                    return Decision(self.phase, 'retry')
                if now - self.since >= self.cast_timeout + 10:
                    return Decision(self.phase, 'pause', reason='Sem leitura recente para repetir o lançamento.')
            return Decision(self.phase)

        if self.phase == 'idle' or (
                self.phase == 'cooldown' and now >= self.next_cast
                and relevant and not visible and stamp >= self.since):
            if not (fresh and visible):
                self.phase = 'waiting'
                self.since = now
                return Decision(self.phase, 'cast')
        return Decision(self.phase)


class JumpTimer:
    def __init__(self, now):
        self.last_jump = now

    def due(self, now, interval, active, focused, safe):
        return (interval > 0 and active and focused and safe
                and now - self.last_jump >= interval)

    def performed(self, now):
        self.last_jump = now
