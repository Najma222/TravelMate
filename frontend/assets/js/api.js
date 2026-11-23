// API helper. Set MOCK=false once Flask is running; mock data follows the PRD contract.
const API={MOCK:true,BASE:'/api'};

// ---- Mock data (only used while MOCK=true) ----
// Sample places per destination. The real backend gets these from Geoapify.
const CATALOG={
 wayanad:{wx:{temp:24,low:18,high:27,condition:'Light rain',rain_prob:45,suggestion:'Carry a rain jacket; forest trails can be slippery.'},places:[
  ['Edakkal Caves',11.6264,76.2358],['Banasura Sagar Dam',11.6713,75.9567],['Soochipara Falls',11.4958,76.183],['Chembra Peak',11.5167,76.0833],['Pookode Lake',11.533,76.023],
  ['Kuruva Island',11.81,76.078],['Thirunelli Temple',11.887,76.007],['Meenmutty Falls',11.462,76.15],['Lakkidi View Point',11.52,76.02],['Muthanga Wildlife Sanctuary',11.625,76.3]]},
 goa:{wx:{temp:29,low:23,high:32,condition:'Partly cloudy',rain_prob:20,suggestion:'Carry sunscreen.'},places:[
  ['Fort Aguada',15.4926,73.7737],['Baga Beach',15.5553,73.7517],['Basilica of Bom Jesus',15.5009,73.9116],['Se Cathedral',15.5035,73.9112],['Anjuna Beach',15.5736,73.7413],
  ['Chapora Fort',15.6055,73.736],['Fontainhas',15.4965,73.8317],['Dudhsagar Falls',15.3144,74.3143],['Palolem Beach',15.01,74.0232],['Cabo de Rama Fort',15.0884,73.9209]]},
 jaipur:{wx:{temp:22,low:10,high:26,condition:'Clear sky',rain_prob:5,suggestion:'Mornings are cool, so carry a light jacket.'},places:[
  ['Amber Fort',26.9855,75.8513],['Hawa Mahal',26.9239,75.8267],['City Palace',26.9258,75.8236],['Jantar Mantar',26.9247,75.8246],['Nahargarh Fort',26.9372,75.8156],
  ['Jal Mahal',26.9535,75.846],['Albert Hall Museum',26.9118,75.819],['Johari Bazaar',26.9187,75.8277],['Jaigarh Fort',26.9857,75.8446],['Panna Meena Ka Kund',26.9885,75.8536]]},
 munnar:{wx:{temp:16,low:11,high:20,condition:'Mist and clouds',rain_prob:30,suggestion:'Pack warm layers for the evenings.'},places:[
  ['Eravikulam National Park',10.195,77.043],['Mattupetty Dam',10.1075,77.123],['Tea Museum',10.0889,77.0595],['Top Station',10.104,77.237],['Echo Point',10.118,77.19],['Attukal Waterfalls',10.043,77.027]]},
 coorg:{wx:{temp:21,low:16,high:25,condition:'Cloudy',rain_prob:40,suggestion:'Carry a rain jacket.'},places:[
  ['Abbey Falls',12.454,75.727],['Raja\'s Seat',12.4202,75.737],['Madikeri Fort',12.4244,75.7382],['Dubare Elephant Camp',12.38,75.93],['Namdroling Monastery',12.4879,75.9633],['Talakaveri',12.385,75.49]]},
 ooty:{wx:{temp:15,low:9,high:19,condition:'Foggy',rain_prob:25,suggestion:'Pack warm clothes.'},places:[
  ['Government Botanical Garden',11.418,76.711],['Ooty Lake',11.41,76.69],['Doddabetta Peak',11.4025,76.737],['Rose Garden',11.412,76.705],['Pykara Falls',11.463,76.597]]}
};
const GENERIC=['City centre walk','Local market','Main museum','Scenic viewpoint','Popular local temple or church','Old town streets'];

function buildTrip(t){
 const key=String(t.destination||'').toLowerCase().replace(/[^a-z]/g,'').replace('waynad','wayanad');
 const c=CATALOG[key];
 const places=c?c.places.map(([name,lat,lon])=>({name,lat,lon})):[];
 const names=c?places.map(p=>p.name):GENERIC;
 const days=Math.min(5,Math.max(1,Math.round((new Date(t.end_date)-new Date(t.start_date))/864e5)+1)); // mock caps at 5 days
 const itinerary=Array.from({length:days},(_,i)=>{
  const a=names[(i*2)%names.length],b=names[(i*2+1)%names.length];
  return{id:t.id*100+i+1,day_number:i+1,title:i===0?`Arrive in ${t.destination}`:a,items:[
   {time:'Morning',activity:a},{time:'Afternoon',activity:b},{time:'Evening',activity:'Dinner and rest at your stay'}]};
 });
 const nights=Math.max(1,days-1),b=Number(t.budget)||0;
 return{itinerary,
  places:places.slice(0,Math.min(places.length,days*2)),
  weather:c?{available:true,...c.wx}:{available:false},
  expenses:[['transport','Travel',.2],['accommodation',`Stay (${nights} night${nights>1?'s':''})`,.35],['food','Food',.2],['activities','Entry fees & activities',.1]].map(([category,label,p],i)=>({id:i+1,category,label,amount:Math.round(b*p),is_confirmed:false})),
  bookings:[]};
}

