"""
Suite de pruebas contra mock_server (simulador local, corre nativo en Windows).

Cubre las defensas que se endurecieron en los hotfixes v1.0.0 y que el mock
comparte con app.py:

  - HF-03  CSRF: gate por header X-Requested-With en toda mutación.
  - HF-01  RCE: /injectProtocol/ pasa por el validador AST (allowlist) antes
           de tocar disco; los payloads de escape deben rechazarse.
  - Contrato básico de los endpoints GET y de control.

El mock es HOY el origen del túnel Cloudflare, así que estas pruebas validan
superficie realmente expuesta. No requiere BeagleBone.

Ejecutar:  python -m pytest tests/test_mock_server.py -v
"""
import os
import json
import pytest

import mock_server

# Header que exige el gate CSRF (block_csrf) para cualquier POST/PUT/PATCH/DELETE.
XRW = {'X-Requested-With': 'XMLHttpRequest'}

# Ruta del archivo que injectProtocol escribe en éxito — se limpia entre pruebas.
_PROTO_MOCK = os.path.join(mock_server.BASE_DIR, 'protocolo_mock.py')


@pytest.fixture
def client():
    mock_server.app.config['TESTING'] = True
    with mock_server.app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_proto():
    """Borra protocolo_mock.py antes y después para que no queden artefactos."""
    for _ in (0, 1):
        if os.path.exists(_PROTO_MOCK):
            os.remove(_PROTO_MOCK)
        yield
        break


# ─────────────────────────────────────────────────────────────
# HF-03 — CSRF gate
# ─────────────────────────────────────────────────────────────

def test_post_sin_header_csrf_rechazado(client):
    r = client.post('/changeDevice/M1')          # sin X-Requested-With
    assert r.status_code == 403
    assert 'CSRF' in r.get_json()['error']


def test_inject_sin_header_csrf_rechazado(client):
    r = client.post('/injectProtocol/', json={'code': 'x'})   # sin header
    assert r.status_code == 403


def test_get_no_requiere_header_csrf(client):
    r = client.get('/getSysdata/')               # GET no pasa por el gate
    assert r.status_code == 200


@pytest.mark.parametrize('verb', ['put', 'patch', 'delete'])
def test_csrf_gate_cubre_verbos_mutantes(client, verb):
    # El gate corre en before_request (antes del routing) → 403 sin header,
    # sin importar si la ruta soporta el verbo.
    r = getattr(client, verb)('/injectProtocol/')
    assert r.status_code == 403
    assert 'CSRF' in r.get_json()['error']


# ─────────────────────────────────────────────────────────────
# Contrato básico — GET
# ─────────────────────────────────────────────────────────────

def test_index_ok(client):
    r = client.get('/')
    assert r.status_code == 200


def test_getsysdata_json_estructura(client):
    r = client.get('/getSysdata/')
    assert r.status_code == 200
    data = r.get_json()
    # _build_sysdata devuelve los campos del device activo directamente
    assert 'DeviceID' in data and 'Custom' in data


def test_cloudstatus_llaves(client):
    r = client.get('/getCloudStatus/')
    assert r.status_code == 200
    data = r.get_json()
    for k in ('status', 'error_msg', 'inject_count'):
        assert k in data


# ─────────────────────────────────────────────────────────────
# HF-01 — /injectProtocol/ acepta FSM legítimo
# ─────────────────────────────────────────────────────────────
#
# El compilador (architect.js) emite la rama `elif` con 4 espacios de
# indentación y el cuerpo con 8. _fsm_dedent quita 4 espacios de cada línea,
# dejando `if (program...):` en col 0 y el cuerpo a 4 → código válido.
# Reproducimos esa forma exacta para que el AST se PARSEE y sea el validador
# (no un error de sintaxis) quien decida.

def fsm(*body_lines):
    lines = ['    elif (program == "C1"):']
    lines += ['        ' + bl for bl in body_lines]
    return '\n'.join(lines)

