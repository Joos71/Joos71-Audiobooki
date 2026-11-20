"""Pergamin: kontrola Pages i ograniczona naprawa aktualnej wersji."""
from __future__ import annotations
import json, os, time, uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent
API = 'https://api.github.com/repos/Joos71/Joos71-Audiobooki/actions/runs'
SITE = 'https://joos71.github.io/Joos71-Audiobooki/'
CONTROL = ROOT / '.git' / 'pergamin-publikacja.json'
MARKER = 'docs/pergamin-publication.json'
DATA = ('docs/data.js', 'docs/oczekujace-data.js')
STUCK, COOLDOWN, MAX_DAILY = 1800, 1800, 3
FIRST_DELAY, CHECK_INTERVAL, SESSION_LIMIT = 120, 300, 7200

@contextmanager
def exclusive():
    with (ROOT / '.git' / 'pergamin-publikacja.lock').open('a+b') as f:
        f.seek(0, os.SEEK_END)
        if f.tell() == 0:
            f.write(b'0'); f.flush()
        f.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            f.seek(0)
            if os.name == 'nt':
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def state():
    if not CONTROL.exists(): return {}
    s = json.loads(CONTROL.read_text(encoding='utf-8'))
    if not isinstance(s, dict): raise RuntimeError('Uszkodzony stan kontroli publikacji.')
    return s

def save(s):
    p = CONTROL.with_suffix('.tmp')
    p.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(p, CONTROL)

def sha(git, ref): return git('rev-parse', ref).stdout.strip()

def prepare(git, log):
    if git('diff','--cached','--quiet',check=False).returncode != 0:
        raise RuntimeError('Istnieją zmiany w indeksie Git; automat zatrzymany.')
    git('fetch','origin')
    a,b=sha(git,'HEAD'),sha(git,'origin/main')
    if a==b: return
    if git('merge-base','--is-ancestor',a,b,check=False).returncode==0:
        git('merge','--ff-only','origin/main')
        log('Git: pobrano nowszy main (fast-forward).')
    elif git('merge-base','--is-ancestor',b,a,check=False).returncode==0:
        log('Git: lokalne zatwierdzenia oczekują na push.')
    else: raise RuntimeError('Rozbieżna historia main; bez nadpisywania danych.')

def http(url):
    req=Request(url,headers={'User-Agent':'Joos71-Pergamin/3.0','Cache-Control':'no-cache','Pragma':'no-cache'})
    with urlopen(req,timeout=15) as r:
        b=r.read(8_000_001)
        if len(b)>8_000_000: raise RuntimeError('Zbyt duża odpowiedź HTTP.')
        return b

def norm(b): return b.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')

def live_state(git,head):
    files=list(DATA)
    if git('cat-file','-e',f'{head}:{MARKER}',check=False).returncode==0: files.append(MARKER)
    different=[]
    for path in files:
        expected=git('show',f'{head}:{path}').stdout.replace('\r\n','\n').replace('\r','\n')
        try: live=norm(http(SITE+path.removeprefix('docs/')+'?pergamin='+uuid.uuid4().hex))
        except HTTPError as e:
            if e.code==404: different.append(path+' (404)'); continue
            raise
        if expected!=live: different.append(path)
    return different

def workflow(head):
    data=json.loads(http(API+'?branch=main&head_sha='+head+'&per_page=20'))
    runs=[r for r in data['workflow_runs'] if r.get('head_sha')==head and (r.get('path')=='dynamic/pages/pages-build-deployment' or r.get('name')=='pages build and deployment')]
    return max(runs,key=lambda r:(r.get('run_number',0),r.get('run_attempt',0)),default=None)

def epoch(stamp): return datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp()

def verdict(run,first_seen,now):
    if run is None: return 'missing',now-first_seen>=STUCK
    status=run.get('status')
    if status=='completed':
        c=run.get('conclusion')
        if c=='success': return 'success-but-different',now-epoch(run['updated_at'])>=STUCK and now-first_seen>=STUCK
        return str(c),c in ('failure','cancelled','timed_out','action_required','startup_failure','stale','skipped')
    if status in ('queued','in_progress','pending','waiting','requested'):
        return str(status),now-epoch(run.get('run_started_at') or run.get('updated_at') or run['created_at'])>=STUCK
    return str(status),False

def retry_allowed(s,now):
    day=datetime.fromtimestamp(now).date().isoformat()
    if s.get('retry_day')!=day: s['retry_day'],s['retry_count']=day,0
    return int(s.get('retry_count',0))<MAX_DAILY and now-float(s.get('last_retry',0))>=COOLDOWN

def clean_for_repair(git):
    return git('diff','--cached','--quiet',check=False).returncode==0 and not git('status','--porcelain','--untracked-files=all','--','docs').stdout.strip()

