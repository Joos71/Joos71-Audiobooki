(()=>{'use strict';
const $=id=>document.getElementById(id);
const raw=window.JOOS71_WAITING;
if(!raw || !Array.isArray(raw.books)){
 $('waiting-count').textContent='Nie udało się wczytać danych. Sprawdź plik oczekujace-data.js.';
 return;
}
const all=raw.books;
const collator=new Intl.Collator('pl',{sensitivity:'base',numeric:true});
const clean=s=>String(s??'').toLocaleLowerCase('pl').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/ł/g,'l');
let records=[],offset=0,loading=false;
const batch=42;
const number=new Intl.NumberFormat('pl-PL');
$('waiting-hero-total').textContent=number.format(all.length);
$('waiting-updated').textContent='Zapis: '+(raw.meta?.sourceDateDisplay||'—');
function create(tag,css='',val=''){
 const el=document.createElement(tag);if(css)el.className=css;if(val)el.textContent=val;return el;
}
function card(b){
 const item=create('article','waiting-item');
 const cover=create('div','waiting-cover');
 const fall=create('div','waiting-cover-fallback',b.title);
 cover.append(fall);
 if(typeof b.cover==='string'&&/^https?:\/\//i.test(b.cover)){
  const img=document.createElement('img');img.loading='lazy';img.decoding='async';img.alt='Okładka: '+b.title;img.referrerPolicy='no-referrer';img.src=b.cover;
  img.addEventListener('error',()=>{img.remove();});cover.append(img);
 }
 const markerRow=create('div','waiting-under-cover');
 const owned=b.type==='własna';
 const marker=create('span','waiting-type-mark '+(owned?'own':'free'),owned?'W':'D');
 marker.title=owned?'Własna':'Darmowa';
 marker.setAttribute('aria-label',owned?'Własna':'Darmowa');
 markerRow.append(marker);
 item.append(cover,markerRow,create('h3','',b.title),create('p','waiting-author',b.author));
 const date=String(b.time||'').slice(0,10).replace(/\//g,'.');
 if(date)item.append(create('div','waiting-meta','Dodano: '+date));
 return item;
}
function renderBatch(){
 if(loading||offset>=records.length)return;
 loading=true;const frag=document.createDocumentFragment();
 const end=Math.min(offset+batch,records.length);
 for(let i=offset;i<end;i++)frag.append(card(records[i]));
 $('waiting-grid').append(frag);offset=end;
 $('waiting-end').hidden=offset<records.length || records.length===0;
 loading=false;
}
function update(){
 const query=clean($('waiting-query').value.trim());const type=$('waiting-type').value;const sort=$('waiting-sort').value;
 records=all.filter(b=>(type==='all'||b.type===type)&&(!query||clean(b.title+' '+b.author).includes(query)));
 const addCmp=(a,b)=>collator.compare(a.title,b.title);
 records.sort((a,b)=>{
  if(sort==='oldest')return String(a.time||'').localeCompare(String(b.time||''))||addCmp(a,b);
  if(sort==='title')return addCmp(a,b);
  if(sort==='title-desc')return -addCmp(a,b);
  if(sort==='author')return collator.compare(a.author,b.author)||addCmp(a,b);
  return String(b.time||'').localeCompare(String(a.time||''))||addCmp(a,b);
 });
 $('waiting-sort-label').textContent=$('waiting-sort').selectedOptions[0].textContent.toLocaleUpperCase('pl');
 $('waiting-count').textContent='Wyświetlono '+number.format(records.length)+' z '+number.format(all.length)+' tytułów';
 $('waiting-empty').hidden=records.length!==0;
 $('waiting-grid').replaceChildren();offset=0;
 $('waiting-end').hidden=true;renderBatch();
}
for(const id of ['waiting-sort','waiting-type'])$(id).addEventListener('change',update);
$('waiting-query').addEventListener('input',update);
$('waiting-reset').addEventListener('click',()=>{$('waiting-query').value='';$('waiting-sort').value='newest';$('waiting-type').value='all';update();});
const sent=$('waiting-sentinel');
if('IntersectionObserver'in window){const obs=new IntersectionObserver(es=>{if(es[0].isIntersecting)renderBatch();},{rootMargin:'550px'});obs.observe(sent);}
else window.addEventListener('scroll',()=>{if(sent.getBoundingClientRect().top<innerHeight+500)renderBatch();},{passive:true});
const top=$('waiting-top');window.addEventListener('scroll',()=>top.classList.toggle('visible',window.scrollY>600),{passive:true});
top.addEventListener('click',()=>window.scrollTo({top:0,behavior:'smooth'}));
update();
})();
