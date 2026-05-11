/* ── Nexus Main JS — extraído de index.html ────────────────────── */
/* Iniciar polling de datos del sistema */
setInterval(getSysData, 2000);

// ── Nexus Tab Navigation ──────────────────────────────────
var _nexusTab = 'main';

function _getArchFrame(){
  return document.querySelector('#nexus-architect iframe');
}

function archCmd(cmd, val){
  var f = _getArchFrame();
  if(f && f.contentWindow) f.contentWindow.postMessage({ type:'archCmd', cmd:cmd, val:val }, window.location.origin);
}

// Función para leer el archivo a importar y enviarlo al iframe
function handleArchImport(event) {
  var file = event.target.files[0];
  if(!file) return;
  var reader = new FileReader();
  reader.onload = function(e) {
    archCmd('importData', e.target.result);
  };
  reader.readAsText(file);
  event.target.value = ''; // Resetear input
}

function switchNexusTab(tab){
  _nexusTab = tab;
  ['main','architect','camera'].forEach(function(t){
    document.getElementById('nexus-'+t).style.display      = (t===tab) ? 'block' : 'none';
    document.getElementById('ntab-'+t).classList.toggle('active', t===tab);
  });
  
  // Mostrar barras según la pestaña
  document.getElementById('ctx-main').style.display      = (tab==='main')      ? 'flex' : 'none';
  document.getElementById('ctx-architect').style.display = (tab==='architect') ? 'flex' : 'none';
  document.getElementById('global-buttons').style.display = (tab==='main') ? 'flex' : 'none';

  if(tab==='architect'){
    var theme = document.documentElement.getAttribute('data-theme') || 'dark';
    setTimeout(function(){
      var f = _getArchFrame();
      if(f && f.contentWindow) f.contentWindow.postMessage({ type:'setTheme', theme:theme }, window.location.origin);
    }, 200);
  }
  if(tab==='main' && _lastData){
    setTimeout(function(){ _updateChartGrid(); _drawAllCharts(_lastData); }, 100);
  }
  if(tab==='camera'){
    loadCameraSettings();
  } else {
    _stopCamPoll();
  }
}

// Escuchar respuestas del Architect
window.addEventListener('message', function(e){
  if(!e.data) return;
  if(e.origin !== window.location.origin) return;
  if(e.data.type === 'tourOverlay'){
    var topbar = document.getElementById('topbar');
    var hlEl = document.getElementById('nexus-tour-highlight');
    var dL = document.getElementById('nexus-topbar-dim-left');
    var dR = document.getElementById('nexus-topbar-dim-right');
    if(!e.data.active){
      if(topbar) topbar.classList.remove('tour-dim');
      if(hlEl) hlEl.classList.remove('vis');
      if(dL) dL.classList.remove('vis');
      if(dR) dR.classList.remove('vis');
    } else {
      if(topbar) topbar.classList.add('tour-dim');
    }
  }
  if(e.data.type === 'tourHighlight'){
    var hl = document.getElementById('nexus-tour-highlight');
    var topbar = document.getElementById('topbar');
    var dL = document.getElementById('nexus-topbar-dim-left');
    var dR = document.getElementById('nexus-topbar-dim-right');
    if(!hl) return;
    if(!e.data.sel){
      hl.classList.remove('vis');
      if(dL) dL.classList.remove('vis');
      if(dR) dR.classList.remove('vis');
      if(topbar) topbar.classList.add('tour-dim');
      return;
    }
    if(topbar) topbar.classList.remove('tour-dim');
    var el = document.querySelector(e.data.sel);
    if(el){
      var r = el.getBoundingClientRect(), PAD = 7;
      var tbH = topbar ? topbar.getBoundingClientRect().height : 50;
      hl.style.left   = (r.left   - PAD) + 'px';
      hl.style.top    = (r.top    - PAD) + 'px';
      hl.style.width  = (r.width  + PAD*2) + 'px';
      hl.style.height = (r.height + PAD*2) + 'px';
      hl.classList.add('vis');
      if(dL){
        dL.style.width  = Math.max(0, r.left - PAD) + 'px';
        dL.style.height = tbH + 'px';
        dL.classList.add('vis');
      }
      if(dR){
        dR.style.left   = (r.right + PAD) + 'px';
        dR.style.width  = Math.max(0, window.innerWidth - r.right - PAD) + 'px';
        dR.style.height = tbH + 'px';
        dR.classList.add('vis');
      }
    }
  }
  if(e.data.type === 'archState'){
    var sendBtn = document.getElementById('arch-send-btn');
    if(sendBtn) sendBtn.disabled = !e.data.canSend;
    
    var badge = document.getElementById('arch-safety-badge');
    var txt   = document.getElementById('arch-safety-text');
    if(badge && txt){
      if(e.data.safetyOk){
        badge.classList.add('on');
        txt.innerHTML = '<i class="fa-solid fa-unlock" style="font-size:9px;margin-right:2px"></i>Seguridad: Confirmada';
      } else {
        badge.classList.remove('on');
        txt.innerHTML = '<i class="fa-solid fa-lock" style="font-size:9px;margin-right:2px"></i>Seguridad';
      }
    }
  }
});

// ── Control de Menú Móvil Superior ──
function toggleMobMenu() {
  var btn = document.getElementById('mob-menu-btn');
  var menu = document.getElementById('tb-content');
  if(btn) btn.classList.toggle('active');
  if(menu) menu.classList.toggle('open');
}

// ── Control de Tabs en Móvil Inferior ──
function switchMobTab(tabId, btn) {
  // Restaurar nexus-main si veníamos de la cámara
  document.getElementById('nexus-main').style.display = 'block';
  document.getElementById('nexus-camera').style.display = 'none';

  // Quitar active de todos los botones de tab móvil
  var tabs = document.querySelectorAll('.mob-tab');
  tabs.forEach(function(t){ t.classList.remove('active'); });
  if(btn) btn.classList.add('active');

  // Ocultar todos los contenedores de tab
  var containers = document.querySelectorAll('.tab-container');
  containers.forEach(function(c){ c.classList.remove('mob-active'); });

  // Mostrar el seleccionado
  var activeContainer = document.getElementById('tab-' + tabId);
  if(activeContainer) activeContainer.classList.add('mob-active');

  // Redibujar gráficas si se entra a la vista de charts
  if(tabId === 'charts') {
    if(typeof _updateChartGrid === 'function') _updateChartGrid();
    if(_lastData) _drawAllCharts(_lastData);
  }
}

function switchMobCamera(btn) {
  var tabs = document.querySelectorAll('.mob-tab');
  tabs.forEach(function(t){ t.classList.remove('active'); });
  if(btn) btn.classList.add('active');
  var containers = document.querySelectorAll('.tab-container');
  containers.forEach(function(c){ c.classList.remove('mob-active'); });
  document.getElementById('nexus-main').style.display = 'none';
  document.getElementById('nexus-camera').style.display = 'block';
  _checkCamOrientation();
  loadCameraSettings();
}

// Inicialización de tabs al abrir en móvil
var _wasMobile = window.innerWidth <= 768;
if(_wasMobile) {
  var firstBtn = document.querySelector('.mob-tab');
  switchMobTab('charts', firstBtn);
}
window.addEventListener('resize', function(){
  var isMobile = window.innerWidth <= 768;
  if(isMobile) {
    var anyActive = Array.from(document.querySelectorAll('.tab-container')).some(function(el){
      return el.classList.contains('mob-active');
    });
    if(!anyActive) {
      var firstBtn = document.querySelector('.mob-tab');
      switchMobTab('charts', firstBtn);
    }
  } else if(_wasMobile) {
    // Solo restaurar desktop al cruzar el umbral móvil→desktop
    switchNexusTab(_nexusTab || 'main');
  }
  _wasMobile = isMobile;
  syncMobileFluorescence();
  _checkCamOrientation();
});

