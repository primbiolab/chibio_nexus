/* ── Architect JS — extraído de architect.html ────────────────────── */
// ╔══════════════════════════════════════════════════════════╗
//  CHI.BIO MASTER ARCHITECT V1.1  —  Core Engine + Cloud + AI
// ╚══════════════════════════════════════════════════════════╝

const AST =[];          
let safetyOk = false;
let cs1 = false, cs2 = false, cs3 = false;
let needOdCalibration = false;
let nodeCounter = 0;
let dragFromPalette = null;   
let dragFromCanvas  = null;   

let globalPumps = { Pump1: 1.0, Pump2: 1.0, Pump3: 1.0, Pump4: 1.0 };
let rawPythonCode = "";

const META = {
  init_temp:   {label:'Temperatura inicial',  ico:'fa-temperature-half', col:'#ef4444'},
  init_od:     {label:'OD objetivo inicial',  ico:'fa-bullseye',         col:'#00e5a0'},
  init_stir:   {label:'Agitación inicial',    ico:'fa-fan',              col:'#fbbf24'},
  thermostat:  {label:'Fijar Termostato',     ico:'fa-temperature-full', col:'#ef4444'},
  ramp_temp:   {label:'Rampa Térmica',        ico:'fa-arrow-trend-up',   col:'#f43f5e'},
  led:         {label:'Control LED',          ico:'fa-lightbulb',        col:'#fbbf24'},
  uv:          {label:'Control UV',           ico:'fa-radiation',        col:'#8b5cf6'},
  pump:        {label:'Dispensar Bomba',      ico:'fa-droplet',          col:'#3b82f6'},
  turbidostat: {label:'Turbidostato',         ico:'fa-chart-line',       col:'#22d3ee'},
  chemostat:   {label:'Quimiostato',          ico:'fa-circle-nodes',     col:'#ec4899'},
  zigzag:      {label:'Zigzag',               ico:'fa-wave-square',      col:'#f59e0b'},
  measure_od:  {label:'Medir OD',             ico:'fa-microscope',       col:'#00e5a0'},
  wait:        {label:'Esperar',              ico:'fa-hourglass-half',   col:'#94a3b8'},
  loop:        {label:'Bucle',                ico:'fa-repeat',           col:'#f59e0b'},
  trigger:     {label:'Trigger (Condición)',  ico:'fa-bolt',             col:'#f87171'},
  log:         {label:'Mensaje en Consola',   ico:'fa-terminal',         col:'#10b981'},
};

const LED_WL = {LEDB:'457nm',LEDC:'500nm',LEDD:'523nm',LEDF:'623nm',LEDG:'6500K',LASER650:'Láser 650nm'};

// ── Modals & Settings ─────────────────────────────────────
function openPumpModal() {
    document.getElementById('p_rate1').value = globalPumps.Pump1;
    document.getElementById('p_rate2').value = globalPumps.Pump2;
    document.getElementById('p_rate3').value = globalPumps.Pump3;
    document.getElementById('p_rate4').value = globalPumps.Pump4;
    document.getElementById('modal-pump').classList.add('open');
}
function closePumpModal(e){ if(e.target===document.getElementById('modal-pump')) document.getElementById('modal-pump').classList.remove('open'); }
function savePumpModal() {
    globalPumps.Pump1 = parseFloat(document.getElementById('p_rate1').value) || 1.0;
    globalPumps.Pump2 = parseFloat(document.getElementById('p_rate2').value) || 1.0;
    globalPumps.Pump3 = parseFloat(document.getElementById('p_rate3').value) || 1.0;
    globalPumps.Pump4 = parseFloat(document.getElementById('p_rate4').value) || 1.0;
    document.getElementById('modal-pump').classList.remove('open');
    refresh(); toast('Caudales globales actualizados', 'ok');
}

// Cloud config — ahora solo abre el modal informativo
function openCloudModal(){
  document.getElementById('modal-cloud').classList.add('open');
}
function saveCloudConfig(){
  document.getElementById('modal-cloud').classList.remove('open');
}
function openSafety(){  cs1=false; cs2=false; cs3=false;['cs1','cs2','cs3'].forEach(id=>document.getElementById(id).classList.remove('done'));
  ['cc1','cc2','cc3'].forEach(id=>{ document.getElementById(id).textContent=''; });
  
  needOdCalibration = AST.some(n =>['turbidostat','zigzag','measure_od'].includes(n.type) || (n.type==='trigger' && n.tvar==='OD'));
  document.getElementById('cs3').style.display = needOdCalibration ? 'flex' : 'none';
  
  document.getElementById('safety-ok-btn').disabled=true;
  document.getElementById('modal-safety').classList.add('open');
}
function toggleCS(n){
  if(n===1) { cs1=!cs1; document.getElementById('cs1').classList.toggle('done',cs1); document.getElementById('cc1').textContent=cs1?'✓':''; }
  else if(n===2) { cs2=!cs2; document.getElementById('cs2').classList.toggle('done',cs2); document.getElementById('cc2').textContent=cs2?'✓':''; }
  else { cs3=!cs3; document.getElementById('cs3').classList.toggle('done',cs3); document.getElementById('cc3').textContent=cs3?'✓':''; }
  
  let valid = cs1 && cs2;
  if(needOdCalibration) valid = valid && cs3;
  document.getElementById('safety-ok-btn').disabled = !valid;
}
function closeSafety(e){ if(e.target===document.getElementById('modal-safety')) closeSafetyBtn(false); }
function closeSafetyBtn(ok){
  document.getElementById('modal-safety').classList.remove('open');
  if(ok){
    safetyOk=true;
    const b=document.getElementById('safety-badge');
    b.classList.add('ok');
    b.querySelector('span').innerHTML='<i class="fa-solid fa-unlock" style="font-size:9px;margin-right:2px"></i>Seguridad: Confirmada';
    toast('Checklist de seguridad validado ✓','ok');
  }
}

function checkSafetyRequirements() {
    const currentNeedOD = AST.some(n =>['turbidostat','zigzag','measure_od'].includes(n.type) || (n.type==='trigger' && n.tvar==='OD'));
    if (currentNeedOD && !needOdCalibration && safetyOk) {
        safetyOk = false;
        cs1 = cs2 = cs3 = false;
        const b = document.getElementById('safety-badge');
        b.classList.remove('ok');
        b.querySelector('span').innerHTML = '<i class="fa-solid fa-lock" style="font-size:9px;margin-right:2px"></i>Seguridad: Revocada';
        toast('Requisitos cambiaron. Vuelve a confirmar la seguridad.', 'warn');
    }
    needOdCalibration = currentNeedOD;
}

document.getElementById('dev-sel').addEventListener('change', function(){ document.getElementById('dev-badge').textContent = this.value; });
document.getElementById('dev-badge').textContent = document.getElementById('dev-sel').value;
function getM(){ return document.getElementById('dev-sel').value; }
function getProg(){ return document.getElementById('prog-sel').value; }

// ── Node factory ──────────────────────────────────────────
function uid(){ return 'n'+(++nodeCounter); }
function mkNode(type){
  const id=uid(), b={id,type};
  switch(type){
    case 'init_temp':   return {...b, temp:37.0};
    case 'init_od':     return {...b, od:0.3};
    case 'init_stir':   return {...b, speed:0.5};
    case 'thermostat':  return {...b, temp:37.0};
    case 'ramp_temp':   return {...b, temp_start:37.0, temp_end:42.0, duration:60};
    case 'led':         return {...b, led:'LEDB', power:0.1, mode:'on', duration:1, unit:'min'};
    case 'uv':          return {...b, power:0.5, mode:'on', duration:1, unit:'min'};
    case 'pump':        return {...b, pump:'Pump1', power:0.5, duration:5.0};
    case 'turbidostat': return {...b, state:'on'};
    case 'chemostat':   return {...b, state:'on', p1:0.02, p2:0.1};
    case 'zigzag':      return {...b, state:'on', zig:0.04};
    case 'measure_od':  return {...b};
    case 'wait':        return {...b, unit:'min', duration:1};
    case 'loop':        return {...b, count:10, children:[]};
    case 'trigger':     return {...b, tvar:'OD', op:'>=', val:0.5, behavior:'wait', children:[]};
    case 'log':         return {...b, msg:'Mensaje de control'};
    default: return b;
  }
}

function cloneNodeDeep(n) {
    const c = JSON.parse(JSON.stringify(n));
    function traverse(node) {
        node.id = uid();
        if(node.children) node.children.forEach(traverse);
    }
    traverse(c);
    return c;
}

// ── AST helpers ───────────────────────────────────────────
function findNode(id, arr){
  arr=arr||AST;
  for(const n of arr){
    if(n.id===id) return {node:n, arr};
    if(n.children){ const r=findNode(id,n.children); if(r) return r; }
  } return null;
}
function delNode(id, arr){
  arr=arr||AST;
  for(let i=0;i<arr.length;i++){
    if(arr[i].id===id){arr.splice(i,1);return true;}
    if(arr[i].children&&delNode(id,arr[i].children)) return true;
  } return false;
}

// ── Singleton helpers (usados en moveNode, buildBlock, drag) ──
const SINGLETON_TYPES = ['init_temp','init_od','init_stir'];
function isFixedBlock(type){ return SINGLETON_TYPES.includes(type); }