FSM_VALIDO = fsm("SetOutputOn(M, 'Heat', 1)", 'addTerminal(M, "prueba")')
FSM_VALIDO_SLEEP = fsm('time.sleep(1)', 'MeasureOD(M)')


@pytest.mark.parametrize('code', [FSM_VALIDO, FSM_VALIDO_SLEEP])
def test_inject_fsm_valido_aceptado(client, code):
    r = client.post('/injectProtocol/', json={'code': code}, headers=XRW)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['ok'] is True


def test_inject_codigo_vacio_400(client):
    r = client.post('/injectProtocol/', json={'code': '   '}, headers=XRW)
    assert r.status_code == 400


def test_inject_sintaxis_invalida_400(client):
    r = client.post('/injectProtocol/', json={'code': fsm('x x x')}, headers=XRW)
    assert r.status_code == 400
    assert 'Sintaxis' in r.get_json()['error']


# ─────────────────────────────────────────────────────────────
# HF-01 — RCE cerrado: los payloads de escape deben rechazarse con 400
# Cada payload PARSEA (indentación correcta) → lo debe cortar el validador AST,
# no un error de sintaxis. Por eso exigimos el mensaje 'Protocolo no permitido'.
# ─────────────────────────────────────────────────────────────

RCE_PAYLOADS = {
    'globals_escape':  fsm('SetOutputOn.__globals__["os"].system("id")'),
    'dunder_import':   fsm('__import__("os").system("id")'),
    'eval':            fsm('eval("1+1")'),
    'exec':            fsm('exec("x=1")'),
    'open_file':       fsm('open("/etc/passwd")'),
    'import_stmt':     fsm('import os'),
    'attr_call_os':    fsm('os.system("id")'),
    'getattr':         fsm('getattr(SetOutputOn, "x")'),
    'class_escape':    fsm('SetOutputOn.__class__'),
    'lambda':          fsm('f = lambda: 1'),
    'list_comp':       fsm('x = [i for i in range(3)]'),
    'walrus':          fsm('(y := 5)'),
    'fstring_dunder':  fsm('addTerminal(M, f"{SetOutputOn.__globals__}")'),
    'subscript_dunder':fsm('SetOutputOn.__dict__["x"]'),
    'while_loop':      fsm('while True:\n            pass'),
}


@pytest.mark.parametrize('name,code', list(RCE_PAYLOADS.items()), ids=list(RCE_PAYLOADS.keys()))
def test_inject_rce_rechazado(client, name, code):
    r = client.post('/injectProtocol/', json={'code': code}, headers=XRW)
    assert r.status_code == 400, f'{name} NO fue rechazado: {r.get_json()}'
    # Debe cortarlo el validador AST (no un error de sintaxis accidental)
    assert 'Protocolo no permitido' in r.get_json()['error'], \
        f'{name} rechazado por razón equivocada: {r.get_json()}'
    # y no debe haber escrito el protocolo a disco
    assert not os.path.exists(_PROTO_MOCK), f'{name} escribió protocolo_mock.py pese al 400'


# ─────────────────────────────────────────────────────────────
# Endpoints de control — camino feliz + validación de dispositivo
# ─────────────────────────────────────────────────────────────

def test_changedevice_valido_204(client):
    r = client.post('/changeDevice/M1', headers=XRW)
    assert r.status_code == 204


def test_changedevice_invalido_400(client):
    r = client.post('/changeDevice/ZZ', headers=XRW)
    assert r.status_code == 400


def test_setoutputon_204(client):
    r = client.post('/SetOutputOn/Heat/1/0', headers=XRW)
    assert r.status_code == 204


def test_setcustom_204(client):
    r = client.post('/SetCustom/C1/0', headers=XRW)
    assert r.status_code == 204


def test_experiment_toggle_204(client):
    assert client.post('/Experiment/1/0', headers=XRW).status_code == 204
    assert client.post('/Experiment/0/0', headers=XRW).status_code == 204