// ── Sincronizar Fluorescencia en Móvil vs Desktop ──
function syncMobileFluorescence() {
  var isMobile = window.innerWidth <= 768;
  var fpMoveable = document.getElementById('fp-moveable');
  var deskDest = document.getElementById('cpane-fp');
  var mobDest = document.getElementById('fp-mob-body');
  
  if(isMobile) {
    if(!fpMoveable || !mobDest || !deskDest) return;
  if(fpMoveable.parentNode !== mobDest) {
      mobDest.appendChild(fpMoveable);
      document.getElementById('fp-mob-card').style.display = 'block';
      document.getElementById('fp-desktop-header').style.display = 'none';
      document.getElementById('adv-ctabs-header').style.display = 'none';
      switchPane('term'); // En Desktop la pestaña viva en avanzado será Terminal
    }
  } else {
    if(fpMoveable.parentNode !== deskDest) {
      deskDest.appendChild(fpMoveable);
      document.getElementById('fp-mob-card').style.display = 'none';
      document.getElementById('fp-desktop-header').style.display = 'flex';
      document.getElementById('adv-ctabs-header').style.display = 'flex';
    }
  }
}
syncMobileFluorescence(); // Ejecutar on load

// ── Control de Tema y Fullscreen ──
function toggleTheme() {
  var b = document.documentElement;
  var isLight = b.getAttribute('data-theme') === 'light';
  var newTheme = isLight ? 'dark' : 'light';
  b.setAttribute('data-theme', newTheme);
  localStorage.setItem('chibio-theme', newTheme);

  var icon = document.querySelector('#themeToggleBtn i');
  if(icon) icon.className = newTheme === 'light' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';

  // Propagar tema al iframe del Architect
  var archFrame = document.querySelector('#nexus-architect iframe');
  if(archFrame && archFrame.contentWindow){
    archFrame.contentWindow.postMessage({ type: 'setTheme', theme: newTheme }, window.location.origin);
  }

  if(_lastData) { _drawAllCharts(_lastData); }
}

function toggleFullscreen() {
  var doc = window.document;
  var docEl = doc.documentElement;

  var isFullscreen = doc.fullscreenElement || doc.webkitFullscreenElement || doc.mozFullScreenElement || doc.msFullscreenElement;

  if (!isFullscreen) {
    // Enter fullscreen
    var req = docEl.requestFullscreen || docEl.webkitRequestFullscreen || docEl.webkitRequestFullScreen || docEl.mozRequestFullScreen || docEl.msRequestFullscreen;
    if (req) {
      var result = req.call(docEl);
      // Handle Promise (modern browsers)
      if (result && result.catch) {
        result.catch(function(err) {
          console.warn('Fullscreen error:', err);
          spawnToast('warn', 'fa-solid fa-expand', 'Pantalla Completa', 'El navegador bloqueó el modo pantalla completa. Prueba con F11.', 4000);
        });
      }
    } else {
      spawnToast('warn', 'fa-solid fa-expand', 'No Disponible', 'Tu navegador no soporta la API de Pantalla Completa. Usa F11.', 4000);
    }
  } else {
    // Exit fullscreen
    var exit = doc.exitFullscreen || doc.webkitExitFullscreen || doc.webkitCancelFullScreen || doc.mozCancelFullScreen || doc.msExitFullscreen;
    if (exit) exit.call(doc);
  }

  // Update icon on fullscreen change
  _updateFullscreenIcon();
}

function _updateFullscreenIcon() {
  var ico = document.querySelector('#fullscreenBtn i');
  if (!ico) return;
  var isFS = document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement;
  ico.className = isFS ? 'fa-solid fa-compress' : 'fa-solid fa-expand';
}
document.addEventListener('fullscreenchange', _updateFullscreenIcon);
document.addEventListener('webkitfullscreenchange', _updateFullscreenIcon);
document.addEventListener('mozfullscreenchange', _updateFullscreenIcon);

// Actualizar el ícono de tema al cargar
document.addEventListener('DOMContentLoaded', function() {
  var th = localStorage.getItem('chibio-theme') || 'dark';
  var icon = document.querySelector('#themeToggleBtn i');
  if(icon) icon.className = th === 'light' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
});

/* ── drawChart2 propio con temas ─── */
var _CHART_COLORS = ['#00d68f','#e05555','#a78bfa','#4a9eff','#f0a500','#22d3ee'];
var _CHART_COLORS_LIGHT = ['#059669','#dc2626','#7c3aed','#2563eb','#d97706','#0891b2'];

var _DARK_OPTS = {
  backgroundColor:{fill:'transparent'},
  chartArea:{backgroundColor:'transparent', left:44, top:28, right:12, bottom:28, width:'100%', height:'100%'},
  legend:{textStyle:{color:'#a0bcd4',fontSize:10,fontName:'Nunito'},position:'top'},
  hAxis:{ textStyle:{color:'#607d95',fontSize:9,fontName:'Nunito'}, gridlines:{color:'#1e2638',count:4}, minorGridlines:{color:'#151b27'}, baselineColor:'#2a3650' },
  vAxis:{ textStyle:{color:'#607d95',fontSize:9,fontName:'Nunito'}, gridlines:{color:'#1e2638',count:4}, minorGridlines:{color:'#151b27'}, baselineColor:'#2a3650' },
  lineWidth:2, pointSize:0, curveType:'function',
  tooltip:{textStyle:{color:'#e2ecf8',fontName:'Nunito'},showColorCode:true},
  colors:_CHART_COLORS, fontName:'Nunito', fontSize:10
};

var _LIGHT_OPTS = {
  backgroundColor:{fill:'transparent'},
  chartArea:{backgroundColor:'transparent', left:44, top:28, right:12, bottom:28, width:'100%', height:'100%'},
  legend:{textStyle:{color:'#334155',fontSize:10,fontName:'Nunito'},position:'top'},
  hAxis:{ textStyle:{color:'#1e3a5f',fontSize:9,fontName:'Nunito'}, gridlines:{color:'#cdd5e0',count:4}, minorGridlines:{color:'#e2e8f0'}, baselineColor:'#94a3b8' },
  vAxis:{ textStyle:{color:'#1e3a5f',fontSize:9,fontName:'Nunito'}, gridlines:{color:'#cdd5e0',count:4}, minorGridlines:{color:'#e2e8f0'}, baselineColor:'#94a3b8' },
  lineWidth:2, pointSize:0, curveType:'function',
  tooltip:{textStyle:{color:'#0f172a',fontName:'Nunito'},showColorCode:true},
  colors:_CHART_COLORS_LIGHT, fontName:'Nunito', fontSize:10
};


/* Estado de sensores de temperatura visibles */
var _tempSensors = {ir:true, target:true, int:true, ext:true};

/* Estado de gráficas visibles */
var _visibleCharts = {od:true, mu:true, temp:true, pumps:true};

/* Datos globales del último updateData para redibujar */
var _lastData = null;

function _parseRecordStr(s){
  if(!s||s==='')return[];
  return s.split(',').map(function(v){return parseFloat(v.trim());}).filter(function(v){return !isNaN(v);});
}

