"""Generuje statyczną, publiczną witrynę Joos71 na podstawie listy książek JSON.
Bez zewnętrznych zależności. Nie zmienia pliku źródłowego.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / 'docs'
REQUIRED = {'title', 'author', 'readDate', 'myRating', 'unfinished', 'cover', 'link', 'lp'}


def load_books(path: Path) -> list[dict]:
    text = path.read_text(encoding='utf-8-sig')
    obj = json.loads(text)
    if not isinstance(obj, list) or not obj:
        raise ValueError('Plik JSON powinien zawierać niepustą listę książek.')
    if len(obj) > 30000:
        raise ValueError('Niespodziewanie duża liczba rekordów.')
    result = []
    for i, row in enumerate(obj, 1):
        if not isinstance(row, dict) or not REQUIRED.issubset(row):
            raise ValueError(f'Pozycja {i}: brak wymaganych pól książki.')
        title, author = str(row['title']).strip(), str(row['author']).strip()
        if not title or not author:
            raise ValueError(f'Pozycja {i}: brak tytułu lub autora.')
        year = str(row['readDate']).strip()
        if not re.fullmatch(r'\d{4}', year) or not 1900 <= int(year) <= 2100:
            raise ValueError(f'Pozycja {i}: nieprawidłowy rok: {year!r}.')
        try:
            score = int(str(row['myRating']).strip())
        except ValueError as exc:
            raise ValueError(f'Pozycja {i}: ocena nie jest liczbą.') from exc
        if score < 0 or score > 10:
            raise ValueError(f'Pozycja {i}: ocena spoza zakresu 0–10.')
        if type(row['unfinished']) is not bool:
            raise ValueError(f'Pozycja {i}: unfinished musi być true albo false.')
        try:
            lp = int(row['lp'])
        except (ValueError, TypeError) as exc:
            raise ValueError(f'Pozycja {i}: nieprawidłowy numer lp.') from exc
        # Publikujemy tylko pola potrzebne do katalogu — żadnych danych systemowych.
        result.append({'lp': lp, 'title': title, 'author': author,
                       'cover': str(row.get('cover') or ''),
                       'link': str(row.get('link') or ''),
                       'readDate': year, 'myRating': str(score),
                       'unfinished': row['unfinished']})
    return result


def checksum(books: list[dict]) -> str:
    encoded = json.dumps(books, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def write_site(books: list[dict], source_name: str, source_modified: float | None = None) -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    if source_modified is None:
        display = 'Dane początkowe'
    else:
        display = datetime.fromtimestamp(source_modified).strftime('%d.%m.%Y, %H:%M')
    data = {'meta': {'sourceDateDisplay': display, 'sourceFile': source_name, 'count': len(books)},
            'books': books}
    # Literal JS bez ryzyka wstrzyknięcia znaczników HTML przez dane tytułów.
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    payload = (payload.replace('<', '\\u003c').replace('>', '\\u003e')
                      .replace('&', '\\u0026').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))
    (SITE / 'data.js').write_text('window.JOOS71_BOOKS = ' + payload + ';\n', encoding='utf-8')


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='Zbuduj stronę Joos71 — Przesłuchane książki')
    p.add_argument('plik', type=Path, help='Plik JSON ze stroną Google Sites')
    a = p.parse_args()
    books = load_books(a.plik)
    write_site(books, a.plik.name, a.plik.stat().st_mtime)
    print(f'Zbudowano {len(books)} książek w folderze {SITE}.')
