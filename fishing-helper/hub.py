"""Small desktop status panel; all Tk calls stay on the main thread."""
import threading
import tkinter as tk


class HubState:
    def __init__(self):
        self.active = threading.Event()
        self.stopped = threading.Event()
        self.start_requested = threading.Event()
        self.lock = threading.Lock()
        self.data = dict(status='Preparando', detail='Carregando controles...',
                         bar=False, ocr='Carregando', fps=0, inside=None,
                         casts=0, collections=0, mouse=False, collecting=False)

    def update(self, **values):
        with self.lock:
            self.data.update(values)

    def increment(self, name):
        with self.lock:
            self.data[name] += 1

    def snapshot(self):
        with self.lock:
            return self.data.copy()


def run(engine):
    state = HubState()
    root = tk.Tk()
    root.title('Pesca Auto')
    root.geometry('340x365+20+120')
    root.resizable(False, False)
    root.configure(bg='#111827')
    root.attributes('-topmost', True)

    def label(text, size=11, color='#cbd5e1'):
        widget = tk.Label(root, text=text, bg='#111827', fg=color,
                          font=('Segoe UI', size), wraplength=310)
        widget.pack(pady=4)
        return widget

    label('PESCA AUTO', 17, '#ffffff')
    status = label('Preparando', 14, '#fbbf24')
    detail = label('Carregando controles...')
    detection = label('Barra: —  |  OCR: carregando')
    performance = label('Captura: —  |  Bloco: —')
    inputs = label('Mouse solto  |  T solto')
    totals = label('Lançamentos: 0  |  Coletas detectadas: 0')
    buttons = tk.Frame(root, bg='#111827')
    buttons.pack(pady=8)

    def start():
        state.update(status='Iniciando', detail='Voltando ao Roblox...')
        state.start_requested.set()

    def pause():
        state.start_requested.clear()
        state.active.clear()
        state.update(status='Pausado', detail='Use Iniciar ou F8 para retomar.')

    for text, callback in [('Iniciar', start), ('Pausar', pause),
                           ('Encerrar', state.stopped.set)]:
        tk.Button(buttons, text=text, command=callback, width=9,
                  bg='#334155', fg='white', relief='flat').pack(side='left', padx=3)

    label('F8: iniciar/pausar • Esc: encerrar', 9)
    root.protocol('WM_DELETE_WINDOW', state.stopped.set)

    def work():
        try:
            engine(state)
        except Exception as error:
            state.active.clear()
            state.update(status='Erro', detail=str(error))
        else:
            state.stopped.set()

    worker = threading.Thread(target=work, daemon=False)
    worker.start()

    def refresh():
        if state.stopped.is_set():
            root.destroy()
            return
        data = state.snapshot()
        colors = {'Pescando': '#4ade80', 'Coletando': '#4ade80',
                  'Pausado': '#fbbf24', 'Erro': '#f87171'}
        status.configure(text=data['status'], fg=colors.get(data['status'], '#60a5fa'))
        detail.configure(text=data['detail'])
        detection.configure(text=f"Barra: {'detectada' if data['bar'] else 'não detectada'}  |  OCR: {data['ocr']}")
        inside = '—' if data['inside'] is None else ('dentro' if data['inside'] else 'fora')
        performance.configure(text=f"Captura: {data['fps']:.0f} FPS  |  Bloco: {inside}")
        inputs.configure(text=f"Mouse {'segurado' if data['mouse'] else 'solto'}  |  T {'segurado' if data['collecting'] else 'solto'}")
        totals.configure(text=f"Lançamentos: {data['casts']}  |  Coletas detectadas: {data['collections']}")
        root.after(100, refresh)

    root.after(100, refresh)
    try:
        root.mainloop()
    finally:
        state.stopped.set()
        worker.join(timeout=2)