function moveNode(id, dir){
  function mv(arr){
    for(let i=0;i<arr.length;i++){
      if(arr[i].id===id){
        const ni=i+dir; if(ni<0||ni>=arr.length) return true;
        // Regla de frontera: un singleton no puede intercambiarse con un libre y viceversa
        const fromFixed=isFixedBlock(arr[i].type);
        const toFixed  =isFixedBlock(arr[ni].type);
        if(fromFixed!==toFixed){ toast('Los bloques de Condiciones Iniciales siempre van primero.','warn'); return true; }
        [arr[i],arr[ni]]=[arr[ni],arr[i]]; return true;
      }
      if(arr[i].children&&mv(arr[i].children)) return true;
    }
  } mv(AST);
}

// ── Singletons & Exclusions ───────────────────────────────
function checkSingletons() {
  const singles = ['init_temp','init_od','init_stir'];

  // Verificar cuáles singletons están en el canvas
  const hasTemp  = AST.some(n => n.type === 'init_temp');
  const hasOD    = AST.some(n => n.type === 'init_od');
  const hasStir  = AST.some(n => n.type === 'init_stir');
  const allInitsDone = hasTemp && hasOD && hasStir;

  // Bloquear pills de singletons ya usados (comportamiento original)
  singles.forEach(type => {
    const pill = document.querySelector(`.pill[data-btype="${type}"]`);
    if(pill) {
      const exists = AST.some(n => n.type === type);
      if (exists) pill.classList.add('disabled'); else pill.classList.remove('disabled');
    }
  });

  // Bloquear TODAS las categorías inferiores hasta que los 3 singletons estén presentes
  const lockedTypes = [
    'thermostat','ramp_temp','led','uv','pump',         // Hardware
    'turbidostat','chemostat','zigzag',                  // Modos de Control
    'measure_od',                                        // Sensores
    'wait','loop','trigger','log'                        // Flujo y Lógica
  ];

  lockedTypes.forEach(type => {
    const pill = document.querySelector(`.pill[data-btype="${type}"]`);
    if (!pill) return;
    if (!allInitsDone) {
      pill.classList.add('disabled');
      pill.setAttribute('data-locked-by-init', '1');
    } else {
      // Solo desbloquear si no está bloqueado por otra razón (modos exclusivos)
      if (pill.getAttribute('data-locked-by-init') === '1') {
        pill.classList.remove('disabled');
        pill.removeAttribute('data-locked-by-init');
      }
    }
  });

  // Actualizar tooltip de categorías para orientar al usuario
  const catEls = document.querySelectorAll('.cat');
  catEls.forEach(cat => {
    if (cat.textContent.includes('Condiciones Iniciales')) return;
    if (!allInitsDone) {
      cat.style.opacity = '0.4';
      cat.title = 'Agrega primero los 3 bloques de Condiciones Iniciales';
    } else {
      cat.style.opacity = '';
      cat.title = '';
    }
  });

  // Modos exclusivos (comportamiento original, solo aplica si ya están desbloqueados)
  if (allInitsDone) {
    const modes = ['turbidostat','chemostat','zigzag'];
    const hasMode = AST.some(n => modes.includes(n.type));
    modes.forEach(type => {
      const pill = document.querySelector(`.pill[data-btype="${type}"]`);
      if(pill) {
        const isThisMode = AST.some(n => n.type === type);
        if(hasMode) pill.classList.add('disabled');
        else if(!pill.getAttribute('data-locked-by-init')) pill.classList.remove('disabled');
      }
    });
  }

  // ── Banner: init_od sin modo de control ──────────────────
  const banner = document.getElementById('canvas-warn-banner');
  if (banner) {
    const hasODNode   = AST.some(n => n.type === 'init_od');
    const hasModeNode = AST.some(n => ['turbidostat','chemostat','zigzag'].includes(n.type));
    banner.classList.toggle('visible', hasODNode && !hasModeNode);
  }
}

// ── Drag & Drop ───────────────────────────────────────────
document.querySelectorAll('.pill[draggable]').forEach(el=>{
  el.addEventListener('dragstart', e=>{
    if(el.classList.contains('disabled')) { e.preventDefault(); return; }
    dragFromPalette=el.dataset.btype; dragFromCanvas=null; e.dataTransfer.effectAllowed='copy';
  });
  el.addEventListener('dragend', ()=>{ dragFromPalette=null; });
});
function canvasDragOver(e){ e.preventDefault(); document.getElementById('dropzone').classList.add('vis'); }
function canvasDragLeave(e){ if(!document.getElementById('canvas').contains(e.relatedTarget)) document.getElementById('dropzone').classList.remove('vis'); }
function canvasDrop(e){
  e.preventDefault(); document.getElementById('dropzone').classList.remove('vis');
  if(dragFromPalette){ AST.push(mkNode(dragFromPalette)); refresh(); dragFromPalette=null; }
}

function addBlock(type, arr){ 
    const pill = document.querySelector(`.pill[data-btype="${type}"]`);
    if(pill?.classList.contains('disabled')){
        if(['turbidostat','chemostat','zigzag'].includes(type)) 
            toast('Solo un Modo de Control permitido a la vez.', 'warn');
        else if(pill.getAttribute('data-locked-by-init'))
            toast('Primero agrega los 3 bloques de Condiciones Iniciales.', 'warn');
        else 
            toast('Este bloque ya fue agregado (único).', 'warn');
        return;
    }
    (arr||AST).push(mkNode(type)); refresh(); 
}
function refresh(){ 
  _historySave();
  renderCanvas(); updateVol(); updateCount(); checkSingletons(); checkSafetyRequirements(); 
  document.getElementById('btn-send-cloud').disabled = true;
  _historyUpdateButtons();
}

// ── UNDO / REDO ───────────────────────────────────────────────
const _undoStack = [];   // snapshots anteriores
const _redoStack =[];   // snapshots para rehacer
let   _historyLock = false; // evita que undo/redo se guarden a sí mismos

function _historySave(){
  if(_historyLock) return;
  _undoStack.push(JSON.stringify({ast: AST, nc: nodeCounter}));
  if(_undoStack.length > 50) _undoStack.shift(); // máximo 50 pasos
  _redoStack.length = 0; // cualquier acción nueva borra el redo
}

function undo(){
  if(_undoStack.length < 2){ toast('Nada que deshacer', 'warn'); return; }
  _redoStack.push(_undoStack.pop()); // mueve el estado actual a redo
  const snap = JSON.parse(_undoStack[_undoStack.length - 1]);
  _historyLock = true;
  AST.length = 0;
  snap.ast.forEach(n => AST.push(n));
  nodeCounter = snap.nc;
  renderCanvas(); updateVol(); updateCount(); checkSingletons(); checkSafetyRequirements();
  document.getElementById('btn-send-cloud').disabled = true;
  _historyLock = false;
  _historyUpdateButtons();
  toast('Deshacer ✓', 'ok');
}

function redo(){
  if(!_redoStack.length){ toast('Nada que rehacer', 'warn'); return; }
  const snap = JSON.parse(_redoStack.pop());
  _undoStack.push(JSON.stringify({ast: AST, nc: nodeCounter}));
  _historyLock = true;
  AST.length = 0;
  snap.ast.forEach(n => AST.push(n));
  nodeCounter = snap.nc;
  renderCanvas(); updateVol(); updateCount(); checkSingletons(); checkSafetyRequirements();
  document.getElementById('btn-send-cloud').disabled = true;
  _historyLock = false;
  _historyUpdateButtons();
  toast('Rehacer ✓', 'ok');
}

function _historyUpdateButtons(){
  const u = document.getElementById('btn-undo');
  const r = document.getElementById('btn-redo');
  if(u) u.disabled = _undoStack.length < 2;
  if(r) r.disabled = _redoStack.length === 0;
}

// ── Render ────────────────────────────────────────────────
function renderCanvas(){
  const cv=document.getElementById('canvas');
  cv.querySelectorAll('.cb').forEach(e=>e.remove());
  document.getElementById('c-empty').style.display = AST.length?'none':'flex';
  AST.forEach((node,i)=>{ cv.insertBefore(buildBlock(node, i+1, AST), document.getElementById('dropzone')); });
}

// Devuelve el índice del último singleton en el AST top-level (-1 si ninguno)
function lastSingletonIdx(){
  let last = -1;
  for(let i=0;i<AST.length;i++){ if(isFixedBlock(AST[i].type)) last=i; }
  return last;
}

