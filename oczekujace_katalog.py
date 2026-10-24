"""Joos71 — odczytowa lista książek do przesłuchania. Nie zmienia źródłowego zapisu."""
from __future__ import annotations
import json
import hashlib
import re
import time
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SITE=ROOT/'docs'
SOURCE_PATTERN=re.compile(r'^wszystkie książki(?: \((\d+)\))?\.json$',re.IGNORECASE)


def load_waiting(path:Path)->list[dict]:
    source=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(source,dict) or not isinstance(source.get('books'),list):
        raise ValueError('Oczekiwano obiektu JSON z tablicą books.')
    rows=source['books']
    if len(rows)>30000:raise ValueError('Niespodziewanie duża liczba książek.')
    result=[]; ids=set()
    for i,row in enumerate(rows,1):
        if not isinstance(row,dict):raise ValueError(f'Pozycja {i} nie jest książką.')
        title=str(row.get('title') or '').strip()
        author=str(row.get('author') or '').strip()
        uid=str(row.get('id') or '').strip()
        if not title or not author or not uid or uid in ids:
            raise ValueError(f'Brak tytułu/autora/ID albo duplikat ID w pozycji {i}.')
        ids.add(uid)
        kind=str(row.get('type') or '').strip().lower()
        if kind not in ('darmowa','własna'):
            raise ValueError(f'Nieznany typ w pozycji {i}: {kind}.')
        cover=str(row.get('cover') or '')
        if cover and not cover.startswith(('https://','http://')):cover=''
        # Pola dotyczące losowania pozostają wyłącznie w oryginalnym JSON.
        result.append({'id':uid,'title':title,'author':author,'type':kind,'cover':cover,
                       'time':str(row.get('time') or '')})
    return result


def checksum_waiting(books:list[dict])->str:
    s=json.dumps(books,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def latest_waiting(folder:Path,logger=None):
    """Najświeższy poprawny eksport po mtime, nie po numerze w nazwie; brak -> None."""
    if not folder.is_dir():raise RuntimeError('Nie znaleziono folderu: '+str(folder))
    candidates=[p for p in folder.iterdir() if p.is_file() and SOURCE_PATTERN.fullmatch(p.name)]
    candidates.sort(key=lambda p:(p.stat().st_mtime_ns,p.name),reverse=True)
    for candidate in candidates:
        try:
            before=candidate.stat()
            time.sleep(.3)
            after=candidate.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                if logger:logger('Oczekujące: plik w trakcie zapisu: '+candidate.name)
                continue
            return candidate,load_waiting(candidate),after.st_mtime_ns
        except (OSError,UnicodeError,ValueError,TypeError,json.JSONDecodeError) as exc:
            if logger:logger('Oczekujące: pomijam niepoprawny '+candidate.name+': '+str(exc)[:250])
    return None


def write_waiting_site(books:list[dict],name:str,mtime:float|None=None)->None:
    SITE.mkdir(parents=True,exist_ok=True)
    stamp=datetime.fromtimestamp(mtime).strftime('%d.%m.%Y, %H:%M') if mtime is not None else 'Zapis początkowy'
    data={'meta':{'sourceDateDisplay':stamp,'sourceFile':name,'count':len(books)},'books':books}
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':'))
    payload=(payload.replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
                    .replace('\u2028','\\u2028').replace('\u2029','\\u2029'))
    (SITE/'oczekujace-data.js').write_text('window.JOOS71_WAITING = '+payload+';\n',encoding='utf-8')
