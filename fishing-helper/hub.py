"""Tabbed desktop hub. Tk stays on the main thread; the engine shares snapshots."""
import os
import ctypes
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from preferences import DEFAULTS, ProfileStore, validate_settings
from window_icon import apply_window_icon, prepare_app_identity


class HubState:
    def __init__(self, settings=None):
        self.active = threading.Event()
        self.stopped = threading.Event()
        self.start_requested = threading.Event()
        self.lock = threading.Lock()
        self.settings = validate_settings(settings or {})
        self.data = dict(status='Preparando', detail='Carregando controles...',
                         bar=False, ocr='Carregando', fps=0, inside=None, track=None,
                         casts=0, collections=0, mouse=False, collecting=False,
                         unconfirmed=0, jumps=0, jump_interval=self.settings['jump_interval'],
                         jump_remaining=self.settings['jump_interval'], overlay_rect=None,
                         suspend_hotkeys=False)

    def update(self, **values):
        with self.lock:
            self.data.update(values)

    def increment(self, name):
        with self.lock:
            self.data[name] += 1

    def snapshot(self):
        with self.lock:
            return self.data.copy()

    def settings_snapshot(self):
        with self.lock:
            return self.settings.copy()

    def apply_settings(self, values):
        settings = validate_settings(values)
        with self.lock:
            self.settings = settings
            self.data['jump_interval'] = settings['jump_interval']