function buildBlock(node, step, parentArr, depth){
  depth=depth||0;
  const m=META[node.type]||{label:node.type,ico:'fa-question',col:'#888'};
  const fixed = isFixedBlock(node.type) && parentArr === AST; // singleton en el canvas raíz

  const div=document.createElement('div'); div.className='cb'; div.id='cb-'+node.id;

  // Los singletons no son arrastrables; los libres sí
  if(!fixed){
    div.setAttribute('draggable','true');
    div.addEventListener('dragstart', e=>{
      e.stopPropagation(); dragFromCanvas={id:node.id, parentArr}; dragFromPalette=null;
      e.dataTransfer.effectAllowed='move'; setTimeout(()=>div.style.opacity='0.45',0);
    });
    div.addEventListener('dragend', ()=>{ div.style.opacity=''; dragFromCanvas=null; });
  }

  div.addEventListener('dragover', e=>{ e.preventDefault(); e.stopPropagation(); div.classList.add('dover'); });
  div.addEventListener('dragleave', ()=>div.classList.remove('dover'));
  div.addEventListener('drop', e=>{
    e.preventDefault(); e.stopPropagation(); div.classList.remove('dover');
    if(dragFromCanvas && dragFromCanvas.id !== node.id){
      const fr=findNode(dragFromCanvas.id); const to=findNode(node.id);
      if(fr && to && fr.arr === to.arr){
        const fromIdx = fr.arr.indexOf(fr.node);
        const toIdx   = to.arr.indexOf(to.node);
        const fromFixed = isFixedBlock(fr.node.type);
        const toFixed   = isFixedBlock(to.node.type);
        // Regla: un libre no puede subir por encima de un singleton,
        // y un singleton no puede bajar por debajo de un libre.
        if(!fromFixed && toFixed){ toast('Los bloques de Condiciones Iniciales siempre van primero.','warn'); return; }
        if(fromFixed && !toFixed){ toast('Los bloques de Condiciones Iniciales siempre van primero.','warn'); return; }
        fr.arr.splice(fromIdx,1); fr.arr.splice(fr.arr.indexOf(to.node),0,fr.node); refresh();
      }
    } else if(dragFromPalette){
      if(SINGLETON_TYPES.includes(dragFromPalette) && AST.some(n=>n.type===dragFromPalette)) return;
      const r=findNode(node.id);
      if(r){
        const insertIdx = r.arr.indexOf(r.node);
        // Si se suelta sobre un singleton, insertar después del último singleton
        if(isFixedBlock(node.type) && !SINGLETON_TYPES.includes(dragFromPalette)){
          const afterSingletons = lastSingletonIdx() + 1;
          r.arr.splice(afterSingletons, 0, mkNode(dragFromPalette));
        } else {
          r.arr.splice(insertIdx, 0, mkNode(dragFromPalette));
        }
      }
      refresh(); dragFromPalette=null;
    }
  });

  const hdr=document.createElement('div'); hdr.className='cb-hdr';
  if(fixed){
    // Header simplificado para singletons: sin grip, sin botones de movimiento/eliminar/clonar
    hdr.innerHTML=
      `<div class="cb-step">${step}</div>`+
      `<div class="cb-ico" style="background:${m.col}18;color:${m.col}"><i class="fa-solid ${m.ico}"></i></div>`+
      `<div class="cb-ttl" style="color:${m.col}">${m.label}</div>`+
      `<div class="cb-acts"></div>`;
  } else {
    hdr.innerHTML=
      `<div class="cb-step">${step}</div><div class="cb-ico" style="background:${m.col}18;color:${m.col}"><i class="fa-solid ${m.ico}"></i></div><div class="cb-ttl" style="color:${m.col}">${m.label}</div><i class="fa-solid fa-grip-lines cb-grip"></i><div class="cb-acts">`+
      `<button class="cba clone" title="Duplicar" data-clone="${node.id}"><i class="fa-regular fa-copy"></i></button>`+
      `<button class="cba" title="Subir" data-id="${node.id}" data-dir="-1"><i class="fa-solid fa-chevron-up"></i></button>`+
      `<button class="cba" title="Bajar" data-id="${node.id}" data-dir="1"><i class="fa-solid fa-chevron-down"></i></button>`+
      `<button class="cba del" title="Eliminar" data-del="${node.id}"><i class="fa-solid fa-xmark"></i></button></div>`;
    hdr.querySelectorAll('.cba[data-dir]').forEach(btn=>btn.addEventListener('click', ()=>{ moveNode(btn.dataset.id, parseInt(btn.dataset.dir)); refresh(); }));
    hdr.querySelector('.cba[data-del]').addEventListener('click', ()=>{ delNode(hdr.querySelector('[data-del]').dataset.del); refresh(); });
    hdr.querySelector('.cba.clone').addEventListener('click', ()=>{
      const c = cloneNodeDeep(node);
      const idx = parentArr.indexOf(node);
      parentArr.splice(idx+1, 0, c);
      refresh();
    });
  }
  div.appendChild(hdr);

  const body=document.createElement('div'); body.className='cb-body';
  buildForm(node, body, parentArr); div.appendChild(body); return div;
}

// ── Form builder ──────────────────────────────────────────
function buildForm(node, body, parentArr){
  function row(lbl, el){ const d=document.createElement('div'); d.className='frow'; d.innerHTML=`<span class="flbl">${lbl}</span>`; d.appendChild(el); body.appendChild(d); return d; }
  function note(txt, cls){ const d=document.createElement('div'); d.className='fnote'+(cls?' '+cls:''); d.innerHTML=txt; body.appendChild(d); return d; }
  function numInput(field, val, min, max, step){
    const inp=document.createElement('input'); inp.type='number'; inp.className='finp'; inp.value=val; inp.step=step||'any'; inp.min=min; inp.max=max;
    function validate(){
      let v=parseFloat(inp.value);
      if(isNaN(v)){ inp.classList.add('err'); errEl.textContent='Número inválido.'; errEl.classList.add('vis'); return; }
      if(v<min){ inp.classList.add('err'); errEl.textContent='Mínimo: '+min; errEl.classList.add('vis'); inp.value=min; v=min; }
      else if(v>max){ inp.classList.add('err'); errEl.textContent='Máximo: '+max; errEl.classList.add('vis'); inp.value=max; v=max; }
      else { inp.classList.remove('err'); errEl.classList.remove('vis'); }
      node[field]=v; updateVol();
    }
    inp.addEventListener('input', validate); inp.addEventListener('blur', validate);
    const errEl=document.createElement('div'); errEl.className='ferr-msg';
    const wrap=document.createElement('div'); wrap.style.flex='1'; wrap.appendChild(inp); wrap.appendChild(errEl); return wrap;
  }
  function txtInput(field, val){
    const inp=document.createElement('input'); inp.type='text'; inp.className='finp-txt'; inp.value=val; inp.maxLength=200;
    inp.addEventListener('input', ()=>{ node[field]=inp.value; }); return inp;
  }
  function selEl(field, opts, val, onChangeCb){
    const s=document.createElement('select'); s.className='fsel';
    opts.forEach(([v,l])=>{ const o=document.createElement('option'); o.value=v; o.textContent=l; if(v==val) o.selected=true; s.appendChild(o); });
    s.addEventListener('change', ()=>{ node[field]=s.value; if(onChangeCb) onChangeCb(s.value); updateVol(); }); return s;
  }

  switch(node.type){
    case 'init_temp': case 'thermostat':
      row('Temperatura (°C)', numInput('temp', node.temp, 0, 50, 0.5));
      if(node.type==='thermostat') note('<i class="fa-solid fa-triangle-exclamation"></i> Requiere Seguridad. Máx: 50°C.','warn');
      break;
    
    case 'ramp_temp':
      row('Temp. Inicial (°C)', numInput('temp_start', node.temp_start, 0, 50, 0.5));
      row('Temp. Final (°C)', numInput('temp_end', node.temp_end, 0, 50, 0.5));
      row('Duración (Minutos)', numInput('duration', node.duration, 1, 10000, 1));
      note('<i class="fa-solid fa-arrow-trend-up"></i> Ajusta la temperatura progresivamente mediante interpolación matemática.','info');
      break;

    case 'init_od': row('OD objetivo', numInput('od', node.od, 0, 10, 0.01)); break;
    case 'init_stir': row('Velocidad (0-1)', numInput('speed', node.speed, 0, 1, 0.1)); note('<i class="fa-solid fa-info-circle"></i> Agitación magnética. 0.5 es estándar.','info'); break;

    case 'led': 
    case 'uv': {
      if(node.type === 'led') row('LED', selEl('led', Object.entries(LED_WL).map(([k,v])=>[k,k+' — '+v]), node.led));
      
      const rUnit = row('Unidad de tiempo', selEl('unit', [['min','Minutos (FSM)'],['sec','Segundos (Pulso)']], node.unit));
      const rDur = row('Duración', numInput('duration', node.duration, 0.1, 1440, 0.1));
      const rPwr = row('Potencia (0–1)', numInput('power', node.power, 0, 1, 0.01));
      
      row('Modo', selEl('mode', [['pulse','Encender por tiempo y apagar'],['on','Encender indefinidamente'],['off','Apagar']], node.mode, (val) => {
          rDur.style.display = (val === 'pulse') ? 'flex' : 'none'; 
          rUnit.style.display = (val === 'pulse') ? 'flex' : 'none'; 
          rPwr.style.display = (val === 'off') ? 'none' : 'flex';
      }));
      
      rDur.style.display = (node.mode === 'pulse') ? 'flex' : 'none';
      rUnit.style.display = (node.mode === 'pulse') ? 'flex' : 'none';
      rPwr.style.display = (node.mode === 'off') ? 'none' : 'flex';
      break;
    }

    case 'pump': {
      row('Bomba', selEl('pump', [['Pump1','Pump1 (In)'],['Pump2','Pump2 (Out)'],['Pump3','Pump3 (Aux)'],['Pump4','Pump4 (Aux)']], node.pump, () => { updatePumpNote(); updateVol(); }));
      row('Potencia (-1 a 1)', numInput('power', node.power, -1, 1, 0.01));
      row('Duración (segundos)', numInput('duration', node.duration, 0.1, 60, 0.1));
      const pnote=note('','');
      function updatePumpNote(){
        const flow = globalPumps[node.pump] || 1.0;
        const v=(Math.abs(node.power) * (node.duration/60.0) * flow).toFixed(3);
        pnote.innerHTML=`<i class="fa-solid fa-droplet"></i> Vol. inyectado estimado: <strong>${v} ml</strong> (Caudal: ${flow} ml/min)`;
        pnote.className='fnote';
      }
      updatePumpNote();
      body.querySelectorAll('input').forEach(i=>i.addEventListener('input',updatePumpNote));
      break;
    }

    case 'turbidostat': row('Estado', selEl('state', [['on','Activar'],['off','Desactivar']], node.state)); break;
    case 'chemostat': row('Estado', selEl('state', [['on','Activar'],['off','Desactivar']], node.state)); row('Tasa Pump1 (entrada)', numInput('p1', node.p1, 0, 1, 0.001)); row('Tasa Pump2 (salida)', numInput('p2', node.p2, 0, 1, 0.001)); break;
    case 'zigzag': row('Estado', selEl('state', [['on','Activar'],['off','Desactivar']], node.state)); row('Amplitud Zig (OD)', numInput('zig', node.zig, 0.01, 0.5, 0.01)); note('<i class="fa-solid fa-info-circle"></i> La frecuencia depende de la biología. Enciende el Turbidostato implícitamente.','info'); break;
    case 'measure_od': note('<i class="fa-solid fa-check-circle"></i> Auto-inyecta pausa del Stirrer para evitar ruido.','ok'); break;

    case 'wait': {
      row('Unidad de tiempo', selEl('unit', [['min','Minutos (FSM Seguro)'],['sec','Segundos (Pulso Corto bloqueante)'],['gen', 'Generaciones (Biológicas)']], node.unit));
      row('Duración', numInput('duration', node.duration, 0.1, 86400, 0.1));
      break;
    }

    case 'loop': {
      row('Repeticiones', numInput('count', node.count, 1, 100000, 1));
      appendChildrenSection(body, node.children, 'Bloques del bucle', node);
      break;
    }

    case 'trigger': {
      const TVARS=[['OD','OD actual'],['GrowthRate','Tasa de Crecimiento (\u03BC)'],['Generations','Generaciones Transcurridas'],['Temp','Temperatura IR'],['FP1','Fluorescencia 1 (FP1)'],['FP2','Fluorescencia 2 (FP2)'],['FP3','Fluorescencia 3 (FP3)']];
      const TOPS=[['>=','≥ mayor o igual'],['<=','≤ menor o igual'],['==','= igual a']];
      const TBEH=[['wait','Esperar hasta que se cumpla (Pausar)'],['if','Evaluar ahora (Saltar si no cumple)']];
      
      row('Comportamiento', selEl('behavior', TBEH, node.behavior));
      const tcond=document.createElement('div'); tcond.className='trigger-cond';
      const tr=document.createElement('div'); tr.className='frow'; tr.style.margin='0';
      const lbl=document.createElement('span'); lbl.className='flbl'; lbl.textContent='Si la medida de:';
      const sv=selEl('tvar', TVARS, node.tvar);
      const so=selEl('op', TOPS, node.op);
      const ni=numInput('val', node.val, -1000, 1000, 0.01);
      tr.append(lbl,sv,so,ni); tcond.appendChild(tr); body.appendChild(tcond);
      
      appendChildrenSection(body, node.children, 'Bloques a ejecutar', node);
      break;
    }

    case 'log': row('Mensaje', txtInput('msg', node.msg)); break;
  }
}