function drawChart2(numSeries,chartNum,times,s1,s2,s3,s4,s5,s6,xLabel,yLabel,seriesNames){
  var containerId='chart_div'+chartNum;
  var el=document.getElementById(containerId);
  if(!el)return;

  var tArr=_parseRecordStr(times);
  if(tArr.length===0){return;}

  /* Para temperatura (chartNum===4) filtrar según _tempSensors */
  var seriesRaw=[s1,s2,s3,s4,s5,s6];
  var nameRaw=(seriesNames||'').split(',');
  var filteredSeries=[], filteredNames=[], filteredColors=[];

  if(chartNum===4){
    /* Orden: IR(T.Cultivo), Target(Objetivo), Int(T.Interior), Ext(T.Exterior) */
    var tempDefs=[
      {key:'ir',    data:s1, label:'T.Cultivo',  color:'#4a9eff'},
      {key:'target',data:s2, label:'Objetivo',    color:'#e05555'},
      {key:'int',   data:s3, label:'T.Interior',  color:'#f0a500'},
      {key:'ext',   data:s4, label:'T.Exterior',  color:'#22d3ee'},
    ];
    tempDefs.forEach(function(d){
      if(_tempSensors[d.key]){
        filteredSeries.push(d.data);
        filteredNames.push(d.label);
        filteredColors.push(d.color);
      }
    });
    if(filteredSeries.length===0)return;
  } else {
    filteredSeries=seriesRaw.slice(0,numSeries);
    filteredNames=nameRaw.slice(0,numSeries);
    if(chartNum===2){filteredColors=['#00d68f','#e05555'];}
    else if(chartNum===3){filteredColors=['#a78bfa'];}
    else if(chartNum===1){filteredColors=['#4a9eff','#00d68f','#a78bfa','#f0a500'];}
    else if(chartNum>=5){filteredColors=['#f0a500','#22d3ee'];}
    else{filteredColors=_CHART_COLORS;}
  }

  var data=new google.visualization.DataTable();
  data.addColumn('number',xLabel||'Time');
  filteredNames.forEach(function(n){data.addColumn('number',n);});

  for(var t=0;t<tArr.length;t++){
    var row=[tArr[t]];
    filteredSeries.forEach(function(s){
      var arr=_parseRecordStr(s+'');
      row.push(arr[t]!==undefined?arr[t]:null);
    });
    data.addRow(row);
  }

  var isLight = document.documentElement.getAttribute('data-theme') === 'light';
  var opts=JSON.parse(JSON.stringify(isLight ? _LIGHT_OPTS : _DARK_OPTS));
  opts.colors=filteredColors;
  opts.vAxis.title=yLabel||'';
  opts.vAxis.titleTextStyle={color:isLight?'#1e3a5f':'#607d95',fontSize:9,fontName:'Nunito'};

  try{
    var chart=new google.visualization.LineChart(el);
    chart.draw(data,opts);
  }catch(e){console.warn('Chart draw error',chartNum,e);}
}

/* Actualizar grid según gráficas visibles */
function _updateChartGrid(){
  var map={od:'cbox-od',mu:'cbox-mu',temp:'cbox-temp',pumps:'cbox-pumps'};
  var shown=Object.keys(_visibleCharts).filter(function(k){return _visibleCharts[k];});
  var n=shown.length;
  var grid=document.getElementById('charts4');
  if(!grid)return;

  /* Mostrar/ocultar */
  Object.keys(map).forEach(function(k){
    var el=document.getElementById(map[k]);
    if(el)el.style.display=_visibleCharts[k]?'flex':'none';
  });

  /* Reset grid-column en todos */
  Object.keys(map).forEach(function(k){
    var el=document.getElementById(map[k]);
    if(el)el.style.gridColumn='';
  });

  if(n===0){grid.style.gridTemplateColumns='1fr';grid.style.gridTemplateRows='1fr';return;}

  /* Columnas */
  var cols = n===1 ? '1fr' : '1fr 1fr';
  grid.style.gridTemplateColumns=cols;

  /* Filas: siempre 1fr para llenar el espacio */
  if(n===1){
    grid.style.gridTemplateRows='1fr';
    document.getElementById(map[shown[0]]).style.gridColumn='1 / -1';
  } else if(n===2){
    /* 2 cajas: una fila, cada una mitad */
    grid.style.gridTemplateRows='1fr';
  } else if(n===3){
    /* 2 filas: primeras dos en fila 1, tercera ocupa fila 2 completa */
    grid.style.gridTemplateRows='1fr 1fr';
    document.getElementById(map[shown[2]]).style.gridColumn='1 / -1';
  } else {
    /* 4: 2×2 */
    grid.style.gridTemplateRows='1fr 1fr';
  }
}

function toggleChart(key){
  _visibleCharts[key]=!_visibleCharts[key];
  var btn=document.getElementById('cht-btn-'+key);
  if(btn){btn.classList.toggle('on',_visibleCharts[key]);}
  _updateChartGrid();
  /* Redibujar si hay datos */
  if(_lastData)_drawAllCharts(_lastData);
}

function toggleTempSensor(key){
  _tempSensors[key]=!_tempSensors[key];
  var btn=document.getElementById('ts-btn-'+key);
  if(btn){btn.classList.toggle('on',_tempSensors[key]);}
  if(_lastData)_drawAllCharts(_lastData);
}

function _drawAllCharts(data){
  if(!data) return;
  var t=data.time.record+'';
  if(_visibleCharts.od)
    drawChart2(2,2,t,data.OD.record+'',data.OD.targetrecord+'','','','','','Time (h)','OD','OD,Target');
  if(_visibleCharts.mu)
    drawChart2(1,3,t,data.GrowthRate.record+'','','','','','','Time (h)','μ','μ');
  if(_visibleCharts.temp)
    drawChart2(4,4,t,data.ThermometerIR.record+'',data.Thermostat.record+'',data.ThermometerInternal.record+'',data.ThermometerExternal.record+'','','','Time (h)','°C','IR,Target,Int,Ext');
  if(_visibleCharts.pumps)
    drawChart2(1,1,t,data.Pump1.record+'','','','','','','Time (h)','Flujo','P1');
  var e1b=$('#FPEmit1B').val(),e2b=$('#FPEmit2B').val(),e3b=$('#FPEmit3B').val();
  if(e1b==='OFF')drawChart2(1,5,t,data.FP1.Emit1Record+'','','','','','','Time (h)','FP1','Em1');
  else drawChart2(2,5,t,data.FP1.Emit1Record+'',data.FP1.Emit2Record+'','','','','','Time (h)','FP1','Em1,Em2');
  if(e2b==='OFF')drawChart2(1,6,t,data.FP2.Emit1Record+'','','','','','','Time (h)','FP2','Em1');
  else drawChart2(2,6,t,data.FP2.Emit1Record+'',data.FP2.Emit2Record+'','','','','','Time (h)','FP2','Em1,Em2');
  if(e3b==='OFF')drawChart2(1,7,t,data.FP3.Emit1Record+'','','','','','','Time (h)','FP3','Em1');
  else drawChart2(2,7,t,data.FP3.Emit1Record+'',data.FP3.Emit2Record+'','','','','','Time (h)','FP3','Em1,Em2');
}

/* ── TOAST MANAGER PREMIUM ────────────────────────────────── */
var _TOAST_ICONS = {
  ok:   'fa-solid fa-circle-check',
  err:  'fa-solid fa-circle-xmark',
  warn: 'fa-solid fa-triangle-exclamation',
  info: 'fa-solid fa-circle-info'
};