class FishingHub:
    PALETTES = {
        'dark': dict(bg='#0b1220', surface='#111e32', card='#14263f',
                     border='#29425e', text='#e6eef9', muted='#9db2cb'),
        'light': dict(bg='#e9f0f7', surface='#ffffff', card='#f4f8fc',
                      border='#cedbea', text='#16304b', muted='#536c85'),
    }

    def __init__(self, root, state, store):
        self.root, self.state, self.store = root, state, store
        self.style = ttk.Style(root)
        self.style.theme_use('clam')
        self.font_family = 'Segoe UI' if os.name == 'nt' else 'Helvetica'
        self.started = time.monotonic()
        self.vars = {}
        self.notice = tk.StringVar(value=store.warning or 'Seu perfil fica salvo neste computador.')
        self.profile = tk.StringVar(value=store.active)
        self.status_text = tk.StringVar(value='Preparando')
        self.detail_text = tk.StringVar(value='Carregando controles...')
        self.metric_vars = {k: tk.StringVar(value='0') for k in ('casts', 'collections', 'unconfirmed', 'jumps')}
        self.indicators = {k: tk.StringVar(value='—') for k in ('bar', 'ocr', 'fps', 'inside', 'inputs', 'jump')}
        self.footer = tk.StringVar()
        self.root.title('Mukz auto fish')
        self.root.minsize(500, 620)
        self.root.protocol('WM_DELETE_WINDOW', self.state.stopped.set)
        self.root.bind('<Configure>', self.overlay_changed)
        self.root.bind('<Map>', self.overlay_changed)
        self.root.bind('<Unmap>', lambda event: self.state.update(overlay_rect=None)
                       if event.widget == self.root else None)
        self.build()
        self.load_fields(state.settings_snapshot())
        self.apply_appearance(resize=True)
        self.refresh_profiles()
        self.root.after(100, self.refresh)

    def build(self):
        self.shell = ttk.Frame(self.root, padding=16, style='Shell.TFrame')
        self.shell.pack(fill='both', expand=True)
        header = ttk.Frame(self.shell, style='Shell.TFrame')
        header.pack(fill='x', pady=(0, 10))
        profile_row = ttk.Frame(header, style='Shell.TFrame')
        profile_row.pack(fill='x')
        ttk.Label(profile_row, text='PERFIL', style='Eyebrow.TLabel').pack(side='left', padx=(0, 10))
        self.profile_combo = ttk.Combobox(profile_row, textvariable=self.profile,
                                          state='readonly', width=23)
        self.profile_combo.pack(side='left', fill='x', expand=True)
        self.profile_combo.bind('<<ComboboxSelected>>', lambda event: self.select_profile())
        ttk.Button(profile_row, text='Salvar', command=self.apply_and_save).pack(side='left', padx=(8, 0))
        self.start_button = ttk.Button(self.shell, text='Iniciar / pausar',
                                      style='Primary.TButton', command=self.toggle)
        self.start_button.pack(fill='x', pady=(0, 4), ipady=5)
        self.author_label = ttk.Label(self.shell, text='by mukz', style='Subtitle.TLabel', anchor='w')
        self.author_label.pack(fill='x', pady=(0, 12))
        self.notebook = ttk.Notebook(self.shell)
        self.pages = {}
        for key, title in [('main', 'Principal'), ('settings', 'Ajustes'), ('profiles', 'Perfis'),
                           ('appearance', 'Visual'), ('help', 'Ajuda')]:
            page = ttk.Frame(self.notebook, padding=12, style='Page.TFrame')
            self.notebook.add(page, text=title)
            self.pages[key] = page
        self.build_main()
        self.build_settings()
        self.build_profiles()
        self.build_appearance()
        self.build_help()
        footer_area = ttk.Frame(self.shell, style='Shell.TFrame')
        footer_area.pack(side='bottom', fill='x', pady=(10, 0))
        ttk.Label(footer_area, textvariable=self.notice, style='Notice.TLabel',
                  wraplength=475).pack(fill='x', pady=(0, 5))
        bottom = ttk.Frame(footer_area, style='Shell.TFrame')
        bottom.pack(fill='x')
        ttk.Label(bottom, textvariable=self.footer, style='Subtitle.TLabel').pack(side='left')
        ttk.Button(bottom, text='Encerrar', command=self.state.stopped.set).pack(side='right')
        self.notebook.pack(fill='both', expand=True)

    def card(self, parent, title):
        frame = ttk.LabelFrame(parent, text=title, padding=10, style='Card.TLabelframe')
        return frame

    def build_main(self):
        page = self.pages['main']
        status = self.card(page, 'AGORA')
        status.pack(fill='x', pady=(0, 10))
        ttk.Label(status, textvariable=self.status_text, style='Status.TLabel').pack(anchor='w')
        ttk.Label(status, textvariable=self.detail_text, wraplength=430,
                  style='Card.TLabel').pack(anchor='w', pady=(5, 0))
        metrics = ttk.Frame(page, style='Page.TFrame')
        metrics.pack(fill='x', pady=(0, 10))
        for index, (key, title) in enumerate([('casts', 'Lançamentos'), ('collections', 'Coletas'),
                                            ('unconfirmed', 'Sem confirmação'), ('jumps', 'Pulos')]):
            metrics.columnconfigure(index, weight=1, uniform='metric')
            frame = self.card(metrics, title)
            frame.grid(row=0, column=index, sticky='nsew', padx=(0 if index == 0 else 5, 0))
            ttk.Label(frame, textvariable=self.metric_vars[key], style='Metric.TLabel').pack(anchor='w')
        live = self.card(page, 'DETECÇÃO AO VIVO')
        live.pack(fill='both', expand=True)
        live.columnconfigure(0, weight=1)
        names = [('bar', 'Barra'), ('ocr', 'Leitura de texto'), ('fps', 'Captura'),
                 ('inside', 'Bloco'), ('inputs', 'Controles'), ('jump', 'Pulo periódico')]
        for index, (key, title) in enumerate(names):
            row = ttk.Frame(live, style='Card.TFrame')
            row.grid(row=index, column=0, sticky='ew', pady=5)
            ttk.Label(row, text=title, style='MutedCard.TLabel', width=14).pack(side='left', anchor='n')
            ttk.Label(row, textvariable=self.indicators[key], style='Card.TLabel',
                      wraplength=225).pack(side='left', anchor='n')
        self.preview = tk.Canvas(live, width=90, height=215, highlightthickness=0)
        self.preview.grid(row=0, column=1, rowspan=6, padx=(12, 0), sticky='n')

    def build_settings(self):
        page = self.pages['settings']
        self.settings_canvas = tk.Canvas(page, highlightthickness=0)
        scrollbar = ttk.Scrollbar(page, orient='vertical', command=self.settings_canvas.yview)
        scrollbar.pack(side='right', fill='y')
        self.settings_canvas.pack(side='left', fill='both', expand=True)
        self.settings_canvas.configure(yscrollcommand=scrollbar.set)
        inner = ttk.Frame(self.settings_canvas, style='Page.TFrame')
        window = self.settings_canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda event: self.settings_canvas.configure(
            scrollregion=self.settings_canvas.bbox('all')))
        self.settings_canvas.bind('<Configure>', lambda event: self.settings_canvas.itemconfigure(window, width=event.width))
        self.root.bind('<MouseWheel>', self.scroll_settings, add='+')
        for title, fields in [
            ('CONTROLE DO BLOCO', [('target_fps', 'Limite de FPS', '30–120; depende do desempenho do PC.'),
                                   ('lookahead', 'Antecipação (s)', '0–0,30; padrão 0,08. Menor valor pode reduzir oscilação.')]),
            ('CICLO DE PESCA', [('cast_timeout', 'Espera pela fisgada (s)', '10–180; tenta novamente se não aparecer a barra.'),
                               ('collect_wait', 'Espera pelo aviso de coleta (s)', '3–60; antes de preparar outro lançamento.'),
                               ('collect_timeout', 'Limite para coletar (s)', '10–120; pausa se a coleta não terminar.'),
                               ('jump_interval', 'Pular a cada (s)', '0 desativa. O pulo aguarda o intervalo entre pescas.')]),
        ]:
            frame = self.card(inner, title)
            frame.pack(fill='x', pady=(0, 10))
            for key, caption, hint in fields:
                row = ttk.Frame(frame, style='Card.TFrame')
                row.pack(fill='x', pady=(0, 3))
                ttk.Label(row, text=caption, style='Card.TLabel').pack(side='left')
                self.vars[key] = tk.StringVar()
                ttk.Entry(row, textvariable=self.vars[key], width=8).pack(side='right')
                ttk.Label(frame, text=hint, style='MutedCard.TLabel', wraplength=390).pack(
                    anchor='w', pady=(0, 10))
        hotkeys = self.card(inner, 'ATALHOS')
        hotkeys.pack(fill='x', pady=(0, 10))
        for key, title in [('start_hotkey', 'Iniciar / pausar'), ('exit_hotkey', 'Encerrar')]:
            self.vars[key] = tk.StringVar()
            row = ttk.Frame(hotkeys, style='Card.TFrame')
            row.pack(fill='x', pady=5)
            ttk.Label(row, text=title, style='Card.TLabel').pack(side='left')
            ttk.Label(row, textvariable=self.vars[key], style='Card.TLabel').pack(side='left', padx=15)
            ttk.Button(row, text='Alterar', command=lambda k=key: self.capture_hotkey(k)).pack(side='right')
        ttk.Button(inner, text='Aplicar e salvar perfil', style='Primary.TButton',
                   command=self.apply_and_save).pack(fill='x', pady=4)
        ttk.Button(inner, text='Carregar ajustes padrão', command=self.load_defaults).pack(fill='x', pady=4)
        ttk.Label(inner, text='Aplicar ajustes pausa a pesca. Retome quando estiver pronto.',
                  wraplength=410, style='PageNote.TLabel').pack(anchor='w', pady=8)

    def build_profiles(self):
        page = self.pages['profiles']
        frame = self.card(page, 'SEUS PERFIS')
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Cada pessoa salva os próprios ajustes neste computador.',
                  style='Card.TLabel', wraplength=425).pack(anchor='w', pady=(0, 12))
        self.profile_list = tk.Listbox(frame, height=7, exportselection=False,
                                      relief='flat', highlightthickness=1)
        self.profile_list.pack(fill='both', expand=True)
        actions = ttk.Frame(frame, style='Card.TFrame')
        actions.pack(fill='x', pady=(12, 0))
        for title, command in [('Carregar', self.load_selected), ('Novo', self.new_profile),
                               ('Excluir', self.delete_profile)]:
            ttk.Button(actions, text=title, command=command).pack(side='left', padx=(0, 6))
        sharing = self.card(page, 'COMPARTILHAR AJUSTES')
        sharing.pack(fill='x', pady=(10, 0))
        ttk.Label(sharing, text='Exporte um JSON para seu amigo. Importar não substitui perfis existentes.',
                  style='Card.TLabel', wraplength=425).pack(anchor='w', pady=(0, 10))
        ttk.Button(sharing, text='Exportar perfil', command=self.export_profile).pack(side='left', padx=(0, 8))
        ttk.Button(sharing, text='Importar perfil', command=self.import_profile).pack(side='left')

    def build_appearance(self):
        page = self.pages['appearance']
        frame = self.card(page, 'APARÊNCIA')
        frame.pack(fill='x')
        self.vars['theme'] = tk.StringVar()
        self.vars['scale'] = tk.StringVar()
        self.vars['accent'] = tk.StringVar()
        self.vars['topmost'] = tk.BooleanVar()
        self.vars['auto_start'] = tk.BooleanVar()
        ttk.Label(frame, text='Tema', style='Card.TLabel').pack(anchor='w')
        themes = ttk.Frame(frame, style='Card.TFrame')
        themes.pack(fill='x', pady=(5, 15))
        for title, value in [('Escuro', 'dark'), ('Claro', 'light')]:
            ttk.Radiobutton(themes, text=title, variable=self.vars['theme'], value=value).pack(side='left', padx=(0, 15))
        row = ttk.Frame(frame, style='Card.TFrame')
        row.pack(fill='x', pady=(0, 15))
        ttk.Label(row, text='Tamanho da interface (%)', style='Card.TLabel').pack(side='left')
        ttk.Combobox(row, textvariable=self.vars['scale'], values=[85, 100, 115, 125, 135],
                     width=6, state='readonly').pack(side='right')
        ttk.Label(frame, text='Cor de destaque', style='Card.TLabel').pack(anchor='w')
        color_row = ttk.Frame(frame, style='Card.TFrame')
        color_row.pack(fill='x', pady=(5, 15))
        ttk.Entry(color_row, textvariable=self.vars['accent'], width=12).pack(side='left')
        ttk.Button(color_row, text='Escolher cor', command=self.pick_color).pack(side='left', padx=8)
        ttk.Checkbutton(frame, text='Manter o hub sempre visível', variable=self.vars['topmost']).pack(anchor='w', pady=8)
        ttk.Checkbutton(frame, text='Iniciar automaticamente ao abrir pelo atalho ou EXE',
                        variable=self.vars['auto_start']).pack(anchor='w', pady=8)
        ttk.Button(page, text='Aplicar e salvar aparência', style='Primary.TButton',
                   command=self.apply_and_save).pack(fill='x', pady=15)
        ttk.Label(page, text='A aparência fica vinculada ao perfil. Seus amigos podem escolher outras cores e atalhos.',
                  style='PageNote.TLabel', wraplength=435).pack(anchor='w')

    def build_help(self):
        page = self.pages['help']
        frame = self.card(page, 'COMO USAR')
        frame.pack(fill='x', pady=(0, 10))
        text = ('1. Abra o Roblox e equipe a vara.\n\n'
                '2. Use o botão Iniciar ou o atalho do seu perfil.\n\n'
                '3. Acompanhe barra, bloco e coleta na aba Principal.\n\n'
                '4. Para personalizar, pause, ajuste e salve o perfil.\n\n'
                'Mantenha o hub fora da barra e do aviso de coleta. '
                'Trocar o foco da janela pausa a automação.')
        ttk.Label(frame, text=text, style='Card.TLabel', wraplength=420,
                  justify='left').pack(anchor='w')
        frame = self.card(page, 'DIAGNÓSTICO')
        frame.pack(fill='x')
        ttk.Label(frame, text=('Coletas são confirmadas pelo desaparecimento do aviso, não pelo inventário. '
                              '“Sem confirmação” pode incluir pescas perdidas.\n\n'
                              'Os pulos não garantem que o servidor evite desconexões.'),
                  wraplength=420, style='Card.TLabel', justify='left').pack(anchor='w', pady=(0, 10))
        ttk.Button(frame, text='Abrir registro de erros e eventos', command=self.open_log).pack(anchor='w')

    def scroll_settings(self, event):
        if self.notebook.select() == str(self.pages['settings']):
            self.settings_canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')

    def load_fields(self, settings):
        for key, variable in self.vars.items():
            variable.set(settings[key])

    def read_fields(self):
        return validate_settings({key: variable.get() for key, variable in self.vars.items()})

    def load_defaults(self):
        self.pause()
        self.load_fields(DEFAULTS)
        self.notice.set('Padrão carregado nos campos. Use Aplicar e salvar para confirmar.')

    def pause(self):
        self.state.start_requested.clear()
        self.state.active.clear()
        hotkey = self.state.settings_snapshot()['start_hotkey'].upper()
        self.state.update(status='Pausado', detail=f'Use Iniciar ou {hotkey} para retomar.')

    def toggle(self):
        if self.state.active.is_set() or self.state.start_requested.is_set():
            self.pause()
        else:
            self.state.update(status='Iniciando', detail='Voltando ao Roblox...')
            self.state.start_requested.set()

    def apply_and_save(self):
        try:
            settings = self.read_fields()
            self.pause()
            self.store.put(self.store.active, settings)
            self.state.apply_settings(settings)
            self.apply_appearance(resize=True)
            self.refresh_profiles()
            self.notice.set(f'Perfil “{self.store.active}” salvo. Pronto para retomar.')
        except (ValueError, OSError) as error:
            messagebox.showerror('Não foi possível salvar', str(error), parent=self.root)

    def refresh_profiles(self):
        names = list(self.store.profiles)
        self.profile_combo.configure(values=names)
        self.profile.set(self.store.active)
        self.profile_list.delete(0, 'end')
        for name in names:
            self.profile_list.insert('end', name)
        index = names.index(self.store.active)
        self.profile_list.selection_set(index)

    def select_profile(self, name=None):
        name = name or self.profile.get()
        try:
            self.pause()
            settings = self.store.select(name)
            self.state.apply_settings(settings)
            self.load_fields(settings)
            self.apply_appearance(resize=True)
            self.refresh_profiles()
            self.notice.set(f'Perfil “{name}” carregado. A pesca está pausada.')
        except (ValueError, OSError) as error:
            messagebox.showerror('Perfil', str(error), parent=self.root)

    def load_selected(self):
        selection = self.profile_list.curselection()
        if selection:
            self.select_profile(self.profile_list.get(selection[0]))

    def new_profile(self):
        self.pause()
        name = simpledialog.askstring('Novo perfil', 'Nome para uma cópia dos ajustes atuais:', parent=self.root)
        if not name:
            return
        try:
            name = self.store.name(name)
            if name in self.store.profiles:
                raise ValueError('Já existe um perfil com esse nome.')
            self.store.put(name, self.read_fields())
            self.state.apply_settings(self.store.current())
            self.load_fields(self.store.current())
            self.apply_appearance(resize=True)
            self.refresh_profiles()
            self.notice.set(f'Perfil “{name}” criado.')
        except (ValueError, OSError) as error:
            messagebox.showerror('Perfil', str(error), parent=self.root)

    def delete_profile(self):
        self.pause()
        selection = self.profile_list.curselection()
        name = self.profile_list.get(selection[0]) if selection else self.store.active
        if not messagebox.askyesno('Excluir perfil', f'Excluir “{name}”?', parent=self.root):
            return
        try:
            self.store.delete(name)
            self.select_profile(self.store.active)
        except (ValueError, OSError) as error:
            messagebox.showerror('Perfil', str(error), parent=self.root)

    def export_profile(self):
        self.pause()
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension='.json',
                                           initialfile='perfil-pesca.json', filetypes=[('Perfil JSON', '*.json')])
        if path:
            try:
                self.store.export(path)
                self.notice.set('Perfil exportado. Apenas os ajustes salvos foram incluídos.')
            except OSError as error:
                messagebox.showerror('Exportar', str(error), parent=self.root)

    def import_profile(self):
        self.pause()
        path = filedialog.askopenfilename(parent=self.root, filetypes=[('Perfil JSON', '*.json')])
        if path:
            try:
                self.store.import_profile(path)
                self.select_profile(self.store.active)
            except (ValueError, OSError, TypeError, AttributeError) as error:
                messagebox.showerror('Importar', str(error), parent=self.root)

    def capture_hotkey(self, key):
        self.pause()
        self.state.update(suspend_hotkeys=True)
        dialog = tk.Toplevel(self.root)
        dialog.title('Alterar atalho')
        dialog.configure(bg=self.palette['surface'])
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text='Pressione F1 a F12 ou Esc.', padding=20).pack()

        def close():
            dialog.destroy()
            self.root.after(350, lambda: self.state.update(suspend_hotkeys=False))

        def capture(event):
            value = event.keysym.lower()
            if value == 'escape':
                value = 'esc'
            if value in ['esc'] + [f'f{i}' for i in range(1, 13)]:
                self.vars[key].set(value)
                close()
                return 'break'

        dialog.bind('<KeyPress>', capture)
        dialog.protocol('WM_DELETE_WINDOW', close)
        ttk.Button(dialog, text='Cancelar', command=close).pack(pady=(0, 15))
        dialog.focus_force()

    def pick_color(self):
        self.pause()
        value = self.vars['accent'].get()
        try:
            color = colorchooser.askcolor(color=value, parent=self.root)[1]
        except tk.TclError:
            color = colorchooser.askcolor(parent=self.root)[1]
        if color:
            self.vars['accent'].set(color)

    def apply_appearance(self, resize=False):
        config = self.state.settings_snapshot()
        p = self.PALETTES[config['theme']]
        self.palette = p
        self.root.configure(bg=p['bg'])
        self.root.attributes('-topmost', config['topmost'])
        factor = config['scale'] / 100
        font = (self.font_family, round(10 * factor))
        self.style.configure('.', font=font, background=p['surface'], foreground=p['text'])
        for name, bg in [('Shell', p['bg']), ('Page', p['surface']), ('Card', p['card'])]:
            self.style.configure(f'{name}.TFrame', background=bg)
        for name, bg, fg in [('Title', p['bg'], p['text']), ('Subtitle', p['bg'], p['muted']),
                             ('Eyebrow', p['bg'], p['muted']), ('Notice', p['bg'], p['muted']),
                             ('Card', p['card'], p['text']), ('MutedCard', p['card'], p['muted']),
                             ('Metric', p['card'], config['accent']), ('Status', p['card'], config['accent'])]:
            self.style.configure(f'{name}.TLabel', background=bg, foreground=fg, font=font)
        self.style.configure('Title.TLabel', font=(self.font_family, round(21 * factor), 'bold'))
        self.style.configure('Metric.TLabel', font=(self.font_family, round(20 * factor), 'bold'))
        self.style.configure('Status.TLabel', font=(self.font_family, round(17 * factor), 'bold'))
        self.style.configure('Eyebrow.TLabel', font=(self.font_family, round(8 * factor), 'bold'))
        self.style.configure('Card.TLabelframe', background=p['card'], bordercolor=p['border'],
                             lightcolor=p['border'], darkcolor=p['border'], borderwidth=1, relief='solid')
        self.style.configure('Card.TLabelframe.Label', background=p['card'], foreground=p['muted'],
                             font=(self.font_family, round(8 * factor), 'bold'))
        self.style.configure('TNotebook', background=p['bg'], borderwidth=0,
                             bordercolor=p['border'], lightcolor=p['border'], darkcolor=p['border'])
        self.style.configure('TNotebook.Tab', padding=(9, 8), background=p['card'], foreground=p['muted'],
                             borderwidth=0, bordercolor=p['bg'], lightcolor=p['card'], darkcolor=p['card'])
        self.style.map('TNotebook.Tab', background=[('selected', p['surface'])],
                       foreground=[('selected', config['accent'])],
                       lightcolor=[('selected', p['surface'])], darkcolor=[('selected', p['surface'])])
        self.style.configure('TButton', background=p['card'], foreground=p['text'], padding=(10, 7),
                             borderwidth=1, bordercolor=p['border'], lightcolor=p['border'],
                             darkcolor=p['border'], relief='flat')
        self.style.map('TButton', background=[('active', p['border'])])
        rgb = [int(config['accent'][i:i+2], 16) for i in (1, 3, 5)]
        ink = '#07111f' if sum(rgb) / 3 > 140 else '#ffffff'
        self.style.configure('Primary.TButton', background=config['accent'], foreground=ink,
                             font=(self.font_family, round(11 * factor), 'bold'), padding=10,
                             borderwidth=0, bordercolor=config['accent'], lightcolor=config['accent'],
                             darkcolor=config['accent'], relief='flat')
        self.style.map('Primary.TButton', background=[('active', config['accent'])], foreground=[('active', ink)])
        self.style.configure('TEntry', fieldbackground=p['bg'], foreground=p['text'], insertcolor=p['text'],
                             bordercolor=p['border'], lightcolor=p['border'], darkcolor=p['border'])
        self.style.configure('TCombobox', fieldbackground=p['bg'], foreground=p['text'], arrowcolor=p['text'],
                             bordercolor=p['border'], lightcolor=p['border'], darkcolor=p['border'])
        self.style.map('TCombobox', fieldbackground=[('readonly', p['bg'])], foreground=[('readonly', p['text'])])
        for name in ('TCheckbutton', 'TRadiobutton'):
            self.style.configure(name, background=p['card'], foreground=p['text'])
            self.style.map(name, background=[('active', p['card'])], foreground=[('active', p['text'])])
        self.style.configure('PageNote.TLabel', background=p['surface'], foreground=p['muted'], font=font)
        self.profile_list.configure(bg=p['bg'], fg=p['text'], selectbackground=config['accent'],
                                     selectforeground=ink, highlightbackground=p['border'], font=font)
        self.settings_canvas.configure(bg=p['surface'])
        self.preview.configure(bg=p['card'])
        if resize:
            width = round(540 * factor)
            height = min(round(800 * factor), self.root.winfo_screenheight() - 80)
            x = max(0, self.root.winfo_x())
            y = max(30, self.root.winfo_y())
            if not self.root.winfo_ismapped():
                x, y = 20, 80
            self.root.geometry(f'{width}x{height}+{x}+{min(y, max(0, self.root.winfo_screenheight()-height))}')

    def overlay_changed(self, event=None):
        if event is not None and event.widget != self.root:
            return
        if self.root.winfo_ismapped():
            self.state.update(overlay_rect=(self.root.winfo_rootx() - 8, self.root.winfo_rooty() - 32,
                                            self.root.winfo_width() + 16, self.root.winfo_height() + 40))

    def draw_preview(self, data):
        p = self.palette
        canvas = self.preview
        canvas.delete('all')
        canvas.create_text(45, 12, text='BARRA', fill=p['muted'], font=(self.font_family, 8))
        canvas.create_rectangle(26, 28, 64, 202, fill=p['bg'], outline=p['border'], width=2)
        track = data['track']
        if track:
            center, block_height, top, bottom, height = track
            factor = 170 / max(1, height)
            canvas.create_rectangle(27, 30 + top * factor, 63, 30 + bottom * factor,
                                    fill='#164e3a' if data['inside'] else '#665313',
                                    outline='#4ade80' if data['inside'] else '#facc15')
            canvas.create_rectangle(34, 30 + (center - block_height / 2) * factor,
                                    56, 30 + (center + block_height / 2) * factor,
                                    fill='#f8fafc', outline='#f8fafc')
        else:
            canvas.create_text(45, 114, text='—', fill=p['muted'])

    def open_log(self):
        directory = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'PescaAuto'
        path = directory / 'pesca.log'
        if not path.exists():
            messagebox.showinfo('Registro', 'O registro ainda não foi criado.', parent=self.root)
            return
        try:
            os.startfile(str(path))
        except (OSError, AttributeError) as error:
            messagebox.showerror('Registro', str(error), parent=self.root)

    def refresh(self):
        if self.state.stopped.is_set():
            self.root.destroy()
            return
        data = self.state.snapshot()
        config = self.state.settings_snapshot()
        self.status_text.set(data['status'])
        self.detail_text.set(data['detail'])
        colors = {'Pescando': '#4ade80', 'Coletando': '#4ade80', 'Pausado': '#fbbf24',
                  'Erro': '#f87171', 'Desconectado': '#f87171'}
        self.style.configure('Status.TLabel', foreground=colors.get(data['status'], config['accent']))
        for key, variable in self.metric_vars.items():
            variable.set(str(data[key]))
        self.indicators['bar'].set('Detectada' if data['bar'] else 'Aguardando')
        self.indicators['ocr'].set(data['ocr'])
        self.indicators['fps'].set(f"{data['fps']:.0f} / {config['target_fps']} FPS")
        self.indicators['inside'].set('—' if data['inside'] is None else 'Dentro da zona' if data['inside'] else 'Fora da zona')
        self.indicators['inputs'].set(f"Mouse {'segurado' if data['mouse'] else 'solto'} | T {'segurado' if data['collecting'] else 'solto'}")
        remaining = data['jump_remaining']
        self.indicators['jump'].set('Desativado' if config['jump_interval'] == 0 else
                                    'Aguardando intervalo entre pescas' if remaining <= 0 else
                                    f'Próximo em {remaining:.0f} s')
        self.start_button.configure(text=(f"PAUSAR ({config['start_hotkey'].upper()})" if self.state.active.is_set()
                                           else f"INICIAR ({config['start_hotkey'].upper()})"))
        elapsed = int(time.monotonic() - self.started)
        self.footer.set(f"{config['start_hotkey'].upper()}: iniciar/pausar | {config['exit_hotkey'].upper()}: sair  |  {elapsed//3600:02}:{elapsed//60%60:02}:{elapsed%60:02}")
        self.overlay_changed()
        self.draw_preview(data)
        self.root.after(100, self.refresh)


def run(engine):
    store = ProfileStore()
    state = HubState(store.current())
    if os.name == 'nt':
        ctypes.windll.user32.SetProcessDPIAware()
    prepare_app_identity()
    root = tk.Tk()
    apply_window_icon(root)
    app = FishingHub(root, state, store)

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
    try:
        root.mainloop()
    finally:
        state.stopped.set()
        worker.join(timeout=2)