function appendChildrenSection(body, children, label, parentNode){
  const wrap=document.createElement('div'); wrap.style.marginTop='7px';
  const lbl=document.createElement('div'); lbl.className='fnote'; lbl.innerHTML='<i class="fa-solid fa-arrow-turn-down"></i> '+label+':'; wrap.appendChild(lbl);
  const ic=document.createElement('div'); ic.className='inner-blocks';
  children.forEach((c,i)=>ic.appendChild(buildBlock(c,i+1,children))); wrap.appendChild(ic);
  const addBtn=document.createElement('button'); addBtn.className='inner-add'; addBtn.innerHTML='<i class="fa-solid fa-plus"></i> Añadir bloque aquí';
  addBtn.addEventListener('click', ()=>openPicker(children)); wrap.appendChild(addBtn); body.appendChild(wrap);
}

function openPicker(arr){
  pickerTarget=arr; document.getElementById('picker-list').innerHTML='';
  Object.entries(META).forEach(([type,m])=>{
    if(['init_temp','init_od','init_stir'].includes(type) && arr!==AST) return;
    const d=document.createElement('div'); d.className='mpill';
    d.innerHTML=`<div class="pi" style="background:${m.col}18;color:${m.col};width:26px;height:26px;border-radius:5px;display:flex;align-items:center;justify-content:center;font-size:11px;flex-shrink:0"><i class="fa-solid ${m.ico}"></i></div><span style="font-size:12px">${m.label}</span>`;
    d.addEventListener('click',()=>{ arr.push(mkNode(type)); refresh(); closePickerBtn(); });
    document.getElementById('picker-list').appendChild(d);
  });
  document.getElementById('modal-picker').classList.add('open');
}
function closePicker(e){ if(e.target===document.getElementById('modal-picker')) closePickerBtn(); }
function closePickerBtn(){ document.getElementById('modal-picker').classList.remove('open'); pickerTarget=null; }

function calcVol(arr){
  let inV=0,outV=0;
  for(const n of (arr||AST)){
    if(n.type==='pump'){
      const flow = globalPumps[n.pump] || 1.0;
      const v = Math.abs(n.power) * (n.duration/60.0) * flow;
      if(n.pump==='Pump2'){ if(n.power>0) outV+=v; else inV+=v; }
      else{ if(n.power>0) inV+=v; else outV+=v; }
    }
    if(n.children){ const s=calcVol(n.children); inV+=s.inV*(n.count||1); outV+=s.outV*(n.count||1); }
  } return {inV,outV};
}
function updateVol(){
  const {inV,outV}=calcVol(AST); const net=Math.max(0,inV-outV); const pct=Math.min(100,(net/25)*100);
  document.getElementById('vol-bar').style.width=pct+'%'; document.getElementById('vol-bar').classList.toggle('danger',net>25);
  document.getElementById('vol-val').textContent=net.toFixed(2)+' / 25 ml'; document.getElementById('vol-val').style.color=net>25?'var(--danger)':'';
}
function updateCount(){
  function cnt(a){ return a.reduce((s,n)=>s+1+(n.children?cnt(n.children):0),0); }
  const c=cnt(AST); document.getElementById('blk-count').textContent=c+(c===1?' bloque':' bloques');
}

// ── COMPILE & VALIDATE ───────────────────────────────────────
function doCompile(){
  const M=getM(); const P=getProg();
  clearConsole(); const errs=[],warns=[];
  validate(AST,errs,warns,M);
  warns.forEach(w=>addMsg('warn','⚠',w));
  if(errs.length){
    errs.forEach(e=>addMsg('err','✖',e)); addMsg('err','✖','<strong>Compilación bloqueada.</strong> Corrige '+errs.length+' error(es).');
    toast('Compilación fallida — '+errs.length+' error(es)','err'); switchTab('console'); return;
  }
  const code = compileFSM(AST, M, P);
  rawPythonCode = code; // Guardar crudo para la nube
  document.getElementById('gen-code').innerHTML=highlight(code); document.getElementById('gen-code').dataset.raw=code;
  document.getElementById('code-status').textContent='Generado FSM · '+M+' · Programa '+P;
  document.getElementById('btn-send-cloud').disabled = false; // Habilitar botón de envío
  addMsg('ok','✔','<strong>Compilación exitosa.</strong> Listo para enviar a la nube.');
  toast('Compilación exitosa ✓','ok'); switchTab('code');
}

function validate(nodes,errs,warns,M){
  let usesOptics = false;
  for(let i=0;i<nodes.length;i++){
    const n=nodes[i];
    switch(n.type){
      case 'init_temp': case 'thermostat': case 'ramp_temp':
        if(!safetyOk) errs.push(`[${(META[n.type]&&META[n.type].label)||n.type}] Completa la Confirmación de Seguridad (Tubo insertado).`);
        let t = n.temp || n.temp_end || 0;
        if(t>50) errs.push(`[Termostato] ${t}°C supera el máximo de seguridad de 50°C. Peligro de quemar placa.`);
        if(t<25) warns.push(`[Temperatura] ${t}°C: Chi.Bio NO tiene refrigeración activa. No bajará de la temperatura ambiente.`);
        break;
      case 'led':
      case 'uv':
        let devName = n.type === 'led' ? `LED ${n.led}` : 'UV';
        if (n.power > 0.5) {
            if (n.mode === 'on') {
                errs.push(`[${devName}] Peligro Crítico: Encendido constante a potencia > 0.5. Quitará el experimento o quemará la placa. Modifica la potencia o ponle un tiempo.`);
            } else if (n.mode === 'pulse' && n.unit === 'min' && n.duration >= 2) {
                errs.push(`[${devName}] Peligro Crítico: Encendido a potencia > 0.5 durante ${n.duration} minutos. El disipador se sobrecalentará. Límite máximo para altas potencias es segundos o ráfagas cortas.`);
            }
        }
        if (n.mode === 'pulse' && n.unit === 'sec' && n.duration > 15) {
             errs.push(`[${devName}] Pulso de ${n.duration}s superado. Límite de sleep es 15s para no colapsar el ciclo. Usa "Minutos (FSM)".`);
        }
        break;
      case 'pump': if(n.duration>20) warns.push(`[Bomba ${n.pump}] Duración > 20s. Pausará la toma de datos del biorreactor.`); break;
      case 'wait': if(n.unit==='sec'&&n.duration>15) errs.push(`[Esperar] Seleccionaste segundos y pusiste más de 15s. Colapsará el ciclo principal. Usa "Minutos" o "Generaciones".`); break;
      case 'chemostat': if(n.p2<=n.p1) warns.push(`[Quimiostato] Pump2 (Out) debería ser mayor que Pump1 para mantener el nivel de líquido.`); break;
      case 'turbidostat': case 'zigzag': usesOptics=true; break;
      case 'trigger':
        if(n.tvar==='OD'||n.tvar==='GrowthRate') usesOptics=true;
        if(n.children) validate(n.children, errs, warns, M); break;
      case 'loop': if(n.children) validate(n.children, errs, warns, M); break;
    }
  }
  if (usesOptics && nodes === AST && !safetyOk) errs.push('<strong>[Sensores Ópticos]</strong> Confirma la Calibración "OD Zero" en el Checklist de Seguridad.');
  const {inV,outV}=calcVol(nodes); if(inV-outV>25 && nodes===AST) errs.push('[Bombas] Volumen de entrada neto superará los 25ml de capacidad del tubo de vidrio. Inundación inminente.');

  // ── Warning: measure_od antes del primer bloque de hardware ──
  if (nodes === AST) {
    const HW_TYPES = ['thermostat','ramp_temp','led','uv','pump','turbidostat','chemostat','zigzag'];
    let firstHwIdx = -1, firstMeasureBeforeHwIdx = -1;
    for (let i = 0; i < nodes.length; i++) {
      const t = nodes[i].type;
      if (HW_TYPES.includes(t) && firstHwIdx === -1) { firstHwIdx = i; }
      if (t === 'measure_od' && firstHwIdx === -1) { firstMeasureBeforeHwIdx = i; }
    }
    if (firstMeasureBeforeHwIdx !== -1) {
      warns.push(`[Medir OD — paso ${firstMeasureBeforeHwIdx + 1}] <strong>measure_od aparece antes del primer bloque de hardware.</strong> La medición se ejecutará con la configuración por defecto del reactor (no la del protocolo). Considera moverlo después de init_temp, thermostat o tu modo de control.`);
    }
  }
}

