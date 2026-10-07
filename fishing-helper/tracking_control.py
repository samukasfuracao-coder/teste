"""Bounded prediction for a binary, hold-to-rise fishing control."""
import math


def track_step(center, block_height, top, bottom, timestamp, previous,
               velocity, held, lookahead):
    target = (top + bottom) / 2
    clearance = max(0, (bottom - top - block_height) / 2)
    target_velocity = 0.0
    if previous is not None:
        py, old_target, old_time = previous
        dt = timestamp - old_time
        # A large jump or stale frame is not a usable velocity measurement.
        if 0.004 <= dt <= 0.15 and abs(center - py) <= max(block_height * 2, 8):
            limit = max(block_height * 25, 100)
            measured = max(-limit, min(limit, (center - py) / dt))
            velocity += (1 - math.exp(-dt / 0.035)) * (measured - velocity)
            target_velocity = max(-limit, min(limit, (target - old_target) / dt))
        else:
            velocity = 0.0
    else:
        velocity = 0.0
    # Never let prediction move the desired correction outside the safe zone.
    prediction_limit = max(1, min(block_height * 0.6, clearance * 0.7))
    lead = max(-prediction_limit, min(prediction_limit,
               (velocity - target_velocity * 0.3) * min(lookahead, 0.12)))
    error = center + lead - target
    band = max(0.7, clearance * 0.12)
    want = error > band or (held and error >= -band)
    # Real boundary crossings take precedence over velocity estimates.
    if center - block_height / 2 < top:
        want = False
    elif center + block_height / 2 > bottom:
        want = True
    return want, (center, target, timestamp), velocity
