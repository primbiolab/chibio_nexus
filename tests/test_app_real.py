"""
Pruebas contra app.py REAL (no el mock) con hardware simulado.

Carga app.py con stubs de Adafruit_GPIO / Adafruit_BBIO / smbus2 / config, sin
BeagleBone. Los tests de hardware sustituyen I2CCom y setPWM por grabadores, así
que se ejecuta el código real de PumpModulation, SetOutput, validadores, etc.

Un test marcado `xfail(strict=True)` documenta una brecha abierta conocida (hoy solo
el DoS de memoria vía variables en /injectProtocol/; ver docs/pendientes.md). Al
corregirla su test pasa a XPASS y, por ser strict, falla: quita entonces el marcador.
Para comprobar un parche sin tocar los marcadores:  python -m pytest tests/test_app_real.py --runxfail

Variable CHIBIO_APP_PATH: apunta a una copia parcheada de app.py (por defecto app.py).

Ejecutar:  python -m pytest tests/test_app_real.py -v
"""
import importlib.util
import os
import random
import sys
import threading
import time
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PATH = os.environ.get('CHIBIO_APP_PATH') or os.path.join(ROOT, 'app.py')

XRW = {'X-Requested-With': 'XMLHttpRequest'}
BUG = 'auditoría 2026-09-18'


class HardExit(Exception):
    """Sustituye a os._exit: lo registra y aborta el hilo que lo llamó."""


class _FakeMux:
    def __init__(self):
        self.v = 0

    def write8(self, reg, val):
        self.v = val

    def readRaw8(self):
        return self.v


