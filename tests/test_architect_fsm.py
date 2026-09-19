"""
Architect → servidor: la salida REAL de `compileFSM` (static/js/architect.js, ejecutada con Node)
pasa por `_fsm_dedent` + `_validate_protocol_ast` + `_nexus_exec` de app.py (hardware simulado).

Criterio de éxito de cada caso: el protocolo es aceptado, `Custom.Status` avanza ciclo a ciclo
hasta 99.0 ("Protocolo Finalizado"), sin errores y sin dosificar de más.

Los tests `xfail(strict=True)` documentan bugs abiertos (docs/historial/auditoria_2026-09-18.md, Fase A).
Para comprobar un parche de architect.js sin tocar los marcadores:
    CHIBIO_ARCHITECT_PATH=<copia parcheada> python -m pytest tests/test_architect_fsm.py --runxfail
Requiere Node en el PATH (si no, se omiten).
"""
import copy
import itertools
import json
import os
import shutil
import subprocess
import types

import pytest

from test_app_real import appmod  # noqa: F401  (fixture de sesión: app.py real con hardware simulado)

HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'js', 'architect_harness.js')
NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='Node no está en el PATH')

M = 'M0'
_ids = itertools.count(1)

_DEFAULTS = {   # espejo de mkNode() en architect.js
    'init_temp': dict(temp=37.0), 'init_od': dict(od=0.3), 'init_stir': dict(speed=0.5),
    'thermostat': dict(temp=37.0), 'ramp_temp': dict(temp_start=37.0, temp_end=42.0, duration=60),
    'led': dict(led='LEDB', power=0.1, mode='on', duration=1, unit='min'),
    'uv': dict(power=0.5, mode='on', duration=1, unit='min'),
    'laser': dict(power=0.5, mode='on', duration=1, unit='min'),
    'pump': dict(pump='Pump1', duration=5.0), 'turbidostat': dict(state='on'),
    'chemostat': dict(state='on', p1=0.02, p2=0.1), 'zigzag': dict(state='on', zig=0.04),
    'measure_od': {}, 'wait': dict(unit='min', duration=1), 'loop': dict(count=10, children=[]),
    'trigger': dict(tvar='OD', op='>=', val=0.5, behavior='wait', children=[]),
    'log': dict(msg='Mensaje de control'),
}


def N(type_, **kw):
    node = {'id': 'n%d' % next(_ids), 'type': type_}
    node.update(copy.deepcopy(_DEFAULTS[type_]))
    node.update(kw)
    return node


def inits():
    return [N('init_temp'), N('init_od'), N('init_stir')]


def pump(p='Pump1', d=5.0):
    return N('pump', pump=p, duration=d)


def loop(count, *children):
    return N('loop', count=count, children=list(children))


def trig(behavior, *children):
    return N('trigger', behavior=behavior, children=list(children))


def wait_min(d=1):
    return N('wait', unit='min', duration=d)


BUG_LAST = 'continue de compileFSM salta el último nodo (architect.js:788): nunca escribe Status=exitState'
BUG_TRIG = 'trigger "esperar" repite en cada ciclo los bloques síncronos previos de su mismo estado'
BUG_EMPTY = 'trigger sin hijos (no último) apunta a un estado sin manejador → atascado'
BUG_NEST = 'modo de control anidado en bucle/trigger: compileFSM lo ignora y deja el estado sin manejador'
BUG_GEN = "motor de generaciones emite `'Generations' not in ...` (ast.NotIn): el servidor rechaza todo protocolo con generaciones"
BUG_LOG = 'log: la barra invertida no se escapa → SyntaxError o inyección de llamadas permitidas'


def case(name, nodes, doses=None, od=1.0, growth=0.0, bug=None, events=()):
    marks = [pytest.mark.xfail(strict=True, reason=bug)] if bug else []
    return pytest.param(name, nodes, doses or {}, od, growth, tuple(events), id=name, marks=marks)


