"""Validated, per-user profiles. No session counters or credentials are stored."""
import json
import math
import os
import re
import shutil
from pathlib import Path

DEFAULTS = dict(target_fps=90, lookahead=0.08, jump_interval=120,
                cast_timeout=45, collect_wait=12, collect_timeout=45,
                start_hotkey='f8', exit_hotkey='esc', theme='dark',
                accent='#38bdf8', scale=100, topmost=True, auto_start=True, startup_shift=True)


def validate_settings(values):
    if not isinstance(values, dict):
        raise ValueError('O perfil deve conter um objeto de configurações.')
    result = DEFAULTS | {k: v for k, v in values.items() if k in DEFAULTS}
    limits = dict(target_fps=(30, 120), lookahead=(0, 0.3),
                  jump_interval=(0, 3600), cast_timeout=(10, 180),
                  collect_wait=(3, 60), collect_timeout=(10, 120), scale=(85, 135))
    for key, (low, high) in limits.items():
        try:
            if isinstance(result[key], bool):
                raise ValueError()
            number = float(result[key])
            if not math.isfinite(number) or not low <= number <= high:
                raise ValueError()
            if key != 'lookahead' and not number.is_integer():
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError(f'{key}: use um valor entre {low} e {high}.') from None
        result[key] = number if key == 'lookahead' else int(number)
    for key in ('topmost', 'auto_start', 'startup_shift'):
        if not isinstance(result[key], bool):
            raise ValueError(f'{key}: use verdadeiro ou falso.')
    for key in ('start_hotkey', 'exit_hotkey'):
        value = str(result[key]).strip().lower()
        if not re.fullmatch(r'f(?:[1-9]|1[0-2])|esc', value):
            raise ValueError('Atalhos permitidos: F1 a F12 ou Esc.')
        result[key] = value
    if result['start_hotkey'] == result['exit_hotkey']:
        raise ValueError('Os atalhos de iniciar e encerrar precisam ser diferentes.')
    if result['theme'] not in ('dark', 'light'):
        raise ValueError('Tema inválido.')
    if not isinstance(result['accent'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', result['accent']):
        raise ValueError('Use uma cor no formato #RRGGBB.')
    return result


class ProfileStore:
    def __init__(self, path=None):
        directory = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'PescaAuto'
        self.path = Path(path) if path else directory / 'perfis.json'
        self.profiles = {'Padrão': DEFAULTS.copy()}
        self.active = 'Padrão'
        self.warning = ''
        if self.path.exists():
            try:
                payload = self.read_json(self.path)
                if payload.get('version') != 1 or not isinstance(payload.get('profiles'), dict):
                    raise ValueError('Formato de perfis inválido.')
                profiles = {self.name(k): validate_settings(v)
                            for k, v in payload['profiles'].items()}
                if not profiles:
                    raise ValueError('Nenhum perfil encontrado.')
                active = payload.get('active')
                if not isinstance(active, str) or active not in profiles:
                    active = next(iter(profiles))
                self.profiles, self.active = profiles, active
            except (OSError, ValueError, TypeError, AttributeError):
                self.warning = 'Não foi possível ler os perfis. Usando o padrão; o arquivo original será preservado ao salvar.'

    @staticmethod
    def name(value):
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 40:
            raise ValueError('Use um nome de perfil de 1 a 40 caracteres.')
        if any(ord(c) < 32 for c in value):
            raise ValueError('O nome do perfil contém caracteres inválidos.')
        return value.strip()

    @staticmethod
    def read_json(path):
        path = Path(path)
        if path.stat().st_size > 256_000:
            raise ValueError('Arquivo de perfil muito grande.')
        return json.loads(path.read_text(encoding='utf-8'))

    def current(self):
        return self.profiles[self.active].copy()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.warning and self.path.exists():
            backup = self.path.with_suffix('.json.bak')
            counter = 1
            while backup.exists():
                backup = self.path.with_suffix(f'.json.bak{counter}')
                counter += 1
            shutil.copy2(self.path, backup)
        payload = dict(version=1, active=self.active, profiles=self.profiles)
        temporary = self.path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.path)
        self.warning = ''

    def put(self, name, settings):
        name = self.name(name)
        settings = validate_settings(settings)
        self.profiles[name] = settings
        self.active = name
        self.save()

    def select(self, name):
        if name not in self.profiles:
            raise ValueError('Perfil não encontrado.')
        self.active = name
        self.save()
        return self.current()

    def delete(self, name):
        if len(self.profiles) <= 1:
            raise ValueError('Mantenha pelo menos um perfil.')
        del self.profiles[name]
        if self.active == name:
            self.active = next(iter(self.profiles))
        self.save()

    def export(self, path):
        payload = dict(version=1, name=self.active, settings=self.current())
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    def import_profile(self, path):
        payload = self.read_json(path)
        if not isinstance(payload, dict) or payload.get('version') != 1:
            raise ValueError('Arquivo de perfil inválido.')
        name = self.name(payload.get('name'))
        settings = validate_settings(payload.get('settings'))
        suffix = 2
        original = name
        while name in self.profiles:
            name = f'{original[:35]} ({suffix})'
            suffix += 1
        self.put(name, settings)
        return name
