import re
from difflib import SequenceMatcher


def has_collect(results):
    for result in results or []:
        if float(result[2]) < 0.55:
            continue
        text = str(result[1]).lower()
        letters = re.sub(r'[^a-z]', '', text)
        if 'collect' in letters or 'coletar' in letters:
            return True
        for word in re.findall(r'[a-z]+', text):
            if 6 <= len(word) <= 8 and SequenceMatcher(None, word, 'collect').ratio() >= 0.82:
                return True
    return False


def has_disconnect(results):
    for result in results or []:
        if float(result[2]) < 0.65:
            continue
        text = re.sub(r'[^a-z]', '', str(result[1]).lower())
        if any(term in text for term in (
                'disconnected', 'desconectado', 'connectionlost',
                'youhavebeenkicked', 'youwerekicked')):
            return True
    return False