CASES = [
    case('solo_inits', inits(), bug=BUG_LAST),
    case('inits_turbidostat', inits() + [N('turbidostat')], events=[('on', 'OD', 1)], bug=BUG_LAST),
    case('inits_chemostat', inits() + [N('chemostat')], bug=BUG_LAST),
    case('inits_zigzag', inits() + [N('zigzag')], events=[('on', 'Zigzag', 1)], bug=BUG_LAST),
    case('pump_solo', inits() + [pump()], {'Pump1': 1}),
    case('pump_y_modo_al_final', inits() + [pump(), N('turbidostat')], {'Pump1': 1}, bug=BUG_LAST),
    case('modo_y_luego_pump', inits() + [N('turbidostat'), pump()], {'Pump1': 1}),
    case('thermostat', inits() + [N('thermostat', temp=40.0)], events=[('on', 'Thermostat', 1)]),
    case('ramp_temp', inits() + [N('ramp_temp', duration=3)], events=[('on', 'Thermostat', 1)]),
    case('led_on', inits() + [N('led', mode='on')], events=[('on', 'LEDB', 1)]),
    case('led_off', inits() + [N('led', mode='off')], events=[('on', 'LEDB', 0)]),
    case('led_pulso_seg', inits() + [N('led', mode='pulse', unit='sec', duration=2)],
         events=[('on', 'LEDB', 1), ('on', 'LEDB', 0)]),
    case('led_pulso_min', inits() + [N('led', mode='pulse', unit='min', duration=2)],
         events=[('on', 'LEDB', 1), ('on', 'LEDB', 0)]),
    case('uv_pulso_min', inits() + [N('uv', mode='pulse', unit='min', duration=1, power=0.3)],
         events=[('on', 'UV', 1), ('on', 'UV', 0)]),
    case('laser_on', inits() + [N('laser', mode='on', power=0.2)], events=[('on', 'LASER650', 1)]),
    case('measure_od', inits() + [N('measure_od')], events=[('measure', 'OD', None)]),
    case('wait_seg', inits() + [N('wait', unit='sec', duration=2), pump()], {'Pump1': 1}),
    case('wait_min', inits() + [wait_min(3), pump()], {'Pump1': 1}),
    case('wait_gen', inits() + [N('wait', unit='gen', duration=1), pump()], {'Pump1': 1}, growth=50.0,
         bug=BUG_GEN),
    case('trigger_generaciones',
         inits() + [N('trigger', behavior='if', tvar='Generations', op='>=', val=0.0, children=[pump()])],
         {'Pump1': 1}, bug=BUG_GEN),
    case('log_simple', inits() + [N('log', msg='hola')]),
    case('log_comilla', inits() + [N('log', msg="it's")]),
    case('log_barra_invertida', inits() + [N('log', msg='ruta\\')], bug=BUG_LOG),
    case('bucle_x3', inits() + [loop(3, pump())], {'Pump1': 3}),
    case('bucle_con_espera', inits() + [loop(2, pump(), wait_min(1))], {'Pump1': 2}),
    case('bucle_en_bucle', inits() + [loop(2, loop(2, pump()))], {'Pump1': 4}),
    case('sincrono_antes_de_bucle', inits() + [pump('Pump1'), loop(2, pump('Pump2'))],
         {'Pump1': 1, 'Pump2': 2}),
    case('bucle_hijos_terminan_en_modo', inits() + [loop(2, pump(), N('turbidostat'))],
         {'Pump1': 2}, bug=BUG_LAST),
    case('trigger_esperar_cumplido', inits() + [trig('wait', pump())], {'Pump1': 1}, od=1.0),
    case('trigger_if_cumplido', inits() + [trig('if', pump())], {'Pump1': 1}, od=1.0),
    case('trigger_if_no_cumplido', inits() + [trig('if', pump())], {'Pump1': 0}, od=0.1),
    case('trigger_ultimo_sin_hijos', inits() + [pump(), trig('if')], {'Pump1': 1}),
    case('trigger_sin_hijos_no_ultimo', inits() + [trig('if'), pump()], {'Pump1': 1}, bug=BUG_EMPTY),
    case('trigger_en_bucle', inits() + [loop(2, trig('if', pump()))], {'Pump1': 2}),
    case('trigger_anidado', inits() + [trig('if', trig('if', pump()))], {'Pump1': 1}),
    case('trigger_espera_no_redosifica_previo',
         inits() + [pump('Pump1'), trig('wait', pump('Pump2'))], {'Pump1': 1, 'Pump2': 1},
         od=lambda c: 0.1 if c < 8 else 1.0, bug=BUG_TRIG),
    case('modo_anidado_en_bucle', inits() + [loop(1, N('turbidostat'))],
         events=[('on', 'OD', 1)], bug=BUG_NEST),
    case('mezcla_completa',
         inits() + [N('turbidostat'), N('thermostat', temp=38.0), wait_min(1), pump('Pump1'),
                    N('ramp_temp', duration=2), loop(2, pump('Pump2'), wait_min(1)),
                    trig('if', N('measure_od')), N('led', mode='pulse', unit='sec', duration=1),
                    N('log', msg='fin')],
         {'Pump1': 1, 'Pump2': 2}),
]