def repair(git,log,head,s,now):
    git('fetch','origin')
    if sha(git,'HEAD')!=head or sha(git,'origin/main')!=head or not clean_for_repair(git):
        log('Pages: naprawa wstrzymana; pojawiły się nowsze lub lokalne zmiany.'); return
    if not retry_allowed(s,now):
        log('Pages: limit napraw (3/dobę lub 30 min przerwy).'); return
    s['retry_count']=int(s.get('retry_count',0))+1
    s['last_retry']=now; save(s)
    marker=ROOT/MARKER
    marker.write_text(json.dumps({'retry':uuid.uuid4().hex,'base':head,'utc':datetime.now(timezone.utc).isoformat()},indent=2)+'\n',encoding='utf-8')
    git('add','--',MARKER)
    git('commit','-m','Pergamin: ponowna publikacja aktualnych danych','--',MARKER)
    newhead=sha(git,'HEAD')
    s['pending_repair']=newhead; save(s)
    git('push','origin','main')
    s.pop('pending_repair',None)
    s['head'],s['first_seen']=newhead,time.time(); save(s)
    log('Pages: wysłano NOWĄ publikację '+newhead[:8]+'; oczekuje na wdrożenie.')

def check(git,log):
    """Kontrola ograniczona czasowo. Błąd sieci nie powoduje naprawy w ciemno."""
    try:
        prepare(git,log)
        s=state()
        local,head=sha(git,'HEAD'),sha(git,'origin/main')
        if local!=head:
            if (s.get('pending_repair')==local and clean_for_repair(git) and
                git('rev-parse','HEAD^').stdout.strip()==head and
                git('diff','--name-only',head,local).stdout.strip()==MARKER and
                time.time()-float(s.get('last_retry',0))>=COOLDOWN):
                now=time.time()
                if not retry_allowed(s,now):
                    log('Pages: limit ponawiania push; zachowuję lokalny commit.'); return False
                s['retry_count']=int(s.get('retry_count',0))+1
                s['last_retry']=now; save(s)
                git('push','origin','main')
                s.pop('pending_repair',None); save(s)
                log('Pages: wysłano oczekujący commit naprawczy.')
            else: log('Pages: lokalny main różni się od serwera; bez publikowania starszych danych.')
            return False
        if s.get('pending_repair')==head:
            s.pop('pending_repair',None); save(s)
        now=time.time()
        if s.get('head')!=head:
            s['head'],s['first_seen']=head,now; save(s)
        different=live_state(git,head)
        if not different:
            s.pop('first_seen',None)
            s['last_verified']=datetime.now(timezone.utc).isoformat()
            s['verified_head']=head; save(s)
            log('Pages: POTWIERDZONO dane publicznej strony zgodne z '+head[:8]+'.')
            return True
        if 'first_seen' not in s:
            s['first_seen']=now; save(s)
        log('Pages: strona różni się od main '+head[:8]+': '+', '.join(different))
        run=workflow(head)
        label,should_retry=verdict(run,float(s['first_seen']),now)
        log('Pages: status bieżącej wersji: '+label+(f' (zadanie #{run.get("run_number")})' if run else ''))
        if should_retry: repair(git,log,head,s,now)
        return False
    except Exception as e:
        log('Pages: kontrola/naprawa nieukończona: '+str(e)[:350]+'; bez wymuszania starszej wersji.')
        return False

def new_marker(head):
    (ROOT/MARKER).write_text(json.dumps({'publication':uuid.uuid4().hex,'base':head,'utc':datetime.now(timezone.utc).isoformat()},indent=2)+'\n',encoding='utf-8')


def monitor(git, log, pushed=False):
    """Jedna sesja po zalogowaniu. Bez cyklicznego zadania Windows."""
    deadline = time.monotonic() + SESSION_LIMIT
    if pushed:
        log('Pages: pierwsza kontrola za 2 minuty po Git push.')
        time.sleep(FIRST_DELAY)
    while True:
        if check(git, log):
            return True
        try:
            s = state()
            now = time.time()
            if (s.get('retry_day') == datetime.fromtimestamp(now).date().isoformat()
                    and int(s.get('retry_count', 0)) >= MAX_DAILY
                    and now - float(s.get('last_retry', 0)) >= STUCK):
                log('Pages: limit 3 prób naprawy na dziś; następna kontrola przy logowaniu.')
                return False
        except Exception as exc:
            log('Pages: nie można odczytać stanu: '+str(exc)[:200]); return False
        remaining = deadline - time.monotonic()
        if remaining < CHECK_INTERVAL:
            log('Pages: koniec sesji (limit 2 h); kolejna kontrola przy logowaniu.')
            return False
        log('Pages: brak potwierdzenia; następna kontrola za 5 minut.')
        time.sleep(CHECK_INTERVAL)