function spawnToast(type, icon, title, message, durationMs) {
  var dur = durationMs || 4000;
  var container = document.getElementById('toasts');
  var el = document.createElement('div');
  el.className = 'toast t-' + (type || 'ok');
  el.style.setProperty('--toast-dur', dur + 'ms');
  el.innerHTML =
    '<div class="toast-body">' +
      '<div class="toast-icon"><i class="' + (icon || _TOAST_ICONS[type] || _TOAST_ICONS.info) + '"></i></div>' +
      '<div class="toast-text">' +
        '<div class="toast-title">' + (title || '') + '</div>' +
        (message ? '<div class="toast-msg">' + message + '</div>' : '') +
      '</div>' +
      '<button class="toast-close" onclick="this.closest(\'.toast\').remove()"><i class="fa-solid fa-xmark"></i></button>' +
    '</div>' +
    '<div class="toast-progress"><div class="toast-progress-fill"></div></div>';
  container.appendChild(el);
  setTimeout(function(){
    el.classList.add('removing');
    setTimeout(function(){ if(el.parentNode) el.remove(); }, 320);
  }, dur);
  return el;
}

// Backward-compatible wrapper
function toast(m, t) {
  spawnToast(t || 'ok', null, m, null, 3200);
}

function ajax(u,cb){$.ajax({type:'POST',url:u,success:function(r){if(cb)cb(r);getSysData();},error:function(){spawnToast('err',null,'Error de Red','No se pudo conectar al servidor.');}});}

/* ── CSV EXPORT ────────────────────────────────────────────── */
function exportToCSV() {
  if (!_lastData) {
    spawnToast('warn', null, 'Sin Datos', 'No hay datos disponibles para exportar.');
    return;
  }
  var d = _lastData;
  var tArr = _parseRecordStr(d.time.record + '');
  if (tArr.length === 0) {
    spawnToast('warn', null, 'Sin Datos', 'Las series de tiempo están vacías.');
    return;
  }
  var odArr = _parseRecordStr(d.OD.record + '');
  var odTgt = _parseRecordStr(d.OD.targetrecord + '');
  var muArr = _parseRecordStr(d.GrowthRate.record + '');
  var tIR   = _parseRecordStr(d.ThermometerIR.record + '');
  var tTgt  = _parseRecordStr(d.Thermostat.record + '');
  var tInt  = _parseRecordStr(d.ThermometerInternal.record + '');
  var tExt  = _parseRecordStr(d.ThermometerExternal.record + '');
  var p1    = _parseRecordStr(d.Pump1.record + '');
  var p2    = _parseRecordStr(d.Pump2.record + '');
  var p3    = _parseRecordStr(d.Pump3.record + '');
  var p4    = _parseRecordStr(d.Pump4.record + '');
  /* FP records — pueden ser arrays o vacíos */
  var fp1b  = d.FP1 ? _parseRecordStr((d.FP1.BaseRecord  || []) + '') : [];
  var fp1e1 = d.FP1 ? _parseRecordStr((d.FP1.Emit1Record || []) + '') : [];
  var fp2b  = d.FP2 ? _parseRecordStr((d.FP2.BaseRecord  || []) + '') : [];
  var fp2e1 = d.FP2 ? _parseRecordStr((d.FP2.Emit1Record || []) + '') : [];
  var fp3b  = d.FP3 ? _parseRecordStr((d.FP3.BaseRecord  || []) + '') : [];
  var fp3e1 = d.FP3 ? _parseRecordStr((d.FP3.Emit1Record || []) + '') : [];

  var rows = ['Tiempo(s),OD,OD_Target,GrowthRate_mu,Temp_IR,Temp_Target,Temp_Int,Temp_Ext,Pump1,Pump2,Pump3,Pump4,FP1_Base,FP1_Emit1,FP2_Base,FP2_Emit1,FP3_Base,FP3_Emit1'];
  for (var i = 0; i < tArr.length; i++) {
    rows.push([
      tArr[i]  != null ? tArr[i]  : '',
      odArr[i] != null ? odArr[i] : '',
      odTgt[i] != null ? odTgt[i] : '',
      muArr[i] != null ? muArr[i] : '',
      tIR[i]   != null ? tIR[i]   : '',
      tTgt[i]  != null ? tTgt[i]  : '',
      tInt[i]  != null ? tInt[i]  : '',
      tExt[i]  != null ? tExt[i]  : '',
      p1[i]    != null ? p1[i]    : '',
      p2[i]    != null ? p2[i]    : '',
      p3[i]    != null ? p3[i]    : '',
      p4[i]    != null ? p4[i]    : '',
      fp1b[i]  != null ? fp1b[i]  : '',
      fp1e1[i] != null ? fp1e1[i] : '',
      fp2b[i]  != null ? fp2b[i]  : '',
      fp2e1[i] != null ? fp2e1[i] : '',
      fp3b[i]  != null ? fp3b[i]  : '',
      fp3e1[i] != null ? fp3e1[i] : ''
    ].join(','));
  }
  var csv  = rows.join('\n');
  var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  var url  = URL.createObjectURL(blob);
  var a    = document.createElement('a');
  var dev  = d.UIDevice || 'ChiBio';
  var now  = new Date();
  var ts   = now.getFullYear() + '-' +
             String(now.getMonth()+1).padStart(2,'0') + '-' +
             String(now.getDate()).padStart(2,'0') + '_' +
             String(now.getHours()).padStart(2,'0') +
             String(now.getMinutes()).padStart(2,'0');
  a.href     = url;
  a.download = 'ChiBio_' + dev + '_' + ts + '.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  spawnToast('ok', 'fa-solid fa-file-csv', 'CSV Generado', 'Descargado: ' + a.download + ' — ' + (tArr.length) + ' puntos, 18 columnas.', 5000);
}

/* ── RIPPLE EFFECT ────────────────────────────────────────── */
function createRipple(e) {
  var btn = e.currentTarget;
  var circle = document.createElement('span');
  var d = Math.max(btn.clientWidth, btn.clientHeight);
  var rect = btn.getBoundingClientRect();
  circle.style.width = circle.style.height = d + 'px';
  circle.style.left = (e.clientX - rect.left - d / 2) + 'px';
  circle.style.top  = (e.clientY - rect.top  - d / 2) + 'px';
  circle.className = 'ripple-circle';
  var old = btn.querySelector('.ripple-circle');
  if (old) old.remove();
  btn.appendChild(circle);
  setTimeout(function(){ if(circle.parentNode) circle.remove(); }, 550);
}

// Auto-inject ripple on all primary buttons
document.addEventListener('DOMContentLoaded', function() {
  var selectors = '.btn, .ib, .mb, .dev-btn, .btn-csv, .mob-tab';
  document.querySelectorAll(selectors).forEach(function(el) {
    el.addEventListener('click', createRipple);
  });
});

/* ── Tabs ───────────────────────────────────────── */
function switchPane(n){
  ['fp','term','proto'].forEach(function(t){
    document.getElementById('cpane-'+t).classList.toggle('on',t===n);
    document.getElementById('ctab-'+t).classList.toggle('on',t===n);
  });
}