@pytest.fixture(scope='module')
def compiled():
    """Compila todo el corpus con la compileFSM real en una sola llamada a Node."""
    payload = [{'name': p.values[0], 'ast': p.values[1]} for p in CASES]
    res = subprocess.run([NODE, HARNESS, 'compile'], input=json.dumps(payload), capture_output=True,
                         text=True, encoding='utf-8', timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


@pytest.fixture
def fsm(appmod, monkeypatch):
    """run(code, ...) ejecuta el protocolo ciclo a ciclo con _nexus_exec real y grabadores de hardware."""
    sd = appmod.sysData[M]
    saved = copy.deepcopy(sd)
    events, terms = [], []
    monkeypatch.setattr(appmod, '_MAX_PROTOCOL_SLEEP', 0.0)
    monkeypatch.setattr(appmod, 'SetOutputOn', lambda M_, item, force: events.append(('on', item, force)))
    monkeypatch.setattr(appmod, 'SetOutputTarget', lambda M_, item, v: events.append(('target', item, v)))
    monkeypatch.setattr(appmod, 'MeasureOD', lambda M_: events.append(('measure', 'OD', None)))
    monkeypatch.setattr(appmod, 'addTerminal', lambda M_, s: terms.append(str(s)))

    def run(code, od=1.0, growth=0.0, max_cycles=400):
        del events[:], terms[:]
        sd['Custom'].update(Status=0.0, ON=1, Program='C8', param1=0.0, param2=0.0, param3=0.0)
        sd['Custom'].pop('Generations', None)
        sd['GrowthRate']['current'] = growth
        appmod._cloud.update(status='idle', error_msg='')
        cycles = 0
        for cycles in range(1, max_cycles + 1):
            sd['Experiment']['cycles'] = cycles
            sd['OD']['current'] = od(cycles) if callable(od) else od
            appmod._nexus_exec(M, code, 'C8')
            if appmod._cloud['status'] == 'error' or sd['Custom']['Status'] == 99.0:
                break
        return types.SimpleNamespace(
            status=sd['Custom']['Status'], cycles=cycles, events=list(events), terms=list(terms),
            error=appmod._cloud['error_msg'] if appmod._cloud['status'] == 'error' else None,
            doses=lambda p: events.count(('on', p, 1)))

    yield run
    for k, v in saved.items():
        sd[k] = v
    appmod._cloud.update(status='idle', error_msg='')


@pytest.mark.parametrize('name,nodes,doses,od,growth,events', CASES)
def test_compilefsm_ejecuta_y_termina(fsm, compiled, name, nodes, doses, od, growth, events):
    out = compiled[name]
    assert 'code' in out, out
    res = fsm(out['code'], od=od, growth=growth)
    assert res.error is None, res.error
    assert res.status == 99.0, 'atascado en Status=%s tras %d ciclos' % (res.status, res.cycles)
    assert any('Protocolo Finalizado' in t for t in res.terms)
    for p, n in doses.items():
        assert res.doses(p) == n, '%s dosificó %d veces (esperado %d)' % (p, res.doses(p), n)
    for ev in events:
        assert ev in res.events, '%s ausente en %s' % (ev, res.events)


def test_inits_se_aplican_en_el_primer_ciclo(fsm, compiled, appmod):
    """Singleton Lock: init_temp/init_od/init_stir (primeros 3) quedan en el estado 0."""
    res = fsm(compiled['solo_inits']['code'], max_cycles=1)
    sd = appmod.sysData[M]
    assert sd['Thermostat']['target'] == 37.0
    assert sd['OD']['target'] == 0.3
    assert sd['Stir']['target'] == 0.5
    assert ('on', 'Thermostat', 1) in res.events and ('on', 'Stir', 1) in res.events


@pytest.mark.xfail(strict=True, reason=BUG_LOG)
def test_log_no_inyecta_llamadas_permitidas(fsm):
    """Un msg con \\'); llamada #  cierra la cadena y ejecuta SetOutputOn (pasa la allowlist)."""
    msg = "\\'); SetOutputOn(M, \"Heat\", 1) #"
    nodes = inits() + [N('log', msg=msg)]
    payload = json.dumps([{'name': 'x', 'ast': nodes}])
    r = subprocess.run([NODE, HARNESS, 'compile'], input=payload, capture_output=True, text=True,
                       encoding='utf-8', timeout=60)
    code = json.loads(r.stdout)['x']['code']
    res = fsm(code)
    assert ('on', 'Heat', 1) not in res.events


# ── Import de .chibio / Gemini: nunca debe llegar HTML sin sanear a innerHTML ─────────────────

def _harness(mode, data):
    r = subprocess.run([NODE, HARNESS, mode], input=json.dumps(data), capture_output=True, text=True,
                       encoding='utf-8', timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


XSS = '<img src=x onerror=alert(1)>'


@pytest.mark.xfail(strict=True, reason='import .chibio/Gemini: node.type sin validar llega a innerHTML (architect.js:374,433)')
def test_import_descarta_tipos_desconocidos_y_sanea_campos():
    out = _harness('sanitize', [
        {'id': 'a', 'type': XSS},
        {'id': 'b', 'type': 'pump', 'pump': XSS, 'duration': '<b>7</b>'},
        {'id': 'c', 'type': 'loop', 'count': 2, 'children': [{'id': 'd', 'type': '__proto__'},
                                                            {'id': 'e', 'type': 'wait', 'unit': XSS, 'duration': 1}]},
        {'id': 'f', 'type': 'trigger', 'tvar': XSS, 'op': XSS, 'behavior': XSS, 'val': 'x'},
    ])
    assert isinstance(out, list), out
    flat = json.dumps(out)
    assert '<' not in flat and 'onerror' not in flat
    assert [n['type'] for n in out] == ['pump', 'loop', 'trigger']
    assert out[0]['pump'] == 'Pump1' and out[0]['duration'] == 0
    assert [c['type'] for c in out[1]['children']] == ['wait']
    assert out[1]['children'][0]['unit'] == 'min'
    assert out[2]['children'] == [] and out[2]['op'] == '>=' and out[2]['behavior'] == 'wait'


@pytest.mark.xfail(strict=True, reason='import .chibio: pumps sin validar llega a innerHTML (architect.js:525)')
def test_import_caudales_solo_numeros():
    out = _harness('pumps', {'Pump1': XSS, 'Pump2': '2.5', 'Pump3': -1, 'Pump4': None, 'Evil': 1})
    assert out == {'Pump1': 1.0, 'Pump2': 2.5, 'Pump3': 1.0, 'Pump4': 1.0}


@pytest.mark.xfail(strict=True, reason='los dos caminos de import (archivo y postMessage) y la IA deben usar el saneador')
def test_los_tres_caminos_de_entrada_usan_el_saneador():
    src = open(os.path.join(os.path.dirname(HARNESS), '..', '..', 'static', 'js', 'architect.js'),
               encoding='utf-8').read()
    assert src.count('= _sanitizeImportedAST(data.ast)') == 2    # importExperiment + importData
    assert src.count('= _sanitizeImportedAST(generatedNodes)') == 1  # Gemini
    assert src.count('_sanitizeImportedPumps(data.pumps)') == 2