def _module(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    return m


@pytest.fixture(scope='session')
def appmod():
    """app.py real importado con hardware simulado (todos los reactores ausentes)."""
    exits = []

    def fake_exit(code=0):
        exits.append(code)
        raise HardExit(code)

    def get_i2c_device(addr, busnum=1):
        if addr == 0x74:
            return _FakeMux()
        raise OSError('sin hardware')

    class _SMBus:
        def __init__(self, *a, **k):
            raise OSError('sin hardware')

    gpio = _module('Adafruit_BBIO.GPIO', OUT=0, IN=1, HIGH=1, LOW=0,
                   setup=lambda *a, **k: None, output=lambda *a, **k: None,
                   input=lambda *a, **k: 0)
    stubs = {
        'Adafruit_GPIO': _module('Adafruit_GPIO'),
        'Adafruit_GPIO.I2C': _module('Adafruit_GPIO.I2C', get_i2c_device=get_i2c_device),
        'Adafruit_BBIO': _module('Adafruit_BBIO'),
        'Adafruit_BBIO.GPIO': gpio,
        'smbus2': _module('smbus2', SMBus=_SMBus),
        'config': _module('config', GEMINI_API_KEY='clave-falsa-de-prueba'),
    }
    saved = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    orig_exit = os._exit
    os._exit = fake_exit
    try:
        spec = importlib.util.spec_from_file_location('chibio_app_under_test', APP_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)     # ~2 s: initialiseAll() espera al watchdog
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    mod.sysItems['Watchdog']['ON'] = 0   # detiene el hilo del watchdog simulado
    mod.EXIT_CALLS = exits
    yield mod
    os._exit = orig_exit


@pytest.fixture
def client(appmod):
    with appmod.application.test_client() as c:
        yield c


@pytest.fixture
def bench(appmod, monkeypatch):
    """Reactor M0 'presente' con setPWM/I2CCom grabados. bench.hw = último PWM por canal."""
    names = {}
    for item in ('Pump1', 'Pump2', 'Pump3', 'Pump4'):
        names[id(appmod.sysItems[item]['In1'])] = item + '.In1'
        names[id(appmod.sysItems[item]['In2'])] = item + '.In2'
    for item in ('Heat', 'UV', 'LEDC', 'LEDD', 'LEDF', 'LEDG', 'LEDH', 'Stir'):
        names[id(appmod.sysItems[item])] = item

    b = types.SimpleNamespace(hw={}, log=[], lock=threading.Lock())

    def fake_setPWM(M, device, channels, fraction, fails):
        time.sleep(0.005)            # ~latencia de las transacciones I2C
        with b.lock:
            name = names.get(id(channels), str(device))
            b.hw[name] = fraction
            b.log.append((name, fraction))

    monkeypatch.setattr(appmod, 'setPWM', fake_setPWM)
    monkeypatch.setattr(appmod, 'I2CCom', lambda *a, **k: 0)

    M = 'M0'
    appmod.EXIT_CALLS.clear()
    was_present = appmod.sysData[M]['present']
    appmod.sysData[M]['present'] = 1
    appmod.sysData[M]['Experiment']['ON'] = 0
    for p in ('Pump1', 'Pump2', 'Pump3', 'Pump4'):
        appmod.sysData[M][p].update(ON=0, target=0.0, direction=1.0)
        appmod.sysDevices[M][p]['active'] = 0
    yield b
    for p in ('Pump1', 'Pump2', 'Pump3', 'Pump4', 'Heat', 'UV', 'Stir'):
        appmod.sysData[M][p]['ON'] = 0
    time.sleep(0.35)                 # deja salir a los hilos PumpModulation (sondean cada 0.1 s)
    appmod.sysData[M]['present'] = was_present


def _post(client, url, **kw):
    return client.post(url, headers=XRW, **kw)


# ─────────────────────────────────────────────────────────────
# Superficie HTTP real (invariantes de CLAUDE.md)
# ─────────────────────────────────────────────────────────────

def test_post_sin_header_xrw_es_403(client):
    r = client.post('/SetOutputTarget/Heat/M0/0.5')
    assert r.status_code == 403


def test_movil_bloqueado_403(client):
    r = client.get('/getSysdata/', headers={'User-Agent': 'Mozilla/5.0 (iPhone) Mobile'})
    assert r.status_code == 403


def test_cabeceras_csp(client):
    csp = client.get('/getSysdata/').headers['Content-Security-Policy']
    assert "object-src 'none'" in csp and "frame-ancestors 'self'" in csp


@pytest.mark.parametrize('url', [
    '/SetOutputTarget/Evil/M0/1',
    '/SetOutputOn/Evil/1/M0',
    '/Direction/Heat/M0',
])
def test_item_fuera_de_allowlist_400(client, url):
    r = _post(client, url)
    assert r.status_code == 400 and 'error' in r.get_json()


@pytest.mark.parametrize('url', [
    '/SetOutputTarget/Heat/M9/0.5',
    '/SetOutputTarget/Heat/M0/abc',
    '/MeasureTemp/Otro/M0',
])
def test_parametros_invalidos_400(client, url):
    assert _post(client, url).status_code == 400


@pytest.mark.parametrize('sent,expected', [('5', 1.0), ('-3', 0.0)])
def test_setoutputtarget_clamp(client, appmod, sent, expected):
    r = _post(client, '/SetOutputTarget/Heat/M0/' + sent)
    assert r.status_code == 204
    assert appmod.sysData['M0']['Heat']['target'] == expected


@pytest.mark.parametrize('sent', ['inf', '-inf', '1e999'])
def test_infinitos_nunca_quedan_como_target(client, appmod, sent):
    """Hoy se recortan al límite; un parche puede rechazarlos con 400. Ambos son válidos."""
    r = _post(client, '/SetOutputTarget/Heat/M0/' + sent)
    assert r.status_code in (204, 400)
    assert 0.0 <= appmod.sysData['M0']['Heat']['target'] <= 1.0


def test_setoutputon_force_es_idempotente(client, appmod, bench):
    _post(client, '/SetOutputTarget/Heat/M0/0.4')
    _post(client, '/SetOutputOn/Heat/1/M0')
    _post(client, '/SetOutputOn/Heat/1/M0')
    assert appmod.sysData['M0']['Heat']['ON'] == 1
    assert bench.hw['Heat'] == pytest.approx(0.4)
    _post(client, '/SetOutputOn/Heat/0/M0')
    assert bench.hw['Heat'] == 0.0


@pytest.mark.parametrize('item', ['Heat', 'Thermostat', 'Pump1'])
def test_nan_rechazado(client, appmod, item):
    r = _post(client, f'/SetOutputTarget/{item}/M0/nan')
    assert r.status_code == 400
    v = appmod.sysData['M0'][item]['target']
    assert v == v   # nunca NaN


def test_force_no_numerico_400_json(client):
    r = _post(client, '/SetOutputOn/Heat/x/M0')
    assert r.status_code == 400 and 'error' in r.get_json()


def test_medir_en_reactor_ausente_no_mata_el_proceso(client, appmod):
    # Usa el I2CCom REAL (sin bench): con present==0 llama a os._exit(4).
    appmod.sysData['M7']['present'] = 0
    appmod.EXIT_CALLS.clear()
    _post(client, '/MeasureTemp/Internal/M7')
    assert appmod.EXIT_CALLS == []


def test_csvdata_libera_lock_si_falla_el_disco(appmod, monkeypatch):
    M = 'M0'
    d = appmod.sysData[M]
    for key in ('time', 'OD', 'Thermostat', 'ThermometerInternal', 'ThermometerExternal',
                'ThermometerIR', 'Light', 'Pump1', 'Pump2', 'Pump3', 'Pump4'):
        d[key]['record'] = [0.0]
    d['OD']['targetrecord'] = [0.0]

    def open_falla(*a, **k):
        raise OSError('disco lleno')

    monkeypatch.setattr(appmod, 'open', open_falla, raising=False)
    try:
        with pytest.raises(OSError):
            appmod.csvData(M)
        bloqueado = appmod.lock.locked()
    finally:
        if appmod.lock.locked():
            appmod.lock.release()    # no dejar el lock tomado para el resto de la suite
    assert not bloqueado


# ─────────────────────────────────────────────────────────────
# /injectProtocol/ contra el validador AST REAL de app.py
# ─────────────────────────────────────────────────────────────

def fsm(*body):
    return '\n'.join(['    elif (program == "C1"):'] + ['        ' + b for b in body])


@pytest.fixture
def proto_en_tmp(appmod, monkeypatch, tmp_path):
    """injectProtocol escribe junto a app.py: lo desviamos a un directorio temporal."""
    monkeypatch.setattr(appmod, '__file__', str(tmp_path / 'app.py'))
    return tmp_path


def test_inject_valido_aceptado(client, proto_en_tmp):
    r = _post(client, '/injectProtocol/', json={'code': fsm("SetOutputOn(M, 'Heat', 1)", 'time.sleep(1)')})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    assert (proto_en_tmp / 'protocolo.py').exists()


@pytest.mark.parametrize('body', [
    ["x = ().__class__"],
    ["import os"],
    ["exec('1')"],
    ["eval('1')"],
    ["open('x')"],
    ["getattr(sysData, 'x')"],
    ["y = [c for c in ().__class__.__mro__]"],
    ["lambda: 1"],
])
def test_inject_ataques_clasicos_400(client, proto_en_tmp, body):
    r = _post(client, '/injectProtocol/', json={'code': fsm(*body)})
    assert r.status_code == 400, r.get_json()
    assert not (proto_en_tmp / 'protocolo.py').exists()


def test_inject_alias_de_str_format_rechazado(client, proto_en_tmp):
    body = ["f = '{0.__globals__}'.format", 'str = f', 'y = str(SetOutputOn)', 'addTerminal(M, y)']
    r = _post(client, '/injectProtocol/', json={'code': fsm(*body)})
    assert r.status_code == 400


@pytest.mark.parametrize('expr', ['x = 9**9**9**9', 'x = [0] * 10**9'])
def test_inject_dos_por_constantes_rechazado(client, proto_en_tmp, expr):
    r = _post(client, '/injectProtocol/', json={'code': fsm(expr)})
    assert r.status_code == 400


CORPUS_PARIDAD = [
    fsm("SetOutputOn(M, 'Heat', 1)"), fsm('time.sleep(1)', 'MeasureOD(M)'),
    fsm('x = ().__class__'), fsm('import os'), fsm("exec('1')"), fsm('open("x")'),
    fsm("getattr(sysData, 'x')"), fsm('lambda: 1'), fsm('x = 9**9'),
    fsm("f = '{0}'.format", 'str = f'),
]


def test_validador_ast_identico_a_mock_server(appmod):
    """El validador está duplicado en mock_server: que no diverjan (ver auditoría)."""
    import ast
    import mock_server

    def veredicto(fn, code):
        try:
            fn(ast.parse(appmod._fsm_dedent(code)))
            return True
        except ValueError:
            return False

    for code in CORPUS_PARIDAD:
        assert veredicto(appmod._validate_protocol_ast, code) == \
               veredicto(mock_server._validate_protocol_ast, code), code


# ─────────────────────────────────────────────────────────────
# Bombas: PumpModulation / SetOutputTarget reales
# ─────────────────────────────────────────────────────────────

def _arranca_bomba(client, target, pump='Pump1'):
    _post(client, f'/SetOutputTarget/{pump}/M0/{target}')
    _post(client, f'/SetOutputOn/{pump}/1/M0')
    time.sleep(0.25)


def test_bomba_manual_mapeo_zona_muerta(client, bench):
    """Caracterización: manual mapea [0,1] -> [PUMP_DZ=0.6, 1.0] (constante GLOBAL)."""
    _arranca_bomba(client, 0.5)
    assert bench.hw['Pump1.In1'] == pytest.approx(0.6 + 0.5 * 0.4)
    assert bench.hw['Pump1.In2'] == 0.0


def test_bomba_manual_sentido_inverso_usa_in2(client, bench):
    _arranca_bomba(client, -0.5)
    assert bench.hw['Pump1.In1'] == 0.0
    assert bench.hw['Pump1.In2'] == pytest.approx(0.8)


def test_bomba_manual_target_cero_no_gira(client, bench):
    """Documenta el comportamiento actual (el comentario de app.py:1005 dice lo contrario)."""
    _arranca_bomba(client, 0)
    assert bench.hw['Pump1.In1'] == 0.0 and bench.hw['Pump1.In2'] == 0.0


def test_bomba_off_apaga_ambos_canales(client, bench):
    _arranca_bomba(client, 0.7)
    _post(client, '/SetOutputOn/Pump1/0/M0')
    time.sleep(0.4)
    assert bench.hw['Pump1.In1'] == 0.0 and bench.hw['Pump1.In2'] == 0.0


def test_cambiar_potencia_en_caliente_no_detiene_la_bomba(client, appmod, bench):
    rng = random.Random(7)
    paradas = []
    for trial in range(6):
        _arranca_bomba(client, 0.5)
        ultimo = 0.5
        for _ in range(5):
            ultimo = rng.choice([v for v in (0.1, 0.3, 0.5, 0.7, 0.9) if v != ultimo])
            _post(client, f'/SetOutputTarget/Pump1/M0/{ultimo}')
        time.sleep(0.6)
        esperado = 0.6 + ultimo * 0.4
        ok = (appmod.sysData['M0']['Pump1']['ON'] == 1
              and bench.hw['Pump1.In1'] == pytest.approx(esperado)
              and bench.hw['Pump1.In2'] == 0.0)
        if not ok:
            paradas.append((trial, ultimo, bench.hw['Pump1.In1'], bench.hw['Pump1.In2']))
        _post(client, '/SetOutputOn/Pump1/0/M0')
        time.sleep(0.4)
    assert paradas == []


# ─────────────────────────────────────────────────────────────
# Reactor ausente (code-review ultra #1): _needs_present
# ─────────────────────────────────────────────────────────────

def test_stop_con_reactor_ausente_baja_banderas_sin_tocar_i2c(client, appmod):
    """Si present pasa a 0 en caliente, Stop debe poder parar el experimento (no 409) y sin I2C."""
    M = 'M7'
    appmod.sysData[M]['present'] = 0
    appmod.sysData[M]['Experiment']['ON'] = 1
    appmod.sysData[M]['OD']['ON'] = 1
    appmod.EXIT_CALLS.clear()
    try:
        r = _post(client, '/Experiment/0/M7')
        time.sleep(0.3)              # deja correr cualquier hilo lanzado por SetOutputOn
        assert r.status_code == 204
        assert appmod.sysData[M]['Experiment']['ON'] == 0
        assert appmod.sysData[M]['OD']['ON'] == 0
        assert appmod.EXIT_CALLS == []
    finally:
        appmod.sysData[M]['Experiment']['ON'] = 0
        appmod.sysData[M]['OD']['ON'] = 0


def test_start_con_reactor_ausente_409(client, appmod):
    appmod.sysData['M7']['present'] = 0
    appmod.EXIT_CALLS.clear()
    r = _post(client, '/Experiment/1/M7')
    assert r.status_code == 409
    assert appmod.sysData['M7']['Experiment']['ON'] == 0
    assert appmod.EXIT_CALLS == []


@pytest.mark.parametrize('call', [
    lambda a: a.MeasureOD('M7'),
    lambda a: a.MeasureTemp('M7', 'Internal'),
    lambda a: a.GetSpectrum('M7', 'x1'),
])
def test_medir_ausente_desde_hilo_conserva_el_fallo_seguro(appmod, call):
    """Fuera de una petición HTTP (Thermostat, runExperiment, CustomProgram) el 409 no existe:
    _needs_present no debe lanzar RuntimeError (mataba el hilo en silencio, con el calefactor
    en su último PWM) sino dejar actuar a I2CCom, que es el fallo seguro (os._exit)."""
    appmod.sysData['M7']['present'] = 0
    appmod.EXIT_CALLS.clear()
    errores = []

    def run():
        try:
            call(appmod)
        except BaseException as e:   # HardExit = os._exit simulado
            errores.append(e)

    t = threading.Thread(target=run)
    t.start()
    t.join(5)
    assert not any(isinstance(e, RuntimeError) for e in errores), errores
    assert 4 in appmod.EXIT_CALLS   # el HardExit simulado a veces lo absorbe un except de app.py; os._exit real no


# ─────────────────────────────────────────────────────────────
# Brecha conocida: DoS de memoria vía variables (code-review ultra #1, hallazgo 3)
# ─────────────────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason='Mult/Add sobre nombres o sysData[...] no se acota con un validador '
                   'estático (la ramp del Architect usa "*" con nombres); requiere sandbox de ejecución '
                   '(subproceso + rlimit). Ver docs/pendientes.md')
def test_inject_dos_por_variable_rechazado(client, proto_en_tmp):
    r = _post(client, '/injectProtocol/', json={'code': fsm('a = [0]', 'a = a * 1000000000')})
    assert r.status_code == 400
