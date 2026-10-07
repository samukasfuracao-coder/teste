import argparse
import ctypes
import math
import sys
import threading
import time
from ctypes import wintypes

import cv2
import mss
import numpy as np
from pynput import keyboard, mouse


def objects(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    height, width = frame.shape[:2]
    white = cv2.inRange(hsv, (0, 0, 155), (179, 85, 255))
    margin = max(2, int(width * 0.30))
    white[:, :margin] = 0
    white[:, width - margin:] = 0
    white[:max(2, int(height * 0.02))] = 0
    white[-2:] = 0
    blocks = []
    for c in cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, w, h = cv2.boundingRect(c)
        if w >= width * 0.18 and 5 <= h <= height * 0.16:
            if cv2.contourArea(c) >= w * h * 0.45:
                blocks.append((w * h, y + h / 2, h))
    colored = cv2.inRange(hsv, (24, 140, 170), (90, 255, 255))
    zones = []
    contours = cv2.findContours(
        colored, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )[0]
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= width * 0.45 and 8 <= h <= height * 0.25:
            zones.append((y, y + h))
    if not blocks or not zones:
        return None
    _, center, block_height = max(blocks)
    top, bottom = max(zones, key=lambda z: z[1] - z[0])
    return center, block_height, top, bottom


def find_bar(frame):
    height, width = frame.shape[:2]
    # Position fallback calibrated from the user's 1920x1017 client capture.
    # Detection still requires both the white block and vivid target outline.
    left = int(width * 0.731)
    top = int(height * 0.272)
    right = int(width * 0.769)
    bottom = int(height * 0.672)
    if objects(frame[top:bottom, left:right]) is not None:
        return (left, top, right - left, bottom - top)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # The bar is transparent: locate the light outline, not its background.
    outline = cv2.inRange(hsv, (0, 0, 145), (179, 100, 255))
    outline = cv2.morphologyEx(
        outline, cv2.MORPH_CLOSE, np.ones((7, 3), np.uint8)
    )
    edges = cv2.Canny(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 50, 130)
    edges = cv2.morphologyEx(
        edges, cv2.MORPH_CLOSE, np.ones((5, 3), np.uint8)
    )
    candidates = []
    for mask in (outline, edges):
        contours = cv2.findContours(
            mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
        )[0]
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if not max(100, height * 0.12) <= h <= height * 0.85:
                continue
            if not 4 <= h / max(w, 1) <= 18:
                continue
            if not 12 <= w <= width * 0.15:
                continue
            pad = max(3, int(w * 0.08))
            left, top = max(0, x - pad), max(0, y - pad)
            right = min(width, x + w + pad)
            bottom = min(height, y + h + pad)
            crop = frame[top:bottom, left:right]
            if objects(crop) is not None:
                box = (left, top, right - left, bottom - top)
                candidates.append((h, box))
    return max(candidates, default=(0, None))[1]


def main(hub=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--auto-start', action='store_true')
    parser.add_argument('--fps', type=int, default=90)
    parser.add_argument('--lookahead', type=float, default=0.08)
    args = parser.parse_args()
    if not 30 <= args.fps <= 120 or not 0 <= args.lookahead <= 0.3:
        parser.error('Use fps de 30 a 120 e lookahead de 0 a 0.3.')
    if sys.platform != 'win32':
        raise SystemExit('Execute no Windows.')
    cv2.setNumThreads(1)
    ctypes.windll.user32.SetProcessDPIAware()
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    print('Preparando controles...', flush=True)
    pointer = mouse.Controller()
    keys = keyboard.Controller()
    active = hub.active if hub else threading.Event()
    stopped = hub.stopped if hub else threading.Event()

    def report(**values):
        if hub:
            hub.update(**values)

    def focus_game(move_pointer=False):
        roblox = user32.FindWindowW(None, 'Roblox')
        if not roblox:
            report(status='Pausado', detail='Abra o Roblox e equipe a vara.')
            return False
        user32.ShowWindow(roblox, 9)
        user32.SetForegroundWindow(roblox)
        if stopped.wait(0.2):
            return False
        if user32.GetForegroundWindow() != roblox:
            report(status='Pausado', detail='Volte ao Roblox e pressione F8.')
            return False
        if move_pointer:
            rect = wintypes.RECT()
            user32.GetClientRect(roblox, ctypes.byref(rect))
            point = wintypes.POINT(int(rect.right * 0.5), int(rect.bottom * 0.75))
            user32.ClientToScreen(roblox, ctypes.byref(point))
            pointer.position = (point.x, point.y)
        return True
    held_mouse = False
    held_t = False
    screen_lock = threading.Lock()
    latest = None
    prompt_lock = threading.Lock()
    prompt_time = 0.0
    prompt_visible = False
    ocr_failed = threading.Event()

    def hold_mouse(want):
        nonlocal held_mouse
        if want != held_mouse:
            if want:
                pointer.press(mouse.Button.left)
            else:
                pointer.release(mouse.Button.left)
            held_mouse = want
            report(mouse=want)

    def hold_t(want):
        nonlocal held_t
        if want != held_t:
            if want:
                keys.press('t')
            else:
                keys.release('t')
            held_t = want
            report(collecting=want)

    def on_press(key):
        if key == keyboard.Key.esc:
            stopped.set()

    def on_release(key):
        if key == keyboard.Key.f8:
            if active.is_set():
                active.clear()
            else:
                active.set()
            report(status='Iniciando' if active.is_set() else 'Pausado',
                   detail='Aguardando o jogo.' if active.is_set() else 'Use Iniciar ou F8 para retomar.')
            print('Ativo' if active.is_set() else 'Pausado', flush=True)

    def read_prompt():
        nonlocal prompt_time, prompt_visible
        try:
            from rapidocr_onnxruntime import RapidOCR
            ocr = RapidOCR()
            report(ocr='Pronto')
            print('Reconhecimento de coleta pronto.', flush=True)
        except Exception as exc:
            report(status='Erro', detail=str(exc), ocr='Erro')
            print('Falha ao carregar OCR:', exc, flush=True)
            ocr_failed.set()
            active.clear()
            return
        while not stopped.is_set():
            if not active.is_set():
                stopped.wait(0.1)
                continue
            with screen_lock:
                image = latest
            if image is None:
                stopped.wait(0.1)
                continue
            try:
                # Search the whole Roblox window; fish name is irrelevant.
                height, width = image.shape[:2]
                central = image[
                    int(height * 0.25):int(height * 0.65),
                    int(width * 0.35):int(width * 0.65),
                ]
                small = cv2.resize(
                    central, None, fx=2, fy=2,
                    interpolation=cv2.INTER_CUBIC,
                )
                results, _ = ocr(small)
                found = any('collect' in str(r[1]).lower() and float(r[2]) >= 0.55
                            for r in (results or []))
                with prompt_lock:
                    prompt_visible = found
                    prompt_time = time.perf_counter()
            except Exception as exc:
                report(status='Erro', detail=str(exc), ocr='Erro')
                print('Falha no OCR; pausando:', exc, flush=True)
                active.clear()
            stopped.wait(0.15)

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    worker = threading.Thread(target=read_prompt, daemon=True)
    listener.start()
    worker.start()
    state = 'idle'
    box = None
    last_seen = 0.0
    next_cast = 0.0
    next_scan = 0.0
    previous = None
    velocity = 0.0
    collecting_since = 0.0
    absent_since = None
    metric_time = time.perf_counter()
    metric_frames = 0
    report(status='Pausado', detail='Vara equipada? Use Iniciar ou F8.')
    print('Vara equipada, Roblox em foco. F8 inicia/pausa; Esc encerra.', flush=True)

    try:
        if args.auto_start or getattr(sys, 'frozen', False):
            report(status='Iniciando', detail='Início automático em 3 segundos. Esc cancela.')
            print('Inicio automatico em 3 segundos. Esc cancela.', flush=True)
            if stopped.wait(3):
                return
            if not ocr_failed.is_set() and focus_game(move_pointer=True):
                active.set()
        with mss.mss() as capture:
            while not stopped.is_set():
                started = time.perf_counter()
                if ocr_failed.is_set():
                    active.clear()
                    hold_mouse(False)
                    hold_t(False)
                    report(status='Erro', detail='Falha ao carregar OCR. Encerre e reinicie.', ocr='Erro')
                    stopped.wait(0.1)
                    continue
                if hub and hub.start_requested.is_set():
                    hub.start_requested.clear()
                    if focus_game(move_pointer=True):
                        active.set()
                # Read only the Roblox client area, without selecting an ROI.
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                title = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, title, 512)
                focused = 'roblox' in title.value.lower()
                if not active.is_set() or not focused:
                    hold_mouse(False)
                    hold_t(False)
                    state, box, previous = 'idle', None, None
                    velocity = 0.0
                    next_cast = next_scan = 0.0
                    absent_since = None
                    with screen_lock:
                        latest = None
                    with prompt_lock:
                        prompt_time = 0.0
                    if active.is_set() and not focused:
                        active.clear()
                        report(status='Pausado', detail='Roblox perdeu o foco. Use Iniciar ou F8.')
                        print('Pausado: Roblox perdeu o foco. Use F8 para retomar.', flush=True)
                    report(bar=False, inside=None, fps=0)
                    metric_frames = 0
                    metric_time = started
                    stopped.wait(0.03)
                    continue
                rect = wintypes.RECT()
                origin = wintypes.POINT(0, 0)
                user32.GetClientRect(hwnd, ctypes.byref(rect))
                user32.ClientToScreen(hwnd, ctypes.byref(origin))
                if rect.right <= 0 or rect.bottom <= 0:
                    active.clear()
                    continue
                frame = np.array(capture.grab(dict(left=origin.x, top=origin.y,
                                                  width=rect.right, height=rect.bottom)))[:, :, :3].copy()
                metric_frames += 1
                elapsed = started - metric_time
                if elapsed >= 0.5:
                    report(fps=metric_frames / elapsed)
                    metric_frames = 0
                    metric_time = started
                with screen_lock:
                    latest = frame
                with prompt_lock:
                    stamp, visible = prompt_time, prompt_visible
                fresh = stamp > 0 and started - stamp < 2.0
                detected = None
                if box is not None:
                    x, y, w, h = box
                    crop = frame[y:y+h, x:x+w]
                    if crop.shape[:2] == (h, w):
                        detected = objects(crop)
                if detected is None and started >= next_scan:
                    box = find_bar(frame)
                    next_scan = started + 0.10
                    if box is not None:
                        x, y, w, h = box
                        detected = objects(frame[y:y+h, x:x+w])
                        previous = None
                        velocity = 0.0
                        print('Barra localizada.', flush=True)

                report(bar=detected is not None, inside=None if detected is None else detected[2] <= detected[0] - detected[1] / 2 and detected[0] + detected[1] / 2 <= detected[3])

                if fresh and visible and detected is None:
                    if state != 'collecting':
                        collecting_since = started
                        print('Coletando com T...', flush=True)
                    state = 'collecting'
                    hold_mouse(False)
                    hold_t(True)
                    absent_since = None

                if state == 'collecting':
                    report(status='Coletando', detail='Segurando T enquanto Collect estiver visível.')
                    hold_mouse(False)
                    if not fresh:
                        hold_t(False)
                        active.clear()
                        report(status='Pausado', detail='Reconhecimento de coleta atrasou.')
                        print('Pausado: reconhecimento de coleta atrasou.', flush=True)
                    elif not visible:
                        hold_t(False)
                        if absent_since is None:
                            absent_since = started
                        elif started - absent_since >= 0.8:
                            state = 'cooldown'
                            next_cast = started + 2.0
                            if hub:
                                hub.increment('collections')
                    if started - collecting_since > 15:
                        hold_t(False)
                        active.clear()
                        report(status='Pausado', detail='Coleta excedeu 15 segundos.')
                        print('Pausado: coleta excedeu 15 segundos.', flush=True)
                elif detected is not None:
                    hold_t(False)
                    state = 'fishing'
                    report(status='Pescando', detail='Corrigindo o bloco dentro da zona.')
                    last_seen = started
                    center, bh, top, bottom = detected
                    target = (top + bottom) / 2
                    target_velocity = 0.0
                    if previous is not None:
                        py, previous_target, pt = previous
                        dt = started - pt
                        if 0 < dt < 0.2:
                            alpha = 1 - math.exp(-dt / 0.04)
                            velocity += alpha * ((center - py) / dt - velocity)
                            target_velocity = max(-600, min(600, (target - previous_target) / dt))
                    previous = (center, target, started)
                    target_lead = max(-bh / 2, min(bh / 2, target_velocity * 0.025))
                    error = center + velocity * args.lookahead - target - target_lead
                    band = max(1.5, (bottom - top - bh) * 0.08)
                    hold_mouse(active.is_set() and not stopped.is_set()
                               and (error > band or (held_mouse and error >= -band)))
                else:
                    hold_mouse(False)
                    hold_t(False)
                    previous = None
                    velocity = 0.0
                    if state == 'fishing' and started - last_seen > 4:
                        state = 'cooldown'
                        next_cast = started + 2.0
                    report(status='Aguardando' if state == 'cooldown' else 'Procurando barra',
                           detail='Preparando próximo lançamento.' if state == 'cooldown' else 'Aguardando o minigame aparecer.')
                    if (state in ('idle', 'cooldown') and started >= next_cast
                            and (fresh or state == 'idle') and not (fresh and visible)
                            and active.is_set() and not stopped.is_set()):
                        hold_mouse(True)
                        stopped.wait(0.05)
                        hold_mouse(False)
                        state = 'waiting'
                        if hub:
                            hub.increment('casts')
                        print('Vara lancada. Procurando a barra...', flush=True)
                stopped.wait(max(0, 1 / args.fps - (time.perf_counter() - started)))
    finally:
        stopped.set()
        hold_mouse(False)
        hold_t(False)
        listener.stop()


if __name__ == '__main__':
    from hub import run
    run(main)