/* ── Protocolo IA — llama al endpoint del BeagleBone ── */
async function analyzeProtocol(){
  var btn = document.getElementById('proto-analyze-btn');
  var res = document.getElementById('proto-result');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Analizando...';
  res.innerHTML = '<span style="color:var(--tx3);font-style:italic;">Consultando al reactor...</span>';

  try {
    var resp = await fetch('/analyzeProtocol/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    if(!resp.ok) throw new Error('Error ' + resp.status);
    var data = await resp.json();
    if(data.error) throw new Error(data.error);

    document.getElementById('proto-raw-code').textContent = data.code || '—';

    var html = (data.analysis || 'Sin respuesta.').split('\n')
      .filter(function(l){ return l.trim(); })
      .map(function(p){ return '<p style="margin-bottom:8px;">' + p + '</p>'; })
      .join('');
    res.innerHTML = html;
    spawnToast('ok', null, 'Análisis listo', 'Protocolo interpretado correctamente.', 3500);

  } catch(e) {
    res.innerHTML = '<span style="color:var(--rd)"><i class="fa-solid fa-triangle-exclamation"></i> Error: ' + e.message + '</span>';
    spawnToast('err', null, 'Error', e.message, 5000);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-robot"></i> Analizar protocolo activo';
  }
}

/* ── Calibración colapsable ─────────────────────── */
var _calOpen = false;
function toggleCal(){
  _calOpen = !_calOpen;
  var body = document.getElementById('cal-body');
  var btn  = document.getElementById('cal-toggle-btn');
  var lbl  = document.getElementById('cal-toggle-label');
  body.classList.toggle('collapsed', !_calOpen);
  body.classList.toggle('expanded',   _calOpen);
  btn.classList.toggle('expanded', _calOpen);
  lbl.textContent = _calOpen ? 'Ocultar' : 'Ver';
}

/* ── Acciones ───────────────────────────────────── */
function changeDevice(M){ajax('/changeDevice/'+M,null);}
function doScanDevices(){ajax('/scanDevices/all',null);spawnToast('info','fa-solid fa-satellite-dish','Escaneando','Buscando dispositivos en la red...', 3000);}
function startExperiment(){ajax('/Experiment/1/0',null);spawnToast('ok','fa-solid fa-play','Experimento Iniciado','El experimento ha comenzado a ejecutarse.', 4000);}
function stopExperiment(){ajax('/Experiment/0/0',null);spawnToast('warn','fa-solid fa-stop','Experimento Detenido','El experimento se ha detenido.', 4000);}
function resetExperiment(){ajax('/ExperimentReset',null);spawnToast('warn','fa-solid fa-rotate-left','Reset','Todos los parámetros han sido reiniciados.', 3500);}
function setOD(){ajax('/SetOutputTarget/OD/0/'+$('#ODInput').val(),null);}
function measureOD(){ajax('/MeasureOD/0',null);}
function calibrateOD(){ajax('/CalibrateOD/OD0/0/'+$('#OD0Input').val()+'/'+$('#OD0Actual').val(),null);}
function setVolume(){ajax('/SetOutputTarget/Volume/0/'+$('#VolumeInput').val(),null);}
function toggleODRegulate(){ajax('/SetOutputOn/OD/2/0',null);}
function toggleZigzag(){ajax('/SetOutputOn/Zigzag/2/0',null);}
function measureTemp(w){ajax('/MeasureTemp/'+w+'/0',null);}
function setThermostat(){ajax('/SetOutputTarget/Thermostat/0/'+$('#ThermostatInput').val(),null);}
function toggleThermostat(){ajax('/SetOutputOn/Thermostat/2/0',null);}
function setStir(){ajax('/SetOutputTarget/Stir/0/'+$('#StirInput').val(),null);}
function toggleStir(){ajax('/SetOutputOn/Stir/2/0',null);}
function toggleCustom(){ajax('/SetCustom/'+$('#CustomProgram1').val()+'/'+$('#CustomInput').val(),null);}
function toggleLight(){ajax('/SetLightActuation/'+$('#LightExcite1').val(),null);}
function setLED(l){ajax('/SetOutputTarget/'+l+'/0/'+$('#'+l+'Input').val(),null);}
function adjLED(l,delta){
  var inp=$('#'+l+'Input');
  var v=Math.round((parseFloat(inp.val()||0)+delta)*10)/10;
  v=Math.max(0,Math.min(1,v));
  inp.val(v);
  ajax('/SetOutputTarget/'+l+'/0/'+v,null);
}
function switchLED(l,on){if(window._updatingLED)return;ajax('/SetOutputOn/'+l+'/'+(on?1:0)+'/0',null);}
function switchPump(p){ajax('/SetOutputOn/'+p+'/2/0',null);}
function dirPump(p){ajax('/Direction/'+p+'/0',null);}
function measureSpectrum(){ajax('/GetSpectrum/'+$('#SpectrumGain').val()+'/0',null);}
function measureFP(){ajax('/MeasureFP/0',null);}
function toggleFP(fp){var n=fp.slice(2);ajax('/SetFPMeasurement/'+fp+'/'+$('#FPExcite'+n).val()+'/'+$('#FPBase'+n).val()+'/'+$('#FPEmit'+n+'A').val()+'/'+$('#FPEmit'+n+'B').val()+'/'+$('#FPGain'+n).val(),null);}
function clearTerm(){ajax('/ClearTerminal/0',null);}

/* ── Cloud pill — pulso azul durante descarga ───── */
var _cloudPrev = '';
setInterval(function(){
  if(_nexusTab !== 'main') return;
  $.ajax({type:'GET',url:'/getCloudStatus/',dataType:'json',
    success:function(d){
      var p=document.getElementById('cloud-pill');
      if(!p) return;
      var t=document.getElementById('cloud-pill-text');
      var ico=document.getElementById('cloud-ico');
      p.className='cpill';
      ico.className='fa-solid fa-cloud cloud-ico';
      if(d.status==='downloading'||d.has_pending){
        p.classList.add('downloading');
        ico.className='fa-solid fa-arrows-rotate cloud-ico'; /* icono giratorio */
        t.textContent='Descargando...';
      }else if(d.status==='ok'){
        p.classList.add('ok');
        t.textContent='Cloud #'+d.inject_count;
        if(_cloudPrev!=='ok')toast('Protocolo inyectado! #'+d.inject_count,'ok');
      }else if(d.status==='new'){
        p.classList.add('new');
        t.textContent='Nuevo protocolo!';
      }else if(d.status==='error'){
        p.classList.add('err');
        t.textContent='Error Cloud';
      }else{
        t.textContent='Cloud';
      }
      _cloudPrev=d.status;
    }
  });
},1500);

/* ── Helpers internos ───────────────────────────── */
function _mb(id,on,cls){var e=document.getElementById(id);if(!e)return;e.classList.remove('on','on-rd','on-am','on-pu');if(on)e.classList.add(cls||'on');}

/* ══════════════════════════════════════════════════
   updateData — puente con HTMLScripts.js
══════════════════════════════════════════════════ */
function updateData(data){
  var running=Boolean(data.Experiment.ON),measuring=Boolean(data.OD.Measuring);

  /* Topbar */
  var pill=document.getElementById('exp-pill');pill.classList.toggle('on',running);
  document.getElementById('exp-pill-text').textContent=running?'Ejecutando':'Detenido';
  /* BUG FIX: pill móvil del topbar también debe actualizarse */
  var pillMob=document.getElementById('exp-pill-mob');if(pillMob)pillMob.classList.toggle('on',running);
  var pillMobTxt=document.getElementById('exp-pill-text-mob');if(pillMobTxt)pillMobTxt.textContent=running?'Ejecutando':'Detenido';
  document.getElementById('StartTime').textContent=running?data.Experiment.startTime:'—';
  document.getElementById('cyc').textContent='Ciclo '+(data.Experiment.cycles||'—');
  document.getElementById('TName').textContent=data.UIDevice||'—';
  /* BUG FIX: TName2 en card FSM también debe actualizarse */
  var tn2=document.getElementById('TName2');if(tn2)tn2.textContent=data.UIDevice||'—';

  /* Device pills */
  ['M0','M1','M2','M3','M4','M5','M6','M7'].forEach(function(m,i){
    var b=document.getElementById('Device'+i);
    var ok=data.presentDevices&&data.presentDevices[m]===1;
    b.disabled=!ok; b.classList.toggle('active',data.UIDevice===m);
  });
  document.getElementById('ExperimentStart').disabled=running;
  document.getElementById('ExperimentReset').disabled=running;
  document.getElementById('ExperimentStop').disabled=!running;
  ['GetSpectrum','ODMeasure','MeasureFP','FP1Switch','FP2Switch','FP3Switch'].forEach(function(id){var el=document.getElementById(id);if(el)el.disabled=measuring;});
  /* BUG FIX: botón FP móvil también debe deshabilitarse al medir */
  var fpMob=document.getElementById('MeasureFPMob');if(fpMob)fpMob.disabled=measuring;

  /* OD */
  document.getElementById('ODCurrent').textContent=data.OD.current.toFixed(3);
  document.getElementById('ODTarget').textContent=data.OD.target.toFixed(3);
  document.getElementById('OD0Current').textContent=data.OD0.target.toFixed(0);
  document.getElementById('ODRawVal').textContent=data.OD0.raw.toFixed(0);
  document.getElementById('VolumeCurrent').textContent=data.Volume.target.toFixed(1);
  _mb('ODRegulate',Boolean(data.OD.ON),'on');
  _mb('Zigzag',data.Zigzag.ON===1,'on');

  /* Temperatura */
  document.getElementById('TempCurrent').textContent=data.ThermometerExternal.current.toFixed(1)+'°';
  document.getElementById('TempCurrent2').textContent=data.ThermometerInternal.current.toFixed(1)+'°';
  document.getElementById('TempCurrent3').textContent=data.ThermometerIR.current.toFixed(1)+'°';
  document.getElementById('ThermostatTarget').textContent=data.Thermostat.target.toFixed(1)+'°';
  _mb('ThermostatSwitch',data.Thermostat.ON===1,'on-rd');

  /* Agitación */
  var stirOn=data.Stir.ON===1;
  document.getElementById('StirCurrent').textContent=data.Stir.target.toFixed(2);
  var orb=document.getElementById('stir-orb');orb.classList.toggle('spin',stirOn);
  if(stirOn){orb.style.setProperty('--spd',Math.max(0.4,3-data.Stir.target*2.5)+'s');}
  _mb('StirSwitch',stirOn,'on-am');

  /* Custom FSM */
  var fsmSt=data.Custom.Status;
  document.getElementById('CustomStatus').textContent=fsmSt.toFixed(1);
  document.getElementById('custom-prog-badge').textContent=data.Custom.Program||'C1';
  var fsmOn=data.Custom.ON===1;
  _mb('CustomSwitch',fsmOn,'on-pu');
  /* Glow más intenso cuando activo */
  document.getElementById('fsm-display').classList.toggle('active',fsmOn);
  /* Barra de estado (ejemplo: estado/10 como porcentaje) */
  var barPct=Math.min(100,Math.abs(fsmSt)*10);
  document.getElementById('fsm-bar-fill').style.width=barPct+'%';

  document.getElementById('LightCurrent').textContent=data.Light.Excite||'—';
  _mb('LightSwitch',data.Light.ON===1,'on');

  /* LEDs — inicializar flag de guard */
  window._updatingLED = window._updatingLED || false;
  ['LEDB','LEDC','LEDD','LEDF','LEDG','LASER650','UV'].forEach(function(l){
    if(!data[l])return;
    var on=data[l].ON===1;
    var cur=document.getElementById(l+'Current');if(cur)cur.textContent=data[l].target.toFixed(2);
    var row=document.getElementById('led-row-'+l);if(row)row.classList.toggle('on',on);
    var tog=document.getElementById(l+'-tog');if(tog){window._updatingLED=true;tog.checked=on;window._updatingLED=false;}
  });

  /* Detección de versión de hardware LED — muestra/oculta filas según V1 o V2 */
  if (!window._ledVersionApplied || window._ledVersionApplied !== data.UIDevice) {
    window._ledVersionApplied = data.UIDevice;
    var isV1 = data.Version && data.Version.LED === 1;
    var ledRowG = document.getElementById('led-row-LEDG');
    if (ledRowG) ledRowG.style.display = isV1 ? '' : 'none';
    /* Actualizar opciones de excitación en FP según hardware */
    var ledOptsV1 = [{v:'LEDB',t:'457nm'},{v:'LEDC',t:'500nm'},{v:'LEDD',t:'523nm'},
                     {v:'LEDF',t:'623nm'},{v:'LEDG',t:'6500K'},{v:'LASER650',t:'Láser'}];
    var ledOptsV2 = [{v:'LEDB',t:'457nm'},{v:'LEDC',t:'500nm'},{v:'LEDD',t:'523nm'},
                     {v:'LEDF',t:'623nm'},{v:'LASER650',t:'Láser'}];
    var opts = isV1 ? ledOptsV1 : ledOptsV2;
    var optsHtml = opts.map(function(o){return '<option value="'+o.v+'">'+o.t+'</option>';}).join('');
    ['FPExcite1','FPExcite2','FPExcite3'].forEach(function(id){
      var el=document.getElementById(id);if(el)el.innerHTML=optsHtml;
    });
  }

  /* Bombas — iluminación azul card + rows + texto botón On/Off */
  var anyPumpOn=false;
  for(var i=1;i<=4;i++){
    var pk='Pump'+i;if(!data[pk])continue;
    var pon=data[pk].ON===1;
    if(pon)anyPumpOn=true;
    document.getElementById('pump-row-'+i).classList.toggle('on',pon);
    var swBtn=document.getElementById(pk+'Switch');
    if(swBtn){swBtn.textContent=pon?'Off':'On';}
  }
  /* Card completa de bombas se ilumina si alguna está on */
  document.getElementById('pumps-card').classList.toggle('pump-on',anyPumpOn);

  var turbOn=Boolean(data.OD.ON);
  /* Espectrómetro */
  var sp=data.AS7341&&data.AS7341.spectrum;
  if(sp){['410','440','470','510','550','583','620','670'].forEach(function(w){document.getElementById(w+'nmSense').textContent=sp['nm'+w]||'—';});document.getElementById('ClearSense').textContent=sp.CLEAR||'—';}

  /* FP */
  ['FP1','FP2','FP3'].forEach(function(fp,fi){
    var n=fi+1;if(!data[fp])return;
    document.getElementById('FPBase'+n+'Value').textContent=data[fp].Base.toFixed(0);
    document.getElementById('FPEmit'+n+'AValue').textContent=data[fp].Emit1.toFixed(3);
    document.getElementById('FPEmit'+n+'BValue').textContent=data[fp].Emit2.toFixed(3);
    var sw=document.getElementById(fp+'Switch');
    if(sw){sw.style.borderColor=data[fp].ON===1?'var(--gr)':'';sw.style.color=data[fp].ON===1?'var(--gr)':'';}
    var e1=document.getElementById('fp'+n+'-em1');if(e1)e1.style.width=Math.min(100,data[fp].Emit1*100)+'%';
    var e2=document.getElementById('fp'+n+'-em2');if(e2)e2.style.width=Math.min(100,data[fp].Emit2*100)+'%';
  });

  /* Terminal */
  document.getElementById('termI').textContent=data.Terminal.text;

  /* Charts */
  _lastData = data;
  if(document.getElementById('GraphReplot').value!=data.time.record.length||document.getElementById('FPRefresh').innerHTML!=data.UIDevice){
    document.getElementById('GraphReplot').value=data.time.record.length;
    document.getElementById('FPRefresh').innerHTML=data.UIDevice;
    _updateChartGrid();
    _drawAllCharts(data);
  }
  if(_nexusTab === 'camera') _updateCamReactorInfo();
}

// ── Camera Settings ────────────────────────────────────────
var _camBase = (function(){
  var el = document.getElementById('nexus-camera');
  var base = el ? (el.getAttribute('data-cam-base') || '') : '';
  return base.replace(/\/$/, '') || 'http://localhost:5001';
})();

// Apuntar el feed al endpoint correcto en cuanto carga el DOM
(function(){
  var feed = document.getElementById('cam-feed');
  if(!feed) return;
  feed.onerror = function(){ _setCamStatus('offline'); };
  feed.src = _camBase + '/video_feed';
})();

var _camDebounce = null;
var _camPollTimer = null;

function onCamSlider(){
  var b = document.getElementById('cam-brightness');
  var c = document.getElementById('cam-contrast');
  var s = document.getElementById('cam-saturation');
  var q = document.getElementById('cam-quality');
  if(b) document.getElementById('cam-brightness-val').textContent = parseFloat(b.value).toFixed(2);
  if(c) document.getElementById('cam-contrast-val').textContent   = parseFloat(c.value).toFixed(2);
  if(s) document.getElementById('cam-saturation-val').textContent = parseFloat(s.value).toFixed(2);
  if(q) document.getElementById('cam-quality-val').textContent    = parseInt(q.value);
  clearTimeout(_camDebounce);
  _camDebounce = setTimeout(_postCamSettings, 150);
}

function _postCamSettings(){
  $.ajax({
    url: _camBase + '/settings',
    method: 'POST',
    contentType: 'application/json',
    data: JSON.stringify({
      brightness:   parseFloat(document.getElementById('cam-brightness').value),
      contrast:     parseFloat(document.getElementById('cam-contrast').value),
      saturation:   parseFloat(document.getElementById('cam-saturation').value),
      jpeg_quality: parseInt(document.getElementById('cam-quality').value)
    }),
    success: function(){ _setCamStatus('online'); },
    error:   function(){ _setCamStatus('offline'); }
  });
}

function _fetchCamStatus(){
  $.ajax({
    url: _camBase + '/settings',
    method: 'GET',
    timeout: 2000,
    success: function(data){
      _applyCamSettings(data);
      _setCamStatus(data.camera_status || 'online');
      var fpsEl = document.getElementById('cam-fps-val');
      if(fpsEl) fpsEl.textContent = (data.fps !== undefined) ? data.fps.toFixed(1) + ' fps' : '--';
    },
    error: function(){
      _setCamStatus('offline');
      var fpsEl = document.getElementById('cam-fps-val');
      if(fpsEl) fpsEl.textContent = '--';
    }
  });
}

function _startCamPoll(){
  _stopCamPoll();
  _fetchCamStatus();
  _camPollTimer = setInterval(_fetchCamStatus, 1500);
}

function _stopCamPoll(){
  clearInterval(_camPollTimer);
  _camPollTimer = null;
}

function loadCameraSettings(){
  _startCamPoll();
  _updateCamReactorInfo();
}

function _checkCamOrientation(){
  var camPanel = document.getElementById('nexus-camera');
  var hint = document.getElementById('cam-rotate-hint');
  if(!hint || !camPanel) return;
  var camVisible = camPanel.style.display === 'block';
  if(!camVisible){ hint.classList.remove('active'); return; }
  var isMobile = window.innerWidth <= 768;
  var isPortrait = window.innerHeight > window.innerWidth;
  hint.classList.toggle('active', isMobile && isPortrait);
}

window.addEventListener('orientationchange', function(){
  setTimeout(_checkCamOrientation, 150);
});

function _applyCamSettings(data){
  function set(id, valId, val, fixed){
    var el = document.getElementById(id);
    var vEl = document.getElementById(valId);
    if(el) el.value = val;
    if(vEl) vEl.textContent = fixed ? parseFloat(val).toFixed(2) : parseInt(val);
  }
  set('cam-brightness', 'cam-brightness-val', data.brightness,   true);
  set('cam-contrast',   'cam-contrast-val',   data.contrast,     true);
  set('cam-saturation', 'cam-saturation-val', data.saturation,   true);
  set('cam-quality',    'cam-quality-val',    data.jpeg_quality, false);
}

function _setCamStatus(status){
  var dot   = document.getElementById('cam-status-dot');
  var badge = document.getElementById('cam-offline-badge');
  if(dot)   dot.className = 'cam-dot ' + status;
  if(badge) badge.style.display = (status === 'offline') ? 'flex' : 'none';
}

function _updateCamReactorInfo(){
  var reactorEl = document.getElementById('cam-reactor-val');
  var badgeEl   = document.getElementById('cam-exp-badge');
  if(!reactorEl || !badgeEl) return;
  if(!_lastData){ reactorEl.textContent = '--'; badgeEl.textContent = '--'; return; }
  reactorEl.textContent = _lastData.UIDevice || '--';
  var running = _lastData.Experiment && _lastData.Experiment.ON;
  badgeEl.textContent = running ? 'Corriendo' : 'Detenido';
  badgeEl.className   = 'cam-exp-badge ' + (running ? 'running' : 'stopped');
}

function captureCamFrame(btn){
  if(btn) btn.disabled = true;
  var xhr = new XMLHttpRequest();
  xhr.open('GET', _camBase + '/capture', true);
  xhr.responseType = 'blob';
  xhr.onload = function(){
    if(xhr.status === 200){
      var url = URL.createObjectURL(xhr.response);
      var a = document.createElement('a');
      var ts = new Date().toISOString().slice(0,19).replace(/[T:]/g,'-');
      a.href = url;
      a.download = 'chibio_' + ts + '.jpg';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
    if(btn) btn.disabled = false;
  };
  xhr.onerror = function(){ if(btn) btn.disabled = false; };
  xhr.send();
}

function resetCameraSettings(){
  _applyCamSettings({ brightness:1.0, contrast:1.0, saturation:1.0, jpeg_quality:80 });
  _postCamSettings();
}

var MAIN_TOUR_STEPS = [
  { sel:'#topbar',
    title:'Bienvenido a Chi.Bio Nexus',
    desc:'Esta es tu barra de control principal. Desde aquí puedes iniciar y detener experimentos, elegir el reactor que deseas monitorear y consultar el estado del sistema en todo momento.',
    pos:'bottom-right' },
  { sel:'#nexus-tab-bar',
    title:'Las tres vistas del sistema',
    desc:'Main te muestra el monitoreo y control en tiempo real. Architect es el editor visual donde diseñas tus protocolos. Cámara te conecta al streaming en vivo del biorreactor.',
    pos:'bottom' },
  { sel:'#exp-pill',
    title:'Estado del experimento',
    desc:'Este botón te indica si hay un experimento en curso. Cuando parpadea en verde, el protocolo está activo. En rojo, el sistema está en espera. También muestra la hora de inicio y el ciclo actual.',
    pos:'bottom' },
  { sel:'.dev-row',
    title:'Selector de reactor',
    desc:'Aquí eliges cuál módulo Chi.Bio (M0–M7) quieres controlar. Solo aparecen disponibles los reactores que el sistema ha detectado correctamente en la red.',
    pos:'bottom' },
  { sel:'#main-scan-btn',
    title:'Buscar reactores',
    desc:'Si acabas de conectar un módulo nuevo o algún reactor no aparece en la fila, este botón inicia un escaneo para encontrarlo y añadirlo a la lista de dispositivos disponibles.',
    pos:'bottom' },
  { sel:'#cyc',
    title:'Contador de ciclos',
    desc:'Indica cuántos ciclos de medición se han completado desde el inicio del experimento. Cada ciclo representa una ronda completa de lecturas: densidad óptica, temperatura y fluorescencia.',
    pos:'bottom' },
  { sel:'#main-action-btns',
    title:'Control del experimento',
    desc:'Iniciar activa el protocolo FSM cargado. Detener lo pausa sin perder los datos registrados. Reset devuelve todos los parámetros al estado inicial — ideal para preparar un experimento nuevo desde cero.',
    pos:'bottom' },
  { sel:'#global-buttons',
    title:'Tema visual y tour',
    desc:'El botón de luna alterna entre el modo oscuro y el claro. Tu preferencia se guarda automáticamente entre sesiones. El botón amarillo relanza este tour cuando quieras.',
    pos:'bottom' },
  { sel:'#cloud-pill',
    title:'Estado del protocolo',
    desc:'Indica el estado del protocolo activo en el sistema. Azul girando significa que se está cargando un nuevo protocolo. Verde confirma que fue inyectado con éxito y el reactor ya lo está ejecutando.',
    pos:'bottom' },
  { sel:'.card.c-gr',
    title:'Densidad Óptica (OD)',
    desc:'El indicador principal del crecimiento celular. El valor grande en verde es el OD medido en tiempo real. Desde aquí también puedes fijar el objetivo y activar el turbidostato o el modo Zigzag.',
    pos:'right' },
  { sel:'.card.c-cy',
    title:'Calibración del sensor óptico',
    desc:'Antes de cada experimento te recomendamos calibrar el sensor con medio de cultivo limpio. Ingresa el valor Raw medido y el OD real obtenido con un espectrofotómetro de referencia.',
    pos:'right' },
  { sel:'.card.c-rd',
    title:'Temperatura',
    desc:'El sistema cuenta con tres sensores independientes: temperatura exterior del cultivo (EXT), interior del chip (INT) y temperatura IR del líquido. Puedes definir un objetivo y activar el termostato desde aquí.',
    pos:'right' },
  { sel:'.card.c-am',
    title:'Agitación magnética',
    desc:'Controla la velocidad del agitador magnético. El orbe animado te da una referencia visual de la intensidad actual. La agitación se suspende automáticamente durante las mediciones de OD para proteger la lectura.',
    pos:'right' },
  { sel:'#charts4',
    title:'Gráficas en tiempo real',
    desc:'Cuatro gráficas simultáneas que registran la evolución del experimento: densidad óptica, tasa de crecimiento μ, temperatura y actividad de las bombas. Puedes activar o desactivar cada una según lo que necesites ver.',
    pos:'left' },
  { sel:'#chart-toggles-bar',
    title:'Selección de gráficas',
    desc:'Usa estos botones para mostrar u ocultar cada gráfica individualmente. Si necesitas analizar una variable con más detalle, puedes dejar solo esa activa y el resto se ocultará para darte más espacio.',
    pos:'bottom' },
  { sel:'#cbox-temp .cbox-t',
    title:'Series de temperatura',
    desc:'Dentro de la gráfica de temperatura puedes elegir qué series mostrar: T. Cultivo (IR), Objetivo, T. Interior y T. Exterior. Cada serie tiene su propio color para facilitar la lectura.',
    pos:'bottom' },
  { sel:'.card.c-pu',
    title:'Programa Custom / FSM',
    desc:'Desde aquí ejecutas los protocolos diseñados en el Architect. El número grande muestra el estado actual de la máquina de estados. Selecciona el slot (C1–C8) y presiona Run para activarlo.',
    pos:'left' },
  { sel:'#cpane-fp',
    title:'Proteínas fluorescentes',
    desc:'Panel de configuración y lectura de los tres canales de fluorescencia (FP1, FP2, FP3). Cada canal tiene su propia longitud de onda de excitación, banda base y bandas de emisión configurables.',
    pos:'left' },
  { sel:'.col-r',
    title:'Panel de actuadores',
    desc:'Control manual de todos los actuadores del reactor: los 9 LEDs y el láser de medición, las 4 bombas peristálticas y el espectrómetro AS7341 de 8 canales para análisis de color.',
    pos:'left' },
  { sel:'.btn-csv',
    title:'Exportar datos',
    desc:'Descarga un archivo CSV con todos los registros del experimento: OD, temperatura, bombas y fluorescencia. No necesitas acceder al BeagleBone por SSH — el archivo incluye el nombre del reactor y la fecha.',
    pos:'bottom' },
];


var _mainTourStep = 0;
var _mainTourActive = false;

function startMainTour(){
  localStorage.setItem('chibio_main_tour_done','1');
  _mainTourStep = 0;
  _mainTourActive = true;
  document.getElementById('main-tour-overlay').classList.add('active');
  _renderMainTourStep();
}

function _renderMainTourStep(){
  if(!_mainTourActive) return;
  var step = MAIN_TOUR_STEPS[_mainTourStep];
  if(!step){ endMainTour(); return; }

  document.getElementById('main-tour-title').textContent = step.title;
  document.getElementById('main-tour-desc').textContent  = step.desc;

  var isLast  = _mainTourStep === MAIN_TOUR_STEPS.length - 1;
  var isFirst = _mainTourStep === 0;
  document.getElementById('main-tour-btn-next').textContent = isLast ? '¡Listo! 🎉' : 'Siguiente →';
  document.getElementById('main-tour-btn-prev').style.visibility = isFirst ? 'hidden' : 'visible';
  document.getElementById('main-tour-count').textContent = (_mainTourStep+1) + ' / ' + MAIN_TOUR_STEPS.length;

  var el   = step.sel ? document.querySelector(step.sel) : null;
  var hl   = document.getElementById('main-tour-highlight');
  var box  = document.getElementById('main-tour-box');
  var rect = null;

  if(el){
    rect = el.getBoundingClientRect();
    if(rect.width > 0 && rect.height > 0){
      var PAD = 7;
      hl.style.display = 'block';
      hl.style.left    = (rect.left   - PAD) + 'px';
      hl.style.top     = (rect.top    - PAD) + 'px';
      hl.style.width   = (rect.width  + PAD*2) + 'px';
      hl.style.height  = (rect.height + PAD*2) + 'px';
    } else {
      hl.style.display = 'none'; rect = null;
    }
  } else {
    hl.style.display = 'none';
  }
  _posMainTourBox(box, rect, step.pos || 'right');
}

function _posMainTourBox(box, rect, pos){
  var BW=330, BH=230, M=16;
  var VW=window.innerWidth, VH=window.innerHeight;
  var l, t;
  if(!rect){ l=(VW-BW)/2; t=(VH-BH)/2; }
  else{
    switch(pos){
      case 'right':        l=rect.right+M;   t=rect.top;       break;
      case 'left':         l=rect.left-BW-M; t=rect.top;       break;
      case 'top':          l=rect.left;       t=rect.top-BH-M;  break;
      case 'bottom':       l=rect.left;       t=rect.bottom+M;  break;
      case 'bottom-right': l=rect.left;       t=rect.bottom+M;  break;
      default:             l=rect.right+M;   t=rect.top;
    }
  }
  l = Math.max(10, Math.min(l, VW-BW-10));
  t = Math.max(10, Math.min(t, VH-BH-10));
  box.style.left = l+'px';
  box.style.top  = t+'px';
}

function mainTourNext(){
  if(_mainTourStep >= MAIN_TOUR_STEPS.length-1){ endMainTour(); return; }
  _mainTourStep++; _renderMainTourStep();
}
function mainTourPrev(){
  if(_mainTourStep <= 0) return;
  _mainTourStep--; _renderMainTourStep();
}
function mainTourSkip(){ endMainTour(); }
function endMainTour(){
  _mainTourActive = false;
  document.getElementById('main-tour-overlay').classList.remove('active');
  document.getElementById('main-tour-highlight').style.display = 'none';
}

// Auto-lanzar el tour la primera vez
if(!localStorage.getItem('chibio_main_tour_done')){ setTimeout(startMainTour, 1200); }

