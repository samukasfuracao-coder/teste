"""Screen-based fishing controller. F8 toggles; Escape quits."""
import argparse
import ctypes
import sys
import threading
import time

import cv2
import mss
import numpy as np
from pynput import keyboard, mouse


def detect(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    height, width = frame.shape[:2]
    # Restrict white detection to the interior; exclude the pale outer border.
    white = cv2.inRange(hsv, (0, 0, 155), (179, 85, 255))
    margin = max(2, int(width * 0.18))
    white[:, :margin] = 0
    white[:, width - margin:] = 0
    white[:max(2, int(height * 0.02))] = 0
    white[height - 2:] = 0
    candidates = []
    for contour in cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= width * 0.18 and h >= 5 and h <= height * 0.16:
            if cv2.contourArea(contour) >= w * h * 0.45:
                candidates.append((w * h, (x, y, w, h)))
    block = max(candidates, default=(0, None), key=lambda item: item[0])[1]
    # Colored outline remains visible even when the white block overlaps it.
    colored = cv2.inRange(hsv, (18, 95, 110), (90, 255, 255))
    rows = np.flatnonzero(np.count_nonzero(colored, axis=1) >= max(2, width * 0.035))
    groups = np.split(rows, np.flatnonzero(np.diff(rows) > 3) + 1)
    zones = [(int(g[0]), int(g[-1])) for g in groups if len(g) >= 6
             and 8 <= g[-1] - g[0] <= height * 0.25]
    zone = max(zones, key=lambda z: z[1] - z[0], default=None)
    return block, zone


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observe', action='store_true', help='Never send mouse input')
    parser.add_argument('--auto-cast', action='store_true', help='Click to cast and repeat after each minigame')
    parser.add_argument('--fps', type=int, default=60)
    parser.add_argument('--lookahead', type=float, default=0.08)
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('Execute este programa no Windows.')
    if not 1 <= args.fps <= 120 or not 0 <= args.lookahead <= 0.5:
        parser.error('Use fps entre 1 e 120 e lookahead entre 0 e 0.5.')
    ctypes.windll.user32.SetProcessDPIAware()
    active = threading.Event()
    stopped = threading.Event()
    controller = mouse.Controller()
    held = False
    listener = None

    def key_press(key):
        if key == keyboard.Key.esc:
            stopped.set()

    def key_release(key):
        if key == keyboard.Key.f8:
            if active.is_set():
                active.clear()
            else:
                active.set()
            print('Ativo' if active.is_set() else 'Pausado', flush=True)

    def set_hold(want):
        nonlocal held
        if want != held:
            if want:
                controller.press(mouse.Button.left)
            else:
                controller.release(mouse.Button.left)
            held = want

    try:
        with mss.mss() as capture:
            desktop = capture.monitors[0]
            screenshot = np.array(capture.grab(desktop))[:, :, :3].copy()
            x, y, w, h = cv2.selectROI('Selecione a barra inteira e pressione Enter', screenshot, False)
            cv2.destroyAllWindows()
            if w < 15 or h < 60:
                print('Seleção cancelada ou pequena demais.')
                return
            region = dict(left=desktop['left'] + x, top=desktop['top'] + y, width=w, height=h)
            listener = keyboard.Listener(on_press=key_press, on_release=key_release)
            listener.start()
            print('F8: iniciar/pausar. Esc: sair. Mantenha o Roblox em foco.', flush=True)
            last_y = None
            last_time = None
            velocity = 0.0
            cast_state = 'idle'
            missing_since = None
            next_cast = 0.0
            while not stopped.is_set():
                started = time.perf_counter()
                frame = np.array(capture.grab(region))[:, :, :3].copy()
                block, zone = detect(frame)
                valid = block is not None and zone is not None
                enabled = active.is_set() and not args.observe
                if not enabled:
                    cast_state = 'idle'
                    missing_since = None
                    next_cast = 0.0
                elif args.auto_cast:
                    if valid:
                        cast_state = 'fishing'
                        missing_since = None
                    elif cast_state == 'fishing':
                        if missing_since is None:
                            missing_since = started
                        elif started - missing_since >= 2.0:
                            cast_state = 'idle'
                            next_cast = started + 3.0
                    elif cast_state == 'idle' and started >= next_cast:
                        set_hold(False)
                        controller.press(mouse.Button.left)
                        held = True
                        stopped.wait(0.05)
                        set_hold(False)
                        cast_state = 'waiting'
                        print('Vara lançada. Aguardando o minigame.', flush=True)
                if valid:
                    bx, by, bw, bh = block
                    center = by + bh / 2
                    if last_y is not None and last_time is not None:
                        dt = started - last_time
                        if 0 < dt < 0.2:
                            velocity = 0.65 * velocity + 0.35 * (center - last_y) / dt
                    last_y, last_time = center, started
                    target = (zone[0] + zone[1]) / 2
                    error = center + velocity * args.lookahead - target
                    deadband = max(2, (zone[1] - zone[0] - bh) * 0.12)
                    want = error > deadband or (held and error >= -deadband)
                    set_hold(want and active.is_set() and not args.observe)
                    cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (255, 255, 255), 1)
                    cv2.rectangle(frame, (0, zone[0]), (w - 1, zone[1]), (255, 0, 255), 1)
                else:
                    set_hold(False)
                    last_y = last_time = None
                    velocity = 0.0
                preview = cv2.resize(frame, (max(w, 150), h))
                cv2.imshow('Deteccao (nao coloque sobre a barra)', preview)
                if cv2.waitKey(1) & 0xFF == 27:
                    stopped.set()
                stopped.wait(max(0, 1 / args.fps - (time.perf_counter() - started)))
    finally:
        set_hold(False)
        if listener is not None:
            listener.stop()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