// ── FSM COMPILER ENGINE ─────────────────────────────────
function compileFSM(nodes, M, progName) {
    let states = {}; let sc = 1; 
    function allocateState() { return ++sc; }
    function write(state, lines) { if(!states[state]) states[state]=[]; if(Array.isArray(lines)) states[state].push(...lines); else states[state].push(lines); }

    function processNodes(nodeList, entryState, exitState) {
        let curr = entryState;
        if (nodeList.length === 0) { write(entryState, `sysData[M]['Custom']['Status'] = ${exitState}.0`); return; }
        
        for(let i=0; i<nodeList.length; i++) {
            const n = nodeList[i];
            
            // Initializers (Ignorados aquí, se procesan en 0.0)
            if (['init_temp','init_od','init_stir','turbidostat','chemostat','zigzag'].includes(n.type)) continue;

            if (n.type === 'wait' && n.unit === 'min') {
                let waitState = allocateState();
                write(curr, `sysData[M]['Custom']['param1'] = sysData[M]['Experiment']['cycles']`);
                write(curr, `sysData[M]['Custom']['Status'] = ${waitState}.0`);
                let next = (i === nodeList.length - 1) ? exitState : allocateState();
                write(waitState, `if (sysData[M]['Experiment']['cycles'] - sysData[M]['Custom']['param1']) >= ${n.duration}:`);
                write(waitState, `    sysData[M]['Custom']['Status'] = ${next}.0`);
                curr = next;
            }
            else if (n.type === 'wait' && n.unit === 'gen') {
                let waitState = allocateState();
                write(curr, `sysData[M]['Custom']['param2'] = sysData[M]['Custom'].get('Generations', 0.0)`);
                write(curr, `sysData[M]['Custom']['Status'] = ${waitState}.0`);
                let next = (i === nodeList.length - 1) ? exitState : allocateState();
                write(waitState, `if (sysData[M]['Custom'].get('Generations', 0.0) - sysData[M]['Custom']['param2']) >= ${n.duration}:`);
                write(waitState, `    sysData[M]['Custom']['Status'] = ${next}.0`);
                curr = next;
            }
            else if ((n.type === 'led' || n.type === 'uv') && n.mode === 'pulse' && n.unit === 'min') {
                let waitState = allocateState();
                let dev = n.type === 'led' ? n.led : 'UV';
                write(curr, `sysData[M]['${dev}']['target'] = ${n.power}`);
                write(curr, `SetOutputOn(M, '${dev}', 1)`);
                write(curr, `sysData[M]['Custom']['param1'] = sysData[M]['Experiment']['cycles']`);
                write(curr, `sysData[M]['Custom']['Status'] = ${waitState}.0`);
                let next = (i === nodeList.length - 1) ? exitState : allocateState();
                write(waitState, `if (sysData[M]['Experiment']['cycles'] - sysData[M]['Custom']['param1']) >= ${n.duration}:`);
                write(waitState, `    SetOutputOn(M, '${dev}', 0)`);
                write(waitState, `    sysData[M]['Custom']['Status'] = ${next}.0`);
                curr = next;
            }
            else if (n.type === 'ramp_temp') {
                let rampState = allocateState();
                write(curr, `sysData[M]['Custom']['param1'] = sysData[M]['Experiment']['cycles']`);
                write(curr, `sysData[M]['Custom']['Status'] = ${rampState}.0`);
                let next = (i === nodeList.length - 1) ? exitState : allocateState();
                
                write(rampState, `_elapsed = sysData[M]['Experiment']['cycles'] - sysData[M]['Custom']['param1']`);
                write(rampState, `if _elapsed <= ${n.duration}:`);
                write(rampState, `    _target_t = ${n.temp_start} + (${n.temp_end} - ${n.temp_start}) * (_elapsed / ${n.duration})`);
                write(rampState, `    sysData[M]['Thermostat']['target'] = _target_t`);
                write(rampState, `    SetOutputOn(M, 'Thermostat', 1)`);
                write(rampState, `else:`);
                write(rampState, `    sysData[M]['Thermostat']['target'] = ${n.temp_end}`);
                write(rampState, `    SetOutputOn(M, 'Thermostat', 1)`);
                write(rampState, `    sysData[M]['Custom']['Status'] = ${next}.0`);
                curr = next;
            }
            else if (n.type === 'trigger') {
                let bodyEntry = n.children.length > 0 ? allocateState() : ((i === nodeList.length - 1) ? exitState : allocateState());
                let nextState = (i === nodeList.length - 1) ? exitState : allocateState();
                
                const vmap={OD:"sysData[M]['OD']['current']",GrowthRate:"sysData[M]['GrowthRate']['current']",Temp:"sysData[M]['ThermometerIR']['current']",FP1:"sysData[M]['FP1']['Emit1']",FP2:"sysData[M]['FP2']['Emit1']",FP3:"sysData[M]['FP3']['Emit1']",Generations:"sysData[M]['Custom'].get('Generations', 0.0)"};
                let cond = `${vmap[n.tvar]} ${n.op} ${n.val}`;
                
                if (n.behavior === 'wait') {
                    write(curr, `if ${cond}:`); write(curr, `    sysData[M]['Custom']['Status'] = ${bodyEntry}.0`);
                } else {
                    write(curr, `if ${cond}:`); write(curr, `    sysData[M]['Custom']['Status'] = ${bodyEntry}.0`);
                    write(curr, `else:`); write(curr, `    sysData[M]['Custom']['Status'] = ${nextState}.0`);
                }
                if (n.children.length > 0) processNodes(n.children, bodyEntry, nextState);
                curr = nextState;
            }
            else if (n.type === 'loop') {
                let loopVar = `loop_n${n.id}`; let bodyEntry = allocateState(); let nextState = (i === nodeList.length - 1) ? exitState : allocateState();
                write(curr, `sysData[M]['Custom']['${loopVar}'] = 0`); write(curr, `sysData[M]['Custom']['Status'] = ${bodyEntry}.0`);
                let bodyExit = allocateState();
                if (n.children.length > 0) processNodes(n.children, bodyEntry, bodyExit); else write(bodyEntry, `sysData[M]['Custom']['Status'] = ${bodyExit}.0`);
                
                write(bodyExit, `sysData[M]['Custom']['${loopVar}'] += 1`);
                write(bodyExit, `if sysData[M]['Custom']['${loopVar}'] < ${n.count}:`);
                write(bodyExit, `    sysData[M]['Custom']['Status'] = ${bodyEntry}.0`);
                write(bodyExit, `else:`);
                write(bodyExit, `    sysData[M]['Custom']['Status'] = ${nextState}.0`);
                curr = nextState;
            }
            else {
                // Sincrónicos
                if (n.type === 'led' || n.type === 'uv') {
                    let dev = n.type === 'led' ? n.led : 'UV';
                    if (n.mode === 'on') { 
                        write(curr, `sysData[M]['${dev}']['target'] = ${n.power}`); 
                        write(curr, `SetOutputOn(M, '${dev}', 1)`); 
                    }
                    else if (n.mode === 'off') { 
                        write(curr, `SetOutputOn(M, '${dev}', 0)`); 
                    }
                    else if (n.mode === 'pulse' && n.unit === 'sec') {
                        write(curr, `sysData[M]['${dev}']['target'] = ${n.power}`);
                        write(curr, `SetOutputOn(M, '${dev}', 1)`);
                        write(curr, `time.sleep(${n.duration})`);
                        write(curr, `SetOutputOn(M, '${dev}', 0)`);
                    }
                }
                else if (n.type === 'pump') {
                    write(curr, `sysData[M]['${n.pump}']['target'] = ${n.power}`); write(curr, `SetOutputOn(M, '${n.pump}', 1)`);
                    write(curr, `time.sleep(${n.duration})`); write(curr, `SetOutputOn(M, '${n.pump}', 0)`);
                }
                else if (n.type === 'thermostat') { 
                    write(curr, `sysData[M]['Thermostat']['target'] = ${n.temp}`); write(curr, `SetOutputOn(M, 'Thermostat', 1)`);
                }
                else if (n.type === 'measure_od') {
                    write(curr, `_stirrer_prev = sysData[M]['Stir']['target']`); write(curr, `SetOutputOn(M, 'Stir', 0)`); write(curr, `time.sleep(3)`);
                    write(curr, `MeasureOD(M)`); write(curr, `sysData[M]['Stir']['target'] = _stirrer_prev`); write(curr, `SetOutputOn(M, 'Stir', 1)`);
                }
                else if (n.type === 'wait' && n.unit === 'sec') { write(curr, `time.sleep(${n.duration})`); }
                else if (n.type === 'log') { write(curr, `addTerminal(M, '${n.msg.replace(/'/g,"\\'")}')`); }
                
                if (i === nodeList.length - 1 && curr !== exitState) write(curr, `sysData[M]['Custom']['Status'] = ${exitState}.0`);
            }
        }
    }

    const L =[];
    L.push(`    elif (program == "${progName}"):`);
    
    let usesGenerations = false;
    function checkGen(arr) {
        for(let n of arr) { if(n.unit === 'gen' || n.tvar === 'Generations') usesGenerations = true; if(n.children) checkGen(n.children); }
    }
    checkGen(nodes);

    if(usesGenerations) {
        L.push(`        # --- MOTOR DE GENERACIONES BIOLÓGICAS ---`);
        L.push(`        if 'Generations' not in sysData[M]['Custom']:`);
        L.push(`            sysData[M]['Custom']['Generations'] = 0.0`);
        L.push(`        _gr = sysData[M]['GrowthRate']['current']`);
        L.push(`        if _gr > 0:`);
        L.push(`            sysData[M]['Custom']['Generations'] += max(0, (_gr / 0.693147) / 60.0)`);
        L.push(``);
    }

    L.push(`        current_status = sysData[M]['Custom']['Status']`);
    L.push(``);
    L.push(`        if current_status == 0.0:`);
    
    // Initializers 
    nodes.filter(n=>['init_temp','init_od','init_stir','turbidostat','chemostat','zigzag'].includes(n.type)).forEach(n=>{
        if(n.type==='init_temp'){ L.push(`            sysData[M]['Thermostat']['target'] = ${n.temp}`); L.push(`            SetOutputOn(M, 'Thermostat', 1)`); }
        if(n.type==='init_od') L.push(`            sysData[M]['OD']['target'] = ${n.od}`);
        if(n.type==='init_stir'){ L.push(`            sysData[M]['Stir']['target'] = ${n.speed}`); L.push(`            SetOutputOn(M, 'Stir', 1)`); }
        if(n.type==='turbidostat') { L.push(`            SetOutputOn(M, 'OD', ${n.state==='on'?1:0})`); }
        if(n.type==='chemostat') { L.push(`            sysData[M]['Chemostat']['ON'] = ${n.state==='on'?1:0}`); L.push(`            sysData[M]['Chemostat']['p1'] = ${n.p1}`); L.push(`            sysData[M]['Chemostat']['p2'] = ${n.p2}`); }
        if(n.type==='zigzag') { L.push(`            SetOutputOn(M, 'Zigzag', ${n.state==='on'?1:0})`); L.push(`            sysData[M]['Zigzag']['Zig'] = ${n.zig}`); if(n.state === 'on'){ L.push(`            SetOutputOn(M, 'OD', 1)  # Zigzag requiere Turbidostato`); } }
    });

    L.push(`            sysData[M]['Custom']['Status'] = 1.0`);
    L.push(``);

    let finalState = allocateState();
    processNodes(nodes, 1, finalState);

    Object.keys(states).sort((a,b)=>a-b).forEach(state => { L.push(`        elif current_status == ${state}.0:`); states[state].forEach(line => L.push(`            ${line}`)); });

    L.push(`        elif current_status == ${finalState}.0:`);
    L.push(`            addTerminal(M, 'Protocolo Finalizado')`);
    L.push(`            sysData[M]['Custom']['Status'] = 99.0`);
    L.push(`        elif current_status == 99.0:`);
    L.push(`            pass  # Reposo eterno`);

    return L.join('\n');
}

