"""Joos71 — JEDNORAZOWE sprawdzenie książek przy zalogowaniu do Windows.

- Wybiera najnowszy poprawny plik przesłuchane.json / przesłuchane (N).json.
- Jeśli dane są nowe, buduje cały katalog od nowa i publikuje na GitHub.
- Jeśli pliku nie zmieniono, nie publikuje niczego.
- Kończy działanie po jednym sprawdzeniu. Nie monitoruje folderu stale.
- Przeznaczony do uruchamiania przez pyw.exe + Harmonogram zadań.
"""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from buduj_katalog import checksum, load_books, write_site
from oczekujace_katalog import checksum_waiting, latest_waiting, write_waiting_site

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'ustawienia.json'
STATE = ROOT / '.stan-synchronizacji.json'
LOG = ROOT / 'synchronizacja.log'
SOURCE_PATTERN = re.compile(r'^przesłuchane(?: \((\d+)\))?\.json$', re.IGNORECASE)


def log(message: str) -> None:
    line = datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '  ' + message
    with LOG.open('a', encoding='utf-8') as file:
        file.write(line + '\n')
    if sys.stdout is not None:
        print(line, flush=True)


def latest_valid_json(folder: Path):
    if not folder.is_dir():
        raise RuntimeError('Folder pobierania nie istnieje: ' + str(folder))
    files = [p for p in folder.iterdir() if p.is_file() and SOURCE_PATTERN.fullmatch(p.name)]
    if not files:
        raise RuntimeError('Nie znaleziono plików przesłuchane.json w ' + str(folder))
    files.sort(key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
    for path in files:
        try:
            # Plik może być chwilowo w trakcie zapisu; odczekaj i sprawdź, czy stabilny.
            s1 = path.stat()
            time.sleep(0.3)
            s2 = path.stat()
            if (s1.st_size, s1.st_mtime_ns) != (s2.st_size, s2.st_mtime_ns):
                log('Pomijam plik, który jest jeszcze zapisywany: ' + path.name)
                continue
            books = load_books(path)
            return path, books, s2.st_mtime_ns
        except (OSError, ValueError, json.JSONDecodeError, UnicodeError) as exc:
            log('Pomijam niepoprawny zapis ' + path.name + ': ' + str(exc)[:300])
    raise RuntimeError('Żaden znaleziony JSON nie zawiera poprawnej listy książek.')


def git_binary() -> str:
    return (shutil.which('git') or next((str(x) for x in [
        Path(r'C:\Program Files\Git\cmd\git.exe'),
        Path(r'C:\Program Files (x86)\Git\cmd\git.exe')
    ] if x.is_file()), '') or '')


def git(*args: str, check=True) -> subprocess.CompletedProcess:
    exe = git_binary()
    if not exe:
        raise RuntimeError('Nie znaleziono Git w Windows. Zainstaluj Git for Windows.')
    env = dict(os.environ)
    # Ukryta aplikacja nie może czekać na niewidoczne okno autoryzacji.
    env['GCM_INTERACTIVE'] = 'never'
    env['GIT_TERMINAL_PROMPT'] = '0'
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        res = subprocess.run([exe, *args], cwd=ROOT, text=True, encoding='utf-8', errors='replace',
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             timeout=180, env=env, creationflags=flags)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('Upłynął limit czasu wykonywania Git.') from exc
    if check and res.returncode:
        raise RuntimeError('Błąd Git (' + ' '.join(args[:2]) + '): ' + (res.stdout or '')[-1300:])
    return res


def check_repository(expected: str) -> None:
    if not (ROOT / '.git').is_dir():
        raise RuntimeError('Repozytorium Git nie zostało jeszcze zainicjowane w ' + str(ROOT))
    origin = git('remote', 'get-url', 'origin').stdout.strip()
    if origin.lower().rstrip('/').removesuffix('.git') != expected.lower().rstrip('/').removesuffix('.git'):
        raise RuntimeError('Adres origin nie zgadza się z ustawienia.json; sprawdź repozytorium.')
    current = git('branch', '--show-current').stdout.strip()
    if current != 'main':
        raise RuntimeError('Nieprawidłowa gałąź: ' + current + ' (wymagana main).')


def pending_push() -> bool:
    check = git('rev-list', '--count', 'origin/main..HEAD', check=False)
    if check.returncode:
        # Pierwsza synchronizacja przed zdalną gałęzią — publikację i tak sprawdzi Git push.
        return bool(git('log', '-1', '--format=%H', check=False).stdout.strip())
    return int(check.stdout.strip() or '0') > 0


def main() -> None:
    """Jedno sprawdzenie obu niezależnych źródeł podczas istniejącego zadania logowania."""
    settings=json.loads(SETTINGS.read_text(encoding='utf-8'))
    folder=Path(settings['folder_pobierania'])
    expected_repo=str(settings['repozytorium_https'])
    log('Rozpoczynam JEDNO sprawdzenie dwóch kolekcji po zalogowaniu do Windows.')
    old=json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
    try:
        source,books,mtime_ns=latest_valid_json(folder)
    except RuntimeError:
        if not old.get('checksum'):
            raise  # Pierwsze uruchomienie musi mieć przynajmniej jeden zapis przesłuchanych.
        source,books,mtime_ns=None,[],None
        current_hash=old['checksum']
        listened_changed=False
        log('Przesłuchane: brak nowego zapisu, zachowuję opublikowaną kolekcję.')
    else:
        current_hash=checksum(books)
        listened_changed=old.get('checksum')!=current_hash
        # Nie cofamy danych przesłuchanych przy pozostawieniu starego eksportu.
        if listened_changed and old.get('source_mtime_ns') and mtime_ns<int(old['source_mtime_ns']):
            log('Przesłuchane: dostępny zapis starszy od ostatnio wysłanego; pozostawiam publikację.')
            listened_changed=False
        log('Przesłuchane: '+source.name+' ('+str(len(books))+' książek).')

    waiting=latest_waiting(folder,log)
    waiting_changed=False
    waiting_hash=old.get('waiting_checksum')
    waiting_source=None
    waiting_books=[]
    waiting_mtime=None
    if waiting is None:
        log('Oczekujące: nie znaleziono poprawnego pliku "wszystkie książki(.N).json". Zachowuję poprzedni zbiór.')
    else:
        waiting_source,waiting_books,waiting_mtime=waiting
        new_waiting_hash=checksum_waiting(waiting_books)
        waiting_changed=new_waiting_hash!=old.get('waiting_checksum')
        if waiting_changed and old.get('waiting_source_mtime_ns') and waiting_mtime<int(old['waiting_source_mtime_ns']):
            log('Oczekujące: znaleziony zapis jest starszy od poprzednio wysłanego. Nie cofnięto danych.')
            waiting_changed=False
        else:
            waiting_hash=new_waiting_hash
        log('Oczekujące: '+waiting_source.name+' ('+str(len(waiting_books))+' książek).')

    check_repository(expected_repo)
    if listened_changed:
        write_site(books,source.name,mtime_ns/1e9)
        log('Przebudowano katalog przesłuchanych.')
    if waiting_changed:
        write_waiting_site(waiting_books,waiting_source.name,waiting_mtime/1e9)
        log('Przebudowano katalog oczekujących.')

    # Dla bezpieczeństwa zapisujemy wyłącznie publiczne elementy strony i dwa skrypty.
    git('add','--all','--','docs','synchronizuj.py','oczekujace_katalog.py')
    diff=git('diff','--cached','--quiet','--','docs','synchronizuj.py','oczekujace_katalog.py',check=False)
    if diff.returncode==1:
        git('commit','-m','Pergamin Kronika - aktualizacja katalogow audiobookow')
        log('Zapisano zmiany w Git.')
    elif diff.returncode!=0:
        raise RuntimeError('Nie udało się sprawdzić zmian w Git.')
    else:
        log('Brak zmian do zapisania.')
    if pending_push():
        git('push','origin','main')
        log('Wysłano nowe dane do GitHub Pages.')
    else:
        log('Nic nowego do wysłania.')

    # Aktualizujemy stan dopiero po zakończonym powodzeniem Git push.
    state=dict(old)
    if listened_changed or not old.get('checksum'):
        state.update({'checksum':current_hash,'source_name':source.name,'source_mtime_ns':mtime_ns})
    if waiting_changed:
        state.update({'waiting_checksum':waiting_hash,'waiting_source_name':waiting_source.name,
                      'waiting_source_mtime_ns':waiting_mtime})
    state['synced_at']=datetime.now().isoformat(timespec='seconds')
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    log('Zakończono sprawdzenie. Program się wyłącza.')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        try:
            log('BŁĄD: ' + str(e))
            log('Szczegóły błędu: ' + traceback.format_exc()[-1600:])
            log('Zakończono sprawdzenie z błędem. Program się wyłącza.')
        except Exception:
            pass
        sys.exit(1)
