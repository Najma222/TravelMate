const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const inr=n=>'₹'+Number(n).toLocaleString('en-IN');
const daysLeft=d=>Math.max(0,Math.ceil((new Date(d)-new Date().setHours(0,0,0,0))/864e5));
function toast(msg,type='dark'){let t=$('#toasts');if(!t){t=document.createElement('div');t.id='toasts';t.className='toast-container position-fixed bottom-0 end-0 p-3';document.body.append(t)}
 const e=document.createElement('div');e.className=`toast align-items-center text-bg-${type} border-0`;e.role='alert';e.innerHTML=`<div class="d-flex"><div class="toast-body">${esc(msg)}</div><button class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button></div>`;t.append(e);new bootstrap.Toast(e,{delay:4000}).show()}
function nav(active){const u=JSON.parse(sessionStorage.user||'null');
 $('#nav').innerHTML=`<div class="d-flex align-items-center justify-content-between flex-wrap gap-2"><a href="dashboard.html" class="fw-bold fs-5 text-decoration-none text-dark">✈ TravelMate</a>
 <nav class="nav-pill" aria-label="Main">${[['dashboard','Dashboard'],['trips','Your Trips'],['notifications','Reminders']].map(([k,l])=>`<a href="${k}.html" class="${k===active?'active':''}">${l}</a>`).join('')}</nav>
 <div class="d-flex gap-2 align-items-center"><a class="btn-new" href="trip-new.html">+ New Trip</a><button id="out" class="btn btn-sm btn-outline-secondary rounded-pill">${u?esc(u.name)+' · ':''}Log out</button></div></div>`;
 $('#out').onclick=async()=>{await api('/auth/logout',{method:'POST'});sessionStorage.clear();location.href='login.html'}}
function guard(){if(!sessionStorage.user)location.href='login.html'}
const head=t=>`<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>${t} · TravelMate</title><link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap" rel=stylesheet><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel=stylesheet><link href="assets/css/style.css" rel=stylesheet>`;
const tail=`<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script><script src="assets/js/api.js"></script><script src="assets/js/app.js"></script>`;
function drawMap(el,pts){const m=L.map(el,{zoomControl:false});L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap'}).addTo(m);
 if(!pts.length){m.setView([20.6,78.9],4);return}const ll=pts.map(p=>[p.lat,p.lon]);L.polyline(ll,{color:'#0f5f55',weight:4}).addTo(m);
 pts.forEach(p=>L.circleMarker([p.lat,p.lon],{radius:7,color:'#0f5f55',fillColor:'#ffe27a',fillOpacity:1}).addTo(m).bindPopup(esc(p.name)));m.fitBounds(ll,{padding:[30,30]})}

// Ambient doodles + scroll animations for pages that use fun.css
(function(){
 if(!document.querySelector('link[href*="fun.css"]'))return;
 const reduce=matchMedia('(prefers-reduced-motion:reduce)').matches;
 const el=document.createElement('div');el.className='amb';el.setAttribute('aria-hidden','true');
 el.innerHTML=[['a',.06],['b',-.1],['c',.12],['d',-.05],['e',.18],['f',-.14],['g',.08]].map(([k,p])=>`<i class="sh ${k}" data-p="${p}"></i>`).join('')+'<svg class="sh pl" data-p="-.2" viewBox="0 0 64 64"><path d="M4 30L60 6 44 58 32 38zM32 38L60 6" fill="none" stroke="#0f5f55" stroke-width="2" stroke-linejoin="round"/></svg>';
 document.body.prepend(el);
 const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}}),{threshold:.08});
 const tag=()=>document.querySelectorAll('.c:not(.rv),.alert:not(.rv),#hd:not(.rv),.nav-pills:not(.rv)').forEach(n=>{n.classList.add('rv');io.observe(n)});
 new MutationObserver(tag).observe(document.body,{childList:true,subtree:true});tag();
 if(reduce)return;
 const sh=[...el.querySelectorAll('.sh')];let tk=false;
 addEventListener('scroll',()=>{if(tk)return;tk=true;requestAnimationFrame(()=>{const y=scrollY;
  sh.forEach(s=>s.style.translate=`0 ${y*s.dataset.p}px`);
  const d=document.getElementById('dest'),sub=document.querySelector('.sub'),st=document.querySelector('.sticker'),f=Math.max(0,1-y/650);
  if(d){d.style.translate=`0 ${y*.22}px`;d.style.opacity=f}if(sub){sub.style.translate=`0 ${y*.12}px`;sub.style.opacity=f*.8}if(st)st.style.rotate=y*.12+'deg';
  tk=false})},{passive:true});
})();