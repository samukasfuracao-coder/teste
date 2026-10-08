import argparse
import ctypes
import sys
import threading
import time
from ctypes import wintypes

import cv2
import mss
import numpy as np
from pynput import keyboard

from cycle import FishingCycle, JumpTimer
from telemetry import session_logger
from vision_text import has_collect, has_disconnect
from preferences import DEFAULTS, validate_settings
from screen_mask import mask_overlay
from startup_input import StartupLockTap
from tracking_control import track_step
from prompt_reader import read_central_prompt
from collect_input import CollectionHold
from windows_input import WindowsInput


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
    parser.add_argument('--fps', type=int)
    parser.add_argument('--lookahead', type=float)
    parser.add_argument('--jump-interval', type=int)
    args = parser.parse_args()
    initial_settings = hub.settings_snapshot() if hub else DEFAULTS.copy()
    for field, value in [('target_fps', args.fps), ('lookahead', args.lookahead),
                         ('jump_interval', args.jump_interval)]:
        if value is not None:
            initial_settings[field] = value
    try:
        initial_settings = validate_settings(initial_settings)
    except ValueError as error:
        parser.error(str(error))
    if hub:
        hub.apply_settings(initial_settings)

    def settings():
        return hub.settings_snapshot() if hub else initial_settings.copy()

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
    logger = session_logger()
    logger.info('Sessão iniciada: fps=%s intervalo_pulo=%s', initial_settings['target_fps'], initial_settings['jump_interval'])
    print('Preparando controles...', flush=True)
    inputs = WindowsInput()
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
            report(status='Pausado', detail='Volte ao Roblox e use o atalho do perfil.')
            return False
        if move_pointer:
            rect = wintypes.RECT()
            user32.GetClientRect(roblox, ctypes.byref(rect))
            point = wintypes.POINT(int(rect.right * 0.5), int(rect.bottom * 0.75))
            user32.ClientToScreen(roblox, ctypes.byref(point))
            inputs.move(point.x, point.y)
        return True
    held_mouse = False
    held_t = False
    screen_lock = threading.Lock()
    latest = None
    prompt_lock = threading.Lock()
    prompt_time = 0.0
    prompt_visible = False
    prompt_sequence = 0
    frame_time = 0.0
    request_phase = 'idle'
    disconnected = threading.Event()
    held_space = False
    ocr_failed = threading.Event()
    ocr_stop = threading.Event()
    session_epoch = 0

    def hold_mouse(want):
        nonlocal held_mouse
        if want != held_mouse:
            inputs.left_mouse(want)
            held_mouse = want
            report(mouse=want)

    def hold_t(want):
        nonlocal held_t
        if want != held_t:
            inputs.key('t', want)
            held_t = want
            report(collecting=want)

    def jump():
        nonlocal held_space
        if not active.is_set() or stopped.is_set():
            return False
        hwnd = user32.GetForegroundWindow()
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        if 'roblox' not in title.value.lower():
            return False
        try:
            inputs.key('space', True)
            held_space = True
            stopped.wait(0.08)
        finally:
            inputs.key('space', False)
            held_space = False
        logger.info('Pulo periódico enviado')
        if hub:
            hub.increment('jumps')
        return True

    ignored_keys = set()

    def on_press(key):
        if hub and hub.snapshot()['suspend_hotkeys']:
            ignored_keys.add(str(key))
            return
        if str(key).removeprefix('Key.') == settings()['exit_hotkey']:
            stopped.set()

    def on_release(key):
        if str(key) in ignored_keys:
            ignored_keys.discard(str(key))
            return
        if hub and hub.snapshot()['suspend_hotkeys']:
            return
        if str(key).removeprefix('Key.') == settings()['start_hotkey']:
            if active.is_set():
                active.clear()
            else:
                active.set()
            report(status='Iniciando' if active.is_set() else 'Pausado',
                   detail='Aguardando o jogo.' if active.is_set() else 'Use Iniciar ou o atalho do perfil para retomar.')
            print('Ativo' if active.is_set() else 'Pausado', flush=True)

    def read_prompt():
        nonlocal prompt_time, prompt_visible, prompt_sequence
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
        last_fallback = 0.0
        while not stopped.is_set() and not ocr_stop.is_set():
            if not active.is_set():
                stopped.wait(0.1)
                continue
            with screen_lock:
                image = latest
                source_time = frame_time
                phase = request_phase
                source_epoch = session_epoch
            if image is None:
                stopped.wait(0.1)
                continue
            try:
                # Search the whole Roblox window; fish name is irrelevant.
                height, width = image.shape[:2]
                found, connection_lost = read_central_prompt(ocr, image, phase)
                now = time.perf_counter()
                if (not found and phase != 'fishing'
                        and now - last_fallback >= 2.0):
                    wide = image[
                        int(height * 0.10):int(height * 0.85),
                        int(width * 0.15):int(width * 0.85),
                    ]
                    wide = cv2.resize(wide, None, fx=1.5, fy=1.5,
                                      interpolation=cv2.INTER_CUBIC)
                    alternate, _ = ocr(wide)
                    found = has_collect(alternate)
                    connection_lost = connection_lost or has_disconnect(alternate)
                    last_fallback = time.perf_counter()
                with screen_lock:
                    if source_epoch != session_epoch or not active.is_set():
                        continue
                if connection_lost:
                    disconnected.set()
                    active.clear()
                    logger.warning('Aviso de desconexão reconhecido; pausando')
                    report(status='Desconectado', detail='Reconecte ao jogo antes de iniciar novamente.')
                with prompt_lock:
                    prompt_visible = found
                    # Freshness refers to capture time, not OCR completion time.
                    prompt_time = source_time
                    prompt_sequence += 1
            except Exception as exc:
                report(status='Erro', detail=str(exc), ocr='Erro')
                logger.exception('Falha no OCR')
                print('Falha no OCR; pausando:', exc, flush=True)
                active.clear()
            stopped.wait(0.15)

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    worker = threading.Thread(target=read_prompt, daemon=True)
    listener.start()
    worker.start()
    cycle = FishingCycle()
    collection_hold = CollectionHold()
    jump_timer = JumpTimer(time.perf_counter())
    startup_lock = StartupLockTap()
    box = None
    next_scan = 0.0
    previous = None
    velocity = 0.0
    metric_time = time.perf_counter()
    metric_frames = 0
    was_running = False
    last_phase = ''
    report(status='Pausado', detail='Vara equipada? Use Iniciar ou o atalho do perfil.')

    try:
        if (args.auto_start or getattr(sys, 'frozen', False)) and settings()['auto_start']:
            report(status='Iniciando', detail='Início automático em 3 segundos. Esc cancela.')
            if stopped.wait(3):
                return
            if not ocr_failed.is_set() and focus_game(move_pointer=True):
                active.set()
        with mss.mss() as capture:
            while not stopped.is_set():
                started = time.perf_counter()
                config = settings()
                cycle.cast_timeout = config['cast_timeout']
                cycle.collect_wait = config['collect_wait']
                cycle.collect_timeout = config['collect_timeout']
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
                        disconnected.clear()
                        active.set()
                hwnd = user32.GetForegroundWindow()
                title = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, title, 512)
                focused = 'roblox' in title.value.lower()
                if disconnected.is_set():
                    active.clear()
                    report(status='Desconectado', detail='Reconecte ao jogo e use Iniciar.')
                if not active.is_set() or not focused:
                    hold_mouse(False)
                    hold_t(False)
                    collection_hold.reset()
                    if was_running:
                        logger.info('Execução pausada: foco=%s desconectado=%s', focused, disconnected.is_set())
                    cycle.reset()
                    box = previous = None
                    velocity = 0.0
                    next_scan = 0.0
                    with screen_lock:
                        latest = None
                        if was_running:
                            session_epoch += 1
                    with prompt_lock:
                        prompt_time = 0.0
                    was_running = False
                    if active.is_set() and not focused:
                        active.clear()
                        report(status='Pausado', detail='Roblox perdeu o foco. Use Iniciar ou o atalho do perfil.')
                    report(bar=False, inside=None, fps=0, track=None)
                    metric_frames = 0
                    metric_time = started
                    stopped.wait(0.03)
                    continue
                if not was_running:
                    jump_timer.performed(started)
                    logger.info('Execução retomada')
                    was_running = True
                rect = wintypes.RECT()
                origin = wintypes.POINT(0, 0)
                user32.GetClientRect(hwnd, ctypes.byref(rect))
                user32.ClientToScreen(hwnd, ctypes.byref(origin))
                if rect.right <= 0 or rect.bottom <= 0:
                    active.clear()
                    report(status='Pausado', detail='Janela do Roblox indisponível.')
                    continue
                if not startup_lock.done:
                    report(status='Iniciando', detail='Preparando Shift Lock antes do primeiro lançamento.')
                    sent = startup_lock.initialize(
                        config['startup_shift'], active, stopped,
                        lambda: user32.GetForegroundWindow() == hwnd,
                        lambda: hold_mouse(False), lambda: hold_t(False),
                        lambda key: inputs.key(key, True),
                        lambda key: inputs.key(key, False), 'alt_l')
                    if sent:
                        logger.info('Alt esquerdo enviado uma vez no início da sessão')
                    if stopped.is_set() or not active.is_set() or user32.GetForegroundWindow() != hwnd:
                        continue
                frame = np.array(capture.grab(dict(left=origin.x, top=origin.y,
                                                  width=rect.right, height=rect.bottom)))[:, :, :3].copy()
                if hub:
                    mask_overlay(frame, origin.x, origin.y, hub.snapshot()['overlay_rect'])
                captured = time.perf_counter()
                metric_frames += 1
                elapsed = captured - metric_time
                if elapsed >= 0.5:
                    report(fps=metric_frames / elapsed)
                    metric_frames = 0
                    metric_time = captured
                with screen_lock:
                    latest = frame
                    frame_time = captured
                    request_phase = cycle.phase
                with prompt_lock:
                    stamp, visible, sequence = prompt_time, prompt_visible, prompt_sequence
                detected = None
                if box is not None:
                    x, y, w, h = box
                    crop = frame[y:y+h, x:x+w]
                    if crop.shape[:2] == (h, w):
                        detected = objects(crop)
                if detected is None and captured >= next_scan:
                    new_box = find_bar(frame)
                    next_scan = captured + 0.10
                    if new_box is not None:
                        if new_box != box:
                            previous = None
                            velocity = 0.0
                        box = new_box
                        x, y, w, h = box
                        detected = objects(frame[y:y+h, x:x+w])
                now = time.perf_counter()
                decision = cycle.step(now, detected is not None, stamp, sequence, visible)
                if decision.phase != last_phase:
                    logger.info('Estado: %s -> %s', last_phase, decision.phase)
                    last_phase = decision.phase
                report(track=(*detected, box[3]) if detected is not None and box else None,
                       bar=detected is not None,
                       inside=None if detected is None else
                       detected[2] <= detected[0] - detected[1] / 2
                       and detected[0] + detected[1] / 2 <= detected[3])
                interval = config['jump_interval']
                report(jump_remaining=max(0, interval - (now - jump_timer.last_jump)) if interval > 0 else -1)
                requested_t = decision.hold_t and active.is_set() and not stopped.is_set()
                want_t, retry_t = collection_hold.step(
                    now, requested_t, visible and 0 <= now - stamp <= 5)
                hold_t(want_t)
                if retry_t:
                    logger.warning('Aviso de coleta persiste; reiniciando T (tentativa %s)',
                                   collection_hold.retries)
                if decision.action == 'pause':
                    active.clear()
                    hold_mouse(False)
                    hold_t(False)
                    report(status='Pausado', detail=decision.reason)
                    logger.warning(decision.reason)
                    continue
                if decision.action == 'collection_done':
                    logger.info('Coleta detectada: Collect ausente em leituras consecutivas')
                    if hub:
                        hub.increment('collections')
                elif decision.action in ('no_collection', 'retry'):
                    logger.warning('Ciclo sem confirmação: %s', decision.action)
                    if hub:
                        hub.increment('unconfirmed')
                if decision.phase == 'fishing' and detected is not None:
                    center, bh, top, bottom = detected
                    want, previous, velocity = track_step(
                        center, bh, top, bottom, captured, previous,
                        velocity, held_mouse, config['lookahead'])
                    hold_mouse(active.is_set() and not stopped.is_set() and want)
                    report(status='Pescando', detail='Corrigindo o bloco dentro da zona.')
                else:
                    hold_mouse(False)
                    previous = None
                    velocity = 0.0
                    if decision.phase == 'collecting':
                        report(status='Coletando', detail=decision.reason or
                               'Segurando T; confirmando o desaparecimento de Collect.')
                    elif decision.phase == 'waiting_collect':
                        report(status='Buscando coleta', detail='Aguardando o aviso antes de lançar novamente.')
                    elif decision.phase == 'cooldown':
                        report(status='Aguardando', detail='Preparando próximo lançamento.')
                    else:
                        report(status='Procurando barra', detail='Aguardando o minigame aparecer.')
                    interval = config['jump_interval']
                    safe_jump = decision.phase == 'cooldown' and decision.action != 'cast'
                    if jump_timer.due(now, interval, active.is_set(), focused, safe_jump):
                        if jump():
                            jump_timer.performed(time.perf_counter())
                            cycle.next_cast = max(cycle.next_cast, time.perf_counter() + 0.5)
                    remaining = max(0, interval - (now - jump_timer.last_jump)) if interval > 0 else -1
                    report(jump_remaining=remaining)
                    if decision.action == 'cast' and active.is_set() and not stopped.is_set():
                        hold_mouse(True)
                        stopped.wait(0.05)
                        hold_mouse(False)
                        logger.info('Vara lançada')
                        if hub:
                            hub.increment('casts')
                stopped.wait(max(0, 1 / config['target_fps'] - (time.perf_counter() - started)))
    except Exception:
        logger.exception('Falha na execução')
        raise
    finally:
        ocr_stop.set()
        cleanup = [lambda: hold_mouse(False), lambda: hold_t(False)]
        if held_space:
            cleanup.append(lambda: inputs.key('space', False))
        if startup_lock.held:
            cleanup.append(lambda: inputs.key('alt_l', False))
        for release in cleanup:
            try:
                release()
            except Exception:
                logger.exception('Falha ao liberar controle durante encerramento')
        listener.stop()
        logger.info('Sessão encerrada')


if __name__ == '__main__':
    from hub import run
    run(main)
