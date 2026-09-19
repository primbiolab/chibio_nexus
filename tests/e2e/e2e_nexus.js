// E2E MANUAL del panel Nexus con Chrome real por CDP (sin dependencias; Node >=22).
// Requisitos: 'python mock_server.py' en 127.0.0.1:5000 (reiniciarlo tras editar templates/) y Chrome instalado.
// Uso: node tests/e2e/e2e_nexus.js   → imprime evidencia por flujo (S1..S12). No es parte de pytest.
// Artefactos del mock (no son bugs de la UI): no valida ni recorta valores; SetOutputOn siempre voltea; Experiment/1 fija Custom.ON.
const { launch, sleep } = require('./cdp.js');
const URL = 'http://127.0.0.1:5000/';
const XRW = "{method:'POST',headers:{'X-Requested-With':'XMLHttpRequest'}}";
const out = [];
const say = (...a) => { console.log(...a); };

(async () => {
  const { page: p, newPage, close } = await launch();
  const post = u => p.ev(`fetch('${u}',${XRW}).then(r=>r.status)`);
  const sys = () => p.ev(`fetch('/getSysdata/').then(r=>r.json())`);
  const reset = async () => { await p.goto(URL, 300); await post('/ExperimentReset'); await post('/changeDevice/M0'); await p.goto(URL, 2500); p.logs.length = 0; p.dialogs.length = 0; };
  const toasts = () => p.ev(`[...document.querySelectorAll('.toast-title')].map(e=>e.textContent)`);
  try {
    await p.send('Emulation.setDeviceMetricsOverride', { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false, screenWidth: 1920, screenHeight: 1080 });
    await reset();
    say('[S0] carga inicial: consola=', JSON.stringify(p.logs), 'ruta=', await p.ev('location.pathname'));

    // S1 doble clic Iniciar
    await reset(); let m = p.mark();
    await p.ev(`(()=>{const b=document.getElementById('ExperimentStart'); b.click(); b.click();})()`);
    await sleep(2500);
    let s = await sys();
    say('[S1] doble clic Iniciar → Experiment.ON=', s.Experiment.ON, ' Custom.ON=', s.Custom.ON, ' dialogos=', JSON.stringify(p.dialogs));
    say('     ' + p.fmt(p.since(m)));
    await reset(); m = p.mark();
    await p.ev(`document.getElementById('ExperimentStart').click()`); await sleep(2500);
    s = await sys(); say('[S1b] un clic Iniciar → Experiment.ON=', s.Experiment.ON, ' Custom.ON=', s.Custom.ON, ' dialogos=', JSON.stringify(p.dialogs));
    say('     ' + p.fmt(p.since(m)));

    // S2 Detener con servidor caído (offline)
    await sleep(2500); // deja que el sondeo fije _customOn
    await p.send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    m = p.mark(); await p.ev(`document.getElementById('ExperimentStop').click()`); await sleep(1500);
    say('[S2] Detener OFFLINE → toasts=', JSON.stringify(await toasts()));
    say('     ' + p.fmt(p.since(m)));
    await p.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    s = await sys(); say('     servidor sigue con Experiment.ON=', s.Experiment.ON);

    // S3 estado global UIDevice entre dos pestañas
    await reset();
    const b = await newPage(URL); await sleep(2500);
    await p.ev(`changeDevice('M1')`); await sleep(3000);
    const bDev = await b.ev(`fetch('/getSysdata/').then(r=>r.json()).then(d=>d.DeviceID)`);
    await b.ev(`fetch('/SetOutputTarget/Stir/0/0.77',${XRW}).then(r=>r.status)`);
    const st1 = (await sys()).Stir.target; await post('/changeDevice/M0'); const st0 = (await sys()).Stir.target;
    say('[S3] pestaña A cambia a M1; pestaña B (sin tocar) ve DeviceID=', bDev, '; B fija Stir=0.77 "/0" → Stir M1=', st1, ' Stir M0=', st0);
    b.ws.close();

    // S4 Reset y consola
    await reset(); m = p.mark(); await p.ev(`document.getElementById('ExperimentReset').click()`); await sleep(3500);
    say('[S4] Reset → consola=', JSON.stringify(p.logs), 'toasts=', JSON.stringify(await toasts()));

    // S5 ráfaga de bombas (oninput sin debounce)
    await reset(); m = p.mark();
    await p.ev(`(()=>{const i=document.getElementById('Pump1Input'); for(let k=1;k<=10;k++){i.value=(k/10).toFixed(1); i.dispatchEvent(new Event('input',{bubbles:true}));}})()`);
    await sleep(1500);
    say('[S5] 10 eventos input en Pump1Input → POSTs:', p.since(m, /SetOutputTarget/).length);

    // S6 LED/UV/láser sin confirmar
    await reset(); m = p.mark();
    await p.ev(`(()=>{for(const id of ['UV-tog','LASER650-tog']){const c=document.getElementById(id); c.checked=true; c.dispatchEvent(new Event('change',{bubbles:true}));}})()`);
    await sleep(1200);
    say('[S6] UV y láser ON con un clic (diálogo aceptado) → dialogos=', JSON.stringify(p.dialogs));
    say('     ' + p.fmt(p.since(m)));
    await reset(); p.dialogAccept = false; m = p.mark();
    await p.ev(`(()=>{const c=document.getElementById('UV-tog'); c.checked=true; c.dispatchEvent(new Event('change',{bubbles:true}));})()`); await sleep(1000);
    say('[S6b] UV con diálogo CANCELADO → peticiones=', p.since(m, /SetOutputOn/).length, ' checkbox queda=', await p.ev(`document.getElementById('UV-tog').checked`));
    p.dialogAccept = true;

    // S7 termostato fuera de rango / vacío
    await reset();
    for (const v of ['999', '-5', '', 'abc']) {
      m = p.mark(); await p.ev(`document.getElementById('ThermostatInput').value='${v}'; setThermostat();`); await sleep(700);
      say(`[S7] Termostato "${v}" →`, p.fmt(p.since(m)) || '(sin petición)', ' toasts=', JSON.stringify(await toasts()));
    }

    // S8 calibrar OD con campos vacíos
    await reset(); m = p.mark();
    await p.ev(`document.getElementById('OD0Set').click()`); await sleep(1000);
    say('[S8] Calibrar OD vacío →', p.fmt(p.since(m)), ' toasts=', JSON.stringify(await toasts()), ' dialogos=', JSON.stringify(p.dialogs));
    m = p.mark(); await p.ev(`document.getElementById('ODInput').value=''; setOD();`); await sleep(800);
    say('     Set OD vacío →', p.fmt(p.since(m)));

    // S9 selects FP tras recargar
    await reset();
    await p.ev(`$('#FPProtein1').val('GFP'); applyFPPreset(1); toggleFP('FP1');`); await sleep(1500);
    const before = await p.ev(`['FPProtein1','FPExcite1','FPBase1','FPEmit1A','FPEmit1B','FPGain1'].map(i=>i+'='+$('#'+i).val()).join(' ')`);
    const srv = (await sys()).FP1;
    await p.goto(URL, 3000);
    const after = await p.ev(`['FPProtein1','FPExcite1','FPBase1','FPEmit1A','FPEmit1B','FPGain1'].map(i=>i+'='+$('#'+i).val()).join(' ')`);
    say('[S9] FP1 antes de recargar:', before); say('     servidor FP1:', JSON.stringify({ ON: srv.ON, LED: srv.LED, BaseBand: srv.BaseBand, Emit1Band: srv.Emit1Band, Emit2Band: srv.Emit2Band, Gain: srv.Gain }));
    say('     tras recargar  :', after);

    await reset();
    await p.ev(`$('#FPProtein1').val('mCherry'); applyFPPreset(1);`);
    const pre = await p.ev(`'FPProtein1='+$('#FPProtein1').val()+' FPExcite1='+$('#FPExcite1').val()`);
    await p.ev(`changeDevice('M1')`); await sleep(3500);
    const post2 = await p.ev(`'FPProtein1='+$('#FPProtein1').val()+' FPExcite1='+$('#FPExcite1').val()`);
    say('[S9b] preset mCherry (excita LEDF) → cambiar a M1:', pre, ' → ', post2);

    // S10 pestaña Cámara sin servidor de cámara
    await reset(); m = p.mark();
    await p.ev(`switchNexusTab('camera')`); await sleep(12000);
    const camReqs = p.since(m); const failed = camReqs.filter(r => r.failed || r.status >= 400);
    say('[S10] Cámara sin servidor 12 s → peticiones=', camReqs.length, ' fallidas=', failed.length, ' consola=', JSON.stringify(p.logs.slice(0, 4)));
    say('     ' + p.fmt(camReqs.slice(0, 6)));

    await p.ev(`switchNexusTab('main')`); await sleep(500); m = p.mark(); await sleep(7000);
    say('[S10b] tras volver a Main, peticiones a cámara en 7 s =', p.since(m, /camera\./).length);

    // S11 Architect en iframe
    await reset(); await p.ev(`switchNexusTab('architect')`); await sleep(2500);
    const arch = await p.ev(`(()=>{const f=document.querySelector('iframe'); if(!f) return 'sin iframe'; archCmd('setVolume',5); return f.src+' '+(f.contentWindow&&f.contentDocument&&f.contentDocument.title)})()`);
    await sleep(500);
    const vol = await p.ev(`document.querySelector('iframe').contentWindow.eval('globalInitVol')`);
    say('[S11] Architect iframe:', arch, ' globalInitVol tras postMessage setVolume=', vol, ' consola=', JSON.stringify(p.logs.slice(0, 3)));

    // S12 mobile-blocked a 1920x1080 con escala 200%
    await p.send('Emulation.setDeviceMetricsOverride', { width: 960, height: 540, deviceScaleFactor: 2, mobile: false, screenWidth: 960, screenHeight: 540 });
    await p.goto(URL, 1500);
    say('[S12] 1920x1080 @200% (screen.width=960) → ruta=', await p.ev('location.pathname'), ' screen.width=', await p.ev('screen.width'), ' dpr=', await p.ev('devicePixelRatio'));
  } catch (e) { console.log('FALLO', e.stack); }
  close(); process.exit(0);
})();
