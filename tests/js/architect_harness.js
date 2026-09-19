// Extrae funciones de static/js/architect.js y las ejecuta en Node, sin DOM.
// Uso:  node architect_harness.js compile  < [{name, ast}]   → {name: código Python}
//       node architect_harness.js sanitize < [nodos]        → nodos saneados (_sanitizeImportedAST)
//       node architect_harness.js pumps    < {Pump1: ...}   → caudales saneados (_sanitizeImportedPumps)
// CHIBIO_ARCHITECT_PATH apunta a una copia parcheada de architect.js.
const fs = require('fs');
const path = require('path');

const file = process.env.CHIBIO_ARCHITECT_PATH ||
    path.join(__dirname, '..', '..', 'static', 'js', 'architect.js');
const src = fs.readFileSync(file, 'utf8');

// Función de nivel superior: termina en la primera línea que empieza por "}".
function grab(name, kind) {
    const m = src.match(new RegExp('^' + kind + ' ' + name + '\\b[\\s\\S]*?^(?:}|\\];?|};?)', 'm'));
    return m ? m[0] : null;
}

const mode = process.argv[2];
const input = JSON.parse(fs.readFileSync(0, 'utf8'));

if (mode === 'compile') {
    const fn = new Function(grab('compileFSM', 'function') + '; return compileFSM;')();
    const out = {};
    for (const c of input) {
        try { out[c.name] = { code: fn(c.ast, 'M0', 'C8') }; }
        catch (e) { out[c.name] = { error: String(e) }; }
    }
    console.log(JSON.stringify(out));
} else if (mode === 'sanitize' || mode === 'pumps') {
    const fnName = mode === 'sanitize' ? '_sanitizeImportedAST' : '_sanitizeImportedPumps';
    const body = grab(fnName, 'function');
    if (!body) { console.log(JSON.stringify({ missing: fnName })); process.exit(0); }
    const meta = grab('META', 'const');
    const fn = new Function(meta + ';' + body + '; return ' + fnName + ';')();
    console.log(JSON.stringify(fn(input)));
} else {
    console.error('modo desconocido: ' + mode);
    process.exit(2);
}