const DB={
 trips:[{id:1,origin:'Bengaluru',destination:'Goa',start_date:'2026-12-10',end_date:'2026-12-12',travellers:2,budget:25000,status:'Completed'},
        {id:2,origin:'Bengaluru',destination:'Jaipur',start_date:'2027-01-20',end_date:'2027-01-23',travellers:1,budget:18000,status:'Processing'}],
 data:{},
 notifications:[{id:1,notification_type:'7-day reminder',delivery_status:'sent'},{id:2,notification_type:'packing reminder',delivery_status:'scheduled'}],
 prefs:{notify_email:true,notify_telegram:false,telegram_chat_id:''}};

// Mock data is kept in localStorage so it survives page changes.
// To reset it, run localStorage.clear() in the browser console.
try{const s=localStorage.getItem('tm_db2');if(s)Object.assign(DB,JSON.parse(s))}catch{}
const save=()=>{try{localStorage.setItem('tm_db2',JSON.stringify(DB))}catch{}};
let polls=0;

function tripData(t){
 if(!DB.data[t.id]){
  DB.data[t.id]=buildTrip(t);
  if(t.id===1){const d=DB.data[1];d.expenses[0].is_confirmed=true;
   d.bookings=[{id:1,type:'train',provider:'IRCTC',reference:'PNR 2231',amount:2400,date:'2026-12-10',status:'Confirmed'},{id:2,type:'hotel',provider:'Zostel',reference:'',amount:6000,date:'2026-12-10',status:'Pending'}]}
  save();
 }
 return DB.data[t.id];
}

function mock(path,m,b){
 let x;
 if(path==='/trips'){
  if(m==='POST'){const t={id:Math.max(0,...DB.trips.map(t=>t.id))+1,status:'Draft',...b};DB.trips.push(t);save();return t}
  return DB.trips;
 }
 if(x=path.match(/^\/trips\/(\d+)\/(\w+)$/)){
  const t=DB.trips.find(t=>t.id==x[1]);
  if(!t)return Promise.reject({message:'Trip not found'});
  const k=x[2];
  if(k==='status'){if(t.status==='Processing'&&++polls>2){t.status='Completed';polls=0;save()}return{status:t.status}}
  if(k==='generate'){ // regenerate itinerary, places and weather; keep any expenses the user already has
   const fresh=buildTrip(t),d=DB.data[t.id]||fresh;
   d.itinerary=fresh.itinerary;d.places=fresh.places;d.weather=fresh.weather;DB.data[t.id]=d;
   t.status='Processing';polls=0;save();return{status:'Processing'}}
  if(!['itinerary','places','weather','expenses','bookings'].includes(k))return Promise.reject({message:'Unknown endpoint '+path});
  const d=tripData(t);
  if(m==='POST'){const l=d[k];const o={id:Math.max(0,...l.map(i=>i.id))+1,...b};l.push(o);save();return o}
  return d[k];
 }
 if(x=path.match(/^\/trips\/(\d+)$/))return DB.trips.find(t=>t.id==x[1])||Promise.reject({message:'Trip not found'});
 if(x=path.match(/^\/itinerary\/(\d+)$/)){
  for(const d of Object.values(DB.data)){const day=d.itinerary.find(i=>i.id==x[1]);if(day){Object.assign(day,b);save();return day}}
  return Promise.reject({message:'Day not found'});
 }
 if(path==='/notifications')return DB.notifications;
 if(path==='/notifications/preferences'){if(m==='PUT'){Object.assign(DB.prefs,b);save()}return DB.prefs}
 if(path==='/auth/login'||path==='/auth/register')return{name:b.name||b.email.split('@')[0],email:b.email};
 if(path==='/auth/logout')return{};
 return Promise.reject({message:'Unknown endpoint '+path});
}

async function api(path,{method='GET',body}={}){
 try{
  if(API.MOCK){await new Promise(r=>setTimeout(r,150));return await mock(path,method,body)}
  const r=await fetch(API.BASE+path,{method,credentials:'include',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
  const d=await r.json().catch(()=>({}));
  if(r.status===401){location.href='login.html';return}
  if(!r.ok)throw{message:d.error||d.message||'Request failed ('+r.status+')'};
  return d;
 }catch(e){toast(e.message||'Network error. Check your connection and try again.','danger');throw e}
}