(() => {
  'use strict';
  const initial = window.JOOS71_BOOKS;
  const rows = Array.isArray(initial?.books) ? initial.books : [];
  const meta = initial?.meta || {};
  const $ = (id) => document.getElementById(id);
  const $grid = $('book-grid');
  const collator = new Intl.Collator('pl', { sensitivity:'base', numeric:true });
  const normal = (x) => String(x ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('pl');
  const rating = (b) => Number(b.myRating) || 0;
  const labelSort = {
    'order':'KOLEJNOŚĆ PRZESŁUCHANIA — NAJNOWSZE',
    'rating-desc':'MOJA OCENA — OD NAJWYŻSZEJ',
    'rating-asc':'MOJA OCENA — OD NAJNIŻSZEJ',
    'title-asc':'TYTUŁ — A DO Z',
    'title-desc':'TYTUŁ — Z DO A',
    'author-asc':'AUTOR — A DO Z',
    'year-desc':'ROK — OD NAJNOWSZEGO',
    'year-asc':'ROK — OD NAJSTARSZEGO'
  };
  const state = { items:[], shown:0, chunk:49, busy:false };
  const fmt = (num) => new Intl.NumberFormat('pl-PL').format(num);
  const validHttp = (url) => { try { const u = new URL(url); return ['https:','http:'].includes(u.protocol) ? u.href : ''; } catch { return ''; } };
  function textEl(tag,className,value){const e=document.createElement(tag);if(className)e.className=className;e.textContent=String(value ?? '');return e;}
  const total=rows.length, unfinished=rows.filter(b=>b.unfinished).length;
  $('stat-total').textContent=fmt(total);
  $('stat-finished').textContent=fmt(total-unfinished);
  $('stat-unfinished').textContent=fmt(unfinished);
  const rated=rows.filter(b=>Number.isFinite(Number(b.myRating)) && String(b.myRating).trim()!=='');
  $('stat-average').textContent=rated.length ? (rated.reduce((a,b)=>a+rating(b),0)/rated.length).toLocaleString('pl-PL',{minimumFractionDigits:1,maximumFractionDigits:1})+' / 10' : '—';
  $('last-update').textContent='Ostatni zapis: '+(meta.sourceDateDisplay || 'Dane początkowe');
  for (const y of [...new Set(rows.map(b=>String(b.readDate ?? '')).filter(Boolean))].sort((a,b)=>collator.compare(b,a))){const opt=document.createElement('option');opt.value=y;opt.textContent=y;$('year').append(opt);}
  function compare(a,b,mode) {
    const byOrder=(Number(a.lp)||999999)-(Number(b.lp)||999999);
    switch(mode) {
      case 'rating-desc': return rating(b)-rating(a)||byOrder;
      case 'rating-asc': return rating(a)-rating(b)||byOrder;
      case 'title-asc': return collator.compare(a.title,b.title)||byOrder;
      case 'title-desc': return collator.compare(b.title,a.title)||byOrder;
      case 'author-asc': return collator.compare(a.author,b.author)||byOrder;
      case 'year-desc': return collator.compare(b.readDate,a.readDate)||byOrder;
      case 'year-asc': return collator.compare(a.readDate,b.readDate)||byOrder;
      default: return byOrder;
    }
  }
  function searchAndSort(){
    const q=normal($('search').value.trim()); const y=$('year').value;const st=$('status').value;const mode=$('sort').value;
    const selected=rows.filter(b=>((y==='all')||String(b.readDate)===y) && ((st==='all')||(st==='unfinished'?b.unfinished:!b.unfinished)) && (!q || normal(b.title+' '+b.author).includes(q)));
    selected.sort((a,b)=>compare(a,b,mode)); state.items=selected; state.shown=0; $grid.replaceChildren();
    $('current-sort').textContent=labelSort[mode]||'SORTOWANIE';
    $('count-status').textContent=`Wyświetlono ${fmt(Math.min(selected.length,state.chunk))} z ${fmt(selected.length)} książek${selected.length!==rows.length?' (w całej kolekcji '+fmt(rows.length)+')':''}`;
    $('no-results').hidden=selected.length!==0; $('end-note').hidden=true;
    nextBatch();
  }
  function createCard(book){
    const card=document.createElement('article');card.className='book-card';
    const href=validHttp(book.link), cover=validHttp(book.cover);
    const outer=href?document.createElement('a'):document.createElement('div');outer.className='cover-link';
    if(href){outer.href=href;outer.target='_blank';outer.rel='noopener noreferrer';outer.setAttribute('aria-label','Otwórz informacje o książce '+book.title);}
    const frame=document.createElement('div');frame.className='cover-frame';
    const fallback=()=>{frame.replaceChildren();const el=textEl('div','cover-fallback',book.title);el.append(textEl('small','',book.author));frame.append(el);if(book.unfinished){frame.append(textEl('span','unfinished-tag','NIEDOKOŃCZONA'));}};
    if(cover){const img=document.createElement('img');img.loading='lazy';img.decoding='async';img.referrerPolicy='no-referrer';img.alt='Okładka: '+book.title;img.onerror=()=>fallback();frame.append(img);if(book.unfinished)frame.append(textEl('span','unfinished-tag','NIEDOKOŃCZONA'));img.src=cover;}else{fallback();}
    outer.append(frame);card.append(outer);
    const title=document.createElement('h3');title.className='book-title';
    if(href){const link=document.createElement('a');link.href=href;link.target='_blank';link.rel='noopener noreferrer';link.textContent=book.title;title.append(link);}else{title.textContent=book.title;}
    card.append(title,textEl('p','book-author',book.author));
    const bottom=document.createElement('div');bottom.className='book-meta';bottom.append(textEl('span','rating',String(book.myRating || '—')+'/10'),textEl('span','', '·'),textEl('span','book-year',book.readDate));card.append(bottom);
    return card;
  }
  function nextBatch(){
    if(state.busy || state.shown>=state.items.length)return;
    state.busy=true;
    const end=Math.min(state.shown+state.chunk,state.items.length);const frag=document.createDocumentFragment();
    for(let i=state.shown;i<end;i++)frag.append(createCard(state.items[i]));
    $grid.append(frag);state.shown=end;
    $('count-status').textContent=`Wyświetlono ${fmt(end)} z ${fmt(state.items.length)} książek${state.items.length!==rows.length?' (w całej kolekcji '+fmt(rows.length)+')':''}`;
    $('end-note').hidden=end<state.items.length||end===0;
    state.busy=false;
  }
  for (const id of ['year','sort','status'])$(id).addEventListener('change',searchAndSort);
  $('search').addEventListener('input',searchAndSort);
  $('reset').addEventListener('click',()=>{$('search').value='';$('year').value='all';$('sort').value='order';$('status').value='all';searchAndSort();});
  const sentinel=$('loading');if('IntersectionObserver' in window){const ob=new IntersectionObserver(entries=>{if(entries[0].isIntersecting)nextBatch();},{rootMargin:'550px'});ob.observe(sentinel);}else window.addEventListener('scroll',()=>{if(sentinel.getBoundingClientRect().top<innerHeight+500)nextBatch();},{passive:true});
  const up=$('to-top');window.addEventListener('scroll',()=>up.classList.toggle('visible',window.scrollY>600),{passive:true});up.addEventListener('click',()=>window.scrollTo({top:0,behavior:'smooth'}));
  const dlg=$('avatar-dialog');$('avatar-open').addEventListener('click',()=>dlg.showModal());$('avatar-close').addEventListener('click',()=>dlg.close());dlg.addEventListener('click',(e)=>{if(e.target===dlg)dlg.close();});
  searchAndSort();
})();