// ── ENVÍO CLOUD A GITHUB ─────────────────────────────────
async function sendToReactor() {
    if(!rawPythonCode) { toast("Compila el código primero", "warn"); return; }

    const M = getM();
    const cleanCode = rawPythonCode.replace(/[\u00B7\u2022\u2027]/g, "");

    try {
        addMsg("info", "🔗", "Enviando protocolo al Biorreactor...");
        const resp = await fetch('/injectProtocol/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: cleanCode, M: M })
        });
        const data = await resp.json();
        if(!resp.ok || data.error) throw new Error(data.error || 'Error ' + resp.status);
        toast("¡Protocolo enviado al Biorreactor!", "ok");
        addMsg("ok", "🚀", "Protocolo guardado en el reactor. Se ejecutará en el próximo ciclo.");
    } catch(e) {
        toast("Error al enviar al Biorreactor", "err");
        addMsg("err", "❌", `Error: ${e.message}`);
    }
}

// ── Syntax highlight ──────────────────────────────────────
function highlight(code){
  const KW=['for','while','if','elif','else','try','except','finally','return','in','pass','not','and','or','True','False','None','range','str','int','float','round','abs','math','max','min'];
  return code.split('\n').map(line=>{
    if(line.trim().startsWith('#')) return '<span class="py-cm">'+esc(line)+'</span>'; let h=esc(line);
    h=h.replace(/&#x27;([^&#]*)&#x27;/g,"<span class='py-str'>&#x27;$1&#x27;</span>"); h=h.replace(/\b(\d+\.?\d*(?:[eE][+-]?\d+)?)\b/g,'<span class="py-num">$1</span>');
    KW.forEach(k=>{ h=h.replace(new RegExp('\\b'+k+'\\b','g'),'<span class="py-kw">'+k+'</span>'); }); h=h.replace(/\b([a-zA-Z_]\w*)\s*\(/g,'<span class="py-fn">$1</span>('); return h;
  }).join('\n');
}
function copyCode(){ navigator.clipboard.writeText(rawPythonCode).then(()=>toast('Código copiado ✓','ok')); }

// ── EXPORT / IMPORT ───────────────────────────────────────────
function exportExperiment(){
  if(!AST.length){ toast('El canvas está vacío', 'warn'); return; }
  const suggestion = `protocolo_${getM()}`;
  const input = window.prompt('Nombre del archivo (sin extensión):', suggestion);
  if(input === null) return;
  const name = (input.trim() || suggestion).replace(/[^a-zA-Z0-9_\-\.]/g, '_');
  const data = {
    version: '1.1',
    date: new Date().toISOString(),
    reactor: getM(),
    program: getProg(),
    pumps: globalPumps,
    ast: AST
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${name}.chibio`;
  a.click();
  toast(`"${name}.chibio" exportado ✓`, 'ok');
  addMsg('ok','📦',`Experimento exportado como <strong>${name}.chibio</strong> (${AST.length} bloques).`);
}

function importExperiment(event){
  const file = event.target.files[0];
  if(!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    try {
      const data = JSON.parse(e.target.result);
      if(!data.ast || !Array.isArray(data.ast)) throw new Error('Formato inválido');
      if(!confirm(`¿Cargar experimento "${file.name}"?\nEsto reemplazará el canvas actual (${AST.length} bloques).`)) return;
      
      AST.length = 0;
      nodeCounter = 0;
      // Reassign IDs to avoid collisions
      function reassignIds(arr){
        for(const n of arr){ n.id = uid(); if(n.children) reassignIds(n.children); }
      }
      reassignIds(data.ast);
      data.ast.forEach(n => AST.push(n));
      if(data.pumps) Object.assign(globalPumps, data.pumps);
      
      // Restore reactor/program if saved
      if(data.reactor) document.getElementById('dev-sel').value = data.reactor;
      if(data.program) document.getElementById('prog-sel').value = data.program;
      
      refresh();
      toast(`Experimento cargado — ${AST.length} bloques ✓`, 'ok');
      addMsg('ok','📂',`Importado: <strong>${file.name}</strong> — ${AST.length} bloques restaurados en el canvas.`);
    } catch(err){
      toast('Error al importar: archivo inválido', 'err');
      addMsg('err','❌',`No se pudo importar: ${err.message}`);
    }
  };
  reader.readAsText(file);
  event.target.value = ''; // Reset so same file can be reimported
}

// ── AI ASSISTANT (GEMINI vía servidor) ───────────────────────────

function handleAIKeyPress(event) {
    if (event.key === "Enter") {
        event.preventDefault();
        triggerAIGeneration();
    }
}

async function triggerAIGeneration() {
    const inputEl = document.getElementById('ai-prompt-input');
    const btnEl = document.getElementById('ai-btn');
    const promptText = inputEl.value.trim();

    if (!promptText) {
        toast("Escribe una instrucción primero", "warn");
        return;
    }

    inputEl.disabled = true;
    btnEl.disabled = true;
    btnEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Pensando...';
    toast("IA procesando el lenguaje natural...", "info");

    try {
        const response = await fetch('/generateProtocol/', {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt: promptText })
        });

        if (!response.ok) throw new Error("Error HTTP " + response.status);

        const data = await response.json();
        if (data.error) throw new Error(data.error);

        let jsonString = data.ast;
        jsonString = jsonString.replace(/^```json\s*/i, '').replace(/```\s*$/i, '').trim();

        const generatedNodes = JSON.parse(jsonString);

        if (!Array.isArray(generatedNodes) || generatedNodes.length === 0) {
            throw new Error("El JSON devuelto está vacío o no es un array.");
        }

        function assignIds(nodes) {
            nodes.forEach(n => {
                n.id = uid();
                if (n.children) assignIds(n.children);
            });
        }
        assignIds(generatedNodes);

        _historySave();
        generatedNodes.forEach(node => AST.push(node));
        refresh();

        toast("¡Magia aplicada! Bloques generados ✨", "ok");
        addMsg("ok", "✨", `La IA transformó tu texto en ${generatedNodes.length} bloques.`);
        inputEl.value = "";

    } catch (error) {
        console.error("Error AI:", error);
        toast("Fallo al entender la instrucción", "err");
        addMsg("err", "❌", `Error IA: ${error.message}.`);
    } finally {
        // Restaurar la UI
        inputEl.disabled = false;
        btnEl.disabled = false;
        btnEl.innerHTML = '<i class="fa-solid fa-robot"></i> Generar';
        inputEl.focus();
    }
}

// ── GUIDED TOUR ───────────────────────────────────────────────
const TOUR_STEPS =[
  { sel: null, pos:'center',
    title:'¡Bienvenido a Chi.Bio Master Architect!',
    desc:'Esta herramienta te permite diseñar protocolos de biorreactor de forma visual, sin escribir código. Construyes el experimento bloque a bloque y al final genera el código Python.' },
  { sel:'.palette', pos:'right',
    title:'Panel de Bloques',
    desc:'Aquí viven todos los bloques disponibles, organizados por categoría. Haz clic en cualquiera o arrástralo al canvas del centro para añadirlo a tu protocolo.' },
  { sel:'.pill[data-btype="init_temp"]', pos:'right',
    title:'Condiciones Iniciales',
    desc:'Estos tres bloques definen el punto de partida del experimento — temperatura, OD objetivo y agitación. Solo puedes usar cada uno una vez, y siempre van al principio.' },
  { sel:'.pill[data-btype="thermostat"]', pos:'right',
    title:'Hardware — Temperatura y Luz',
    desc:'Controlan el hardware directamente durante el experimento: cambiar temperatura, hacer rampas graduales, encender LEDs de distintas longitudes de onda, o aplicar luz UV.' },
  { sel:'.pill[data-btype="turbidostat"]', pos:'right',
    title:'Modos de Control Continuo',
    desc:'Son los motores del experimento, los que mantienen una condición activa de forma continua. Solo puedes activar uno a la vez.' },
  { sel:'.pill[data-btype="trigger"]', pos:'right',
    title:'Lógica Condicional y Bucles',
    desc:'Los bloques más poderosos. El Trigger reacciona a datos del sensor en tiempo real para disparar acciones. El Bucle repite una secuencia cuantas veces necesites.' },
  { sel:'.canvas-panel', pos:'left',
    title:'Canvas — Tu Protocolo',
    desc:'Aquí construyes el experimento. Los bloques se ejecutan de arriba a abajo, en orden. Puedes arrastrarlos para reordenarlos, duplicarlos o eliminarlos en cualquier momento.' },
  { sel:'.ai-bar', pos:'top',
    title:'Copiloto de IA (NLU)',
    desc:'Escribe lo que quieres que haga el Biorreactor en lenguaje natural y la Inteligencia Artificial construirá los bloques automáticamente por ti.' },
  { sel:'.vol-bar-outer', pos:'top',
    title:'Volumen Estimado',
    desc:'Lleva la cuenta del volumen neto que inyectarán las bombas a lo largo del protocolo. Si superas los 25 ml el compilador bloqueará el experimento.' },
  { sel: null, pos:'top-bar', parentSel:'#arch-caudales-btn',
    title:'Caudales de Bombas',
    desc:'Abre la configuración de caudales globales para las 4 bombas peristálticas. Aquí defines cuántos ml por minuto entrega cada bomba.' },
  { sel: null, pos:'top-bar', parentSel:'#arch-reactor-group',
    title:'Reactor y Destino',
    desc:'Elige qué módulo Chi.Bio (M0–M7) ejecutará el protocolo y en qué ranura de programa (C1–C8) se guardará. El reactor activo en el Nexus se sincroniza automáticamente.' },
  { sel: null, pos:'top-bar', parentSel:'#arch-safety-badge',
    title:'Checklist de Seguridad',
    desc:'Antes de enviar un protocolo debes confirmar físicamente que el tubo de vidrio está insertado y que el sistema está listo. La pastilla cambia a verde al validar y habilita el envío.' },
  { sel: null, pos:'top-bar', parentSel:'#arch-export-btns',
    title:'Exportar e Importar',
    desc:'Guarda tu protocolo como archivo .chibio para compartirlo, hacer copia de seguridad o retomarlo en otra sesión. Importar carga un archivo .chibio sobre el canvas actual.' },
  { sel: null, pos:'top-bar', parentSel:'#arch-tour-btn',
    title:'Tour Guiado',
    desc:'¿Olvidaste cómo funciona algo? Este botón reinicia el tour que estás viendo ahora mismo. Siempre disponible mientras estés en la pestaña Architect.' },
  { sel: null, pos:'top-bar', parentSel:'#arch-hist-btns',
    title:'Historial y Canvas',
    desc:'El Architect guarda hasta 50 pasos de historial. Deshacer revierte la última acción, Rehacer la vuelve a aplicar. La papelera limpia el canvas completo sin posibilidad de deshacer.' },
  { sel: null, pos:'top-bar', parentSel:'#arch-compile-btns',
    title:'Compilar y Enviar',
    desc:'Compilar FSM valida el protocolo y genera el código Python. Si no hay errores, el botón Enviar al Biorreactor se activa para inyectar el protocolo directamente al reactor activo.' },
  { sel:'.rpanel', pos:'left',
    title:'Consola y Código Python',
    desc:'La Consola muestra errores y advertencias de validación en tiempo real. La pestaña Python FSM muestra el código generado con resaltado de sintaxis, listo para enviar.' }
];

let tourStep = 0;
let _tourActive = false;

function startTour(){
  localStorage.setItem('chibio_tour_done','1');
  tourStep = 0;
  _tourActive = true;
  _postParent({ type:'tourOverlay', active:true });
  document.body.classList.add('tour-active');
  document.getElementById('tour-overlay').classList.add('active');
  renderTourStep();
}

function renderTourStep(){
  if(!_tourActive) return;
  const step = TOUR_STEPS[tourStep];
  if(!step){ endTour(); return; }

  // Gestión cross-frame: dim del backdrop local y highlight en el topbar del padre
  const backdrop = document.getElementById('tour-backdrop');
  if(step.parentSel){
    backdrop.classList.add('dim');
    _postParent({ type:'tourHighlight', sel:step.parentSel });
  } else {
    // Dim local cuando no hay elemento que destacar (el box-shadow de tour-highlight no aplica)
    backdrop.classList.toggle('dim', !step.sel);
    _postParent({ type:'tourHighlight', sel:null });
  }

  document.getElementById('tour-title').textContent = step.title;
  document.getElementById('tour-desc').textContent  = step.desc;

  // Buttons
  const isLast  = tourStep === TOUR_STEPS.length-1;
  const isFirst = tourStep === 0;
  document.getElementById('tour-btn-next').textContent = isLast ? '¡Listo! 🎉' : 'Siguiente →';
  document.getElementById('tour-btn-prev').style.visibility = isFirst ? 'hidden' : 'visible';
  document.getElementById('tour-step-count').textContent = (tourStep+1) + ' / ' + TOUR_STEPS.length;

  // Highlight + box
  const el  = step.sel ? document.querySelector(step.sel) : null;
  const hl  = document.getElementById('tour-highlight');
  const box = document.getElementById('tour-box');
  let rect  = null;

  if(el){
    rect = el.getBoundingClientRect();
    if(rect.width > 0 && rect.height > 0){
      const PAD = 7;
      hl.style.display = 'block';
      hl.style.left    = (rect.left   - PAD) + 'px';
      hl.style.top     = (rect.top    - PAD) + 'px';
      hl.style.width   = (rect.width  + PAD*2) + 'px';
      hl.style.height  = (rect.height + PAD*2) + 'px';
    } else {
      hl.style.display = 'none';
      rect = null;
    }
  } else {
    hl.style.display = 'none';
  }
  _positionBox(box, rect, step.pos || 'right');
}

function _positionBox(box, rect, pos){
  const BW=340, BH=240, M=16;
  const VW=window.innerWidth, VH=window.innerHeight;
  let l, t;
  
  if(!rect){ 
    // NUEVA LÓGICA: Si la posición es 'top-bar', lo pegamos arriba del todo
    if(pos === 'top-bar') {
      l = (VW-BW)/2; 
      t = 10; 
    } else {
      l = (VW-BW)/2; 
      t = (VH-BH)/2; 
    }
  }
  else{
    switch(pos){
      case 'right':        l=rect.right+M;   t=rect.top;       break;
      case 'left':         l=rect.left-BW-M; t=rect.top;       break;
      case 'top':          l=rect.left;       t=rect.top-BH-M;  break;
      case 'bottom':       l=rect.left;       t=rect.bottom+M;  break;
      case 'bottom-left':  l=rect.right-BW;   t=rect.bottom+M;  break;
      case 'bottom-right': l=rect.left;       t=rect.bottom+M;  break;
      default:             l=rect.right+M;   t=rect.top;
    }
  }
  
  // Evitar que se salga de la pantalla
  l = Math.max(10, Math.min(l, VW-BW-10));
  t = Math.max(10, Math.min(t, VH-BH-10));
  box.style.left=l+'px'; box.style.top=t+'px';
}

function tourNext(){
  if(tourStep >= TOUR_STEPS.length-1){ endTour(); return; }
  tourStep++; renderTourStep();
}
function tourPrev(){
  if(tourStep <= 0) return;
  tourStep--; renderTourStep();
}
function endTour(){
  _tourActive = false;
  document.body.classList.remove('tour-active');
  document.getElementById('tour-overlay').classList.remove('active');
  document.getElementById('tour-backdrop').classList.remove('dim');
  const hl = document.getElementById('tour-highlight');
  hl.style.display='none';
  _postParent({ type:'tourOverlay', active:false });
}

if(!localStorage.getItem('chibio_tour_done')){ setTimeout(startTour, 900); }

function clearConsole(){ document.getElementById('console-wrap').innerHTML='<div class="console-empty-msg"><i class="fa-solid fa-shield-halved"></i><span>Motor M.E. listo.</span></div>'; }
function addMsg(type, icon, html){ const ce=document.getElementById('console-wrap').querySelector('.console-empty-msg'); if(ce) ce.remove(); const d=document.createElement('div'); d.className='cmsg '+type; d.innerHTML=icon+' '; const sp=document.createElement('span'); sp.innerHTML=html; d.appendChild(sp); document.getElementById('console-wrap').appendChild(d); }
function switchTab(name){ ['console','code'].forEach(t=>{ document.getElementById('rpane-'+t).classList.toggle('on',t===name); document.getElementById('rtab-'+t).classList.toggle('on',t===name); }); }
function toast(msg, type){ const ct=document.getElementById('toasts'); const d=document.createElement('div'); d.className='toast '+type; const ic={ok:'fa-check-circle',err:'fa-xmark-circle',warn:'fa-triangle-exclamation'}; d.innerHTML='<i class="fa-solid '+(ic[type]||'fa-info-circle')+'"></i> '+msg; ct.appendChild(d); setTimeout(()=>d.remove(),3000); }
function clearCanvas(){ if(!AST.length) return; AST.length=0; nodeCounter=0; refresh(); document.getElementById('gen-code').innerHTML='<span class="py-cm"># Canvas limpiado.</span>'; document.getElementById('gen-code').dataset.raw=''; rawPythonCode=''; document.getElementById('code-status').textContent='Sin compilar'; document.getElementById('btn-send-cloud').disabled = true; toast('Canvas limpiado','warn'); }
function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#x27;'); }

// ── JS TOOLTIP SYSTEM ─────────────────────────────────────────
(function(){
  const tip = document.createElement('div');
  tip.id = 'tooltip-el';
  document.body.appendChild(tip);
  let _tid = null;

  function show(el){
    const text = el.getAttribute('data-tip');
    if(!text) return;
    clearTimeout(_tid);
    tip.textContent = text;
    tip.style.opacity = '0';
    tip.style.display = 'block';

    const r  = el.getBoundingClientRect();
    const TW = 220, TH = tip.offsetHeight || 80;
    const VW = window.innerWidth, VH = window.innerHeight;
    const M  = 10;
    let l, t;

    // Default: right of element
    l = r.right + M;
    t = r.top + (r.height - TH) / 2;

    // If would overflow right → try left
    if(l + TW > VW - 4) { l = r.left - TW - M; }
    // If still off-screen left → put below
    if(l < 4) { l = r.left; t = r.bottom + M; }
    // Clamp vertical
    t = Math.max(6, Math.min(t, VH - TH - 6));
    // Clamp horizontal
    l = Math.max(6, Math.min(l, VW - TW - 6));

    tip.style.left  = l + 'px';
    tip.style.top   = t + 'px';
    tip.style.width = TW + 'px';
    _tid = setTimeout(()=>{ tip.style.opacity='1'; }, 120);
  }

  function hide(){
    clearTimeout(_tid);
    tip.style.opacity = '0';
    _tid = setTimeout(()=>{ tip.style.display='none'; }, 160);
  }

  // Event delegation — works for all current and future [data-tip] elements
  document.addEventListener('mouseover', e=>{
    const el = e.target.closest('[data-tip]');
    if(el) show(el);
  });
  document.addEventListener('mouseout', e=>{
    const el = e.target.closest('[data-tip]');
    if(el) hide();
  });
  // Hide on drag start to prevent dragging tooltip
  document.addEventListener('dragstart', ()=>{ tip.style.opacity='0'; tip.style.display='none'; });
})();

// ── BLOCK SELECTION ───────────────────────────────────────────
// Tracks which block is "selected" for keyboard shortcuts
let _selectedId = null;
document.addEventListener('click', e => {
  const cb = e.target.closest('.cb');
  if(cb){
    document.querySelectorAll('.cb.selected').forEach(el => el.classList.remove('selected'));
    const id = cb.id.replace('cb-','');
    if(_selectedId === id){ _selectedId = null; } // clic de nuevo deselecciona
    else { _selectedId = id; cb.classList.add('selected'); }
  } else {
    // clic fuera de un bloque deselecciona
    if(!e.target.closest('.cba') && !e.target.closest('.moverlay') && !e.target.closest('.ai-bar')){
      _selectedId = null;
      document.querySelectorAll('.cb.selected').forEach(el => el.classList.remove('selected'));
    }
  }
});

// ── KEYBOARD SHORTCUTS ────────────────────────────────────────
document.addEventListener('keydown', e => {
  const tag = document.activeElement?.tagName;
  const inField = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';

  // Ctrl+Z — Deshacer (funciona siempre)
  if(e.ctrlKey && !e.shiftKey && e.key === 'z'){ e.preventDefault(); undo(); return; }

  // Ctrl+Y o Ctrl+Shift+Z — Rehacer (funciona siempre)
  if((e.ctrlKey && e.key === 'y') || (e.ctrlKey && e.shiftKey && e.key === 'z')){ e.preventDefault(); redo(); return; }

  if(inField) return; // el resto solo aplica fuera de campos de texto

  // Supr / Backspace — eliminar bloque seleccionado
  if((e.key === 'Delete' || e.key === 'Backspace') && _selectedId){
    e.preventDefault();
    delNode(_selectedId); _selectedId = null; refresh();
    toast('Bloque eliminado', 'warn');
    return;
  }

  // Ctrl+D — duplicar bloque seleccionado
  if(e.ctrlKey && e.key === 'd' && _selectedId){
    e.preventDefault();
    const found = findNode(_selectedId);
    if(found){
      const clone = cloneNodeDeep(found.node);
      const idx = found.arr.indexOf(found.node);
      found.arr.splice(idx + 1, 0, clone);
      refresh(); toast('Bloque duplicado ✓', 'ok');
    }
    return;
  }

  // Flecha arriba — subir bloque seleccionado
  if(e.key === 'ArrowUp' && _selectedId){
    e.preventDefault(); moveNode(_selectedId, -1); refresh(); return;
  }

  // Flecha abajo — bajar bloque seleccionado
  if(e.key === 'ArrowDown' && _selectedId){
    e.preventDefault(); moveNode(_selectedId, 1); refresh(); return;
  }

  // Escape — deseleccionar
  if(e.key === 'Escape'){
    _selectedId = null;
    document.querySelectorAll('.cb.selected').forEach(el => el.classList.remove('selected'));
  }
});

refresh();

// ── Comunicación con el Nexus padre ──────────────────────
function _postParent(data){
  if(window.parent !== window)
    window.parent.postMessage(data, window.location.origin);
}

function _emitState(){
  if(window.parent === window) return;
  window.parent.postMessage({
    type: 'archState',
    canSend:   !document.getElementById('btn-send-cloud').disabled,
    safetyOk:  safetyOk
  }, window.location.origin);
}

window.addEventListener('message', function(e){
  if(!e.data) return;
  if(e.origin !== window.location.origin) return;
  if(e.data.type === 'setTheme'){
    document.body.setAttribute('data-theme', e.data.theme);
  }
  if(e.data.type === 'archCmd'){
    switch(e.data.cmd){
      case 'openPumpModal':  openPumpModal();  break;
      case 'openSafety':     openSafety();     break;
      case 'doCompile':      doCompile(); setTimeout(_emitState, 200); break;
      case 'sendToReactor':  sendToReactor();  break;
      case 'clearCanvas':    clearCanvas(); setTimeout(_emitState, 200); break;
      case 'undo':           undo(); setTimeout(_emitState, 200); break;
      case 'redo':           redo(); setTimeout(_emitState, 200); break;
      case 'export':         exportExperiment(); break;
      case 'tour':           startTour(); break;
      case 'importData':
        try {
          const data = JSON.parse(e.data.val);
          AST.length = 0; nodeCounter = 0;
          function reassignIds(arr){ for(const n of arr){ n.id = uid(); if(n.children) reassignIds(n.children); } }
          reassignIds(data.ast);
          data.ast.forEach(n => AST.push(n));
          if(data.pumps) Object.assign(globalPumps, data.pumps);
          if(data.reactor) { document.getElementById('dev-sel').value = data.reactor; document.getElementById('dev-badge').textContent = data.reactor; }
          if(data.program) document.getElementById('prog-sel').value = data.program;
          refresh();
          toast(`Experimento cargado — ${AST.length} bloques ✓`, 'ok');
        } catch(err){ toast('Error al importar', 'err'); }
        break;
      case 'setReactor':
        document.getElementById('dev-sel').value = e.data.val;
        document.getElementById('dev-badge').textContent = e.data.val;
        break;
      case 'setDestino':
        document.getElementById('prog-sel').value = e.data.val;
        break;
    }
  }
});

// Sobrescribimos la función de seguridad para que avise al Main cuando confirmes
const originalCloseSafetyBtn = closeSafetyBtn;
closeSafetyBtn = function(ok) {
  originalCloseSafetyBtn(ok);
  _emitState();
};

// Emitir estado inicial al cargar
window.addEventListener('load', function(){ setTimeout(_emitState, 500); });
