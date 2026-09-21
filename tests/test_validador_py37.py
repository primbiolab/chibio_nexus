"""
El validador AST del protocolo inyectado (`_validate_protocol_ast`) debe dar el MISMO veredicto y el
mismo mensaje en Python 3.7 (BeagleBone) que en el Python del PC.

Motivo: en 3.7 `ast.parse` no genera `ast.Constant` sino `Num`/`Str`/`NameConstant` (3.8+ unifica).
Con un validador que solo conoce `Constant`, la BBB rechazaba TODO protocolo con literales
("Construcción no permitida: Str"), y los tests en el PC (3.14) no lo veían.

El mismo script (región del validador + corpus) se ejecuta en un subproceso local y, si la variable
CHIBIO_BBB está definida (p. ej. CHIBIO_BBB=root@192.168.7.2, SSH por llave), también en la BBB.
Solo lee y ejecuta en memoria (`python3 -` por stdin): no escribe archivos ni importa la app.

    CHIBIO_BBB=root@192.168.7.2 python -m pytest tests/test_validador_py37.py -v
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BBB = os.environ.get('CHIBIO_BBB')

# (id, líneas del cuerpo del estado C1, ¿debe aceptarse?)
CASES = [
    ('literales_texto_y_numero', ["SetOutputOn(M, 'Heat', 1)", 'time.sleep(1)'], True),
    ('numeros_bool_none', ['x = 1', 'y = -2.5', 'z = True', 'w = None'], True),
    ('aritmetica_con_sysdata', ["x = sysData[M]['OD']['current'] * 2.5 - 1"], True),
    ('indices_y_slices', ["x = sysData[M]['OD']['record'][0]", "y = sysData[M]['OD']['record'][0:2]",
                          "z = sysData[M]['OD']['record'][-1]"], True),
    ('fstring', ["addTerminal(M, f'Ciclo {1 + 1}')"], True),
    ('if_else', ['if 1 > 0:', '    pass', 'else:', '    pass'], True),
    ('llamada_get', ["x = sysData[M]['Custom'].get('param1')"], True),
    ('atributo_dunder', ['x = ().__class__'], False),
    ('import', ['import os'], False),
    ('exec', ["exec('1')"], False),
    ('open', ["open('x')"], False),
    ('lambda', ['lambda: 1'], False),
    ('cadena_con_dunder', ["y = '__class__'"], False),
    ('repeticion_de_texto', ["x = 'ab' * 3"], False),
    ('repeticion_de_lista', ['x = [0] * 10'], False),
    ('potencia', ['x = 9 ** 9'], False),
    ('llama_alias_de_format', ["f = '{0}'.format", 'y = f(SetOutputOn)'], False),
    ('reasigna_nombre_protegido', ['str = abs'], False),
    ('asigna_atributo', ['math.log10 = abs'], False),
]


def _region(path, start='def _fsm_dedent(code):', end=None):
    src = open(os.path.join(ROOT, path), encoding='utf-8').read()
    a = src.index(start)
    b = src.index(end, a)
    return src[a:b]


REGIONS = {
    'app.py': _region('app.py', end='# ── Sleep acotado'),
    'mock_server.py': _region('mock_server.py', end='# ── Rutas Flask'),
}


def _script(region):
    cases = json.dumps([(name, '\n'.join(['    elif (program == "C1"):'] + ['        ' + b for b in body]))
                        for name, body, _ in CASES])
    return ('# -*- coding: utf-8 -*-\nimport ast, sys, json\n' + region + '\n'
            'for _name, _code in json.loads(%r):\n'
            '    try:\n'
            '        _validate_protocol_ast(ast.parse(_fsm_dedent(_code)))\n'
            '        print(json.dumps([_name, None]))\n'
            '    except SyntaxError:\n'
            '        print(json.dumps([_name, "SyntaxError"]))\n'
            '    except ValueError as _e:\n'
            '        print(json.dumps([_name, str(_e)]))\n' % cases)


def _run(cmd, script, timeout=60):
    r = subprocess.run(cmd, input=script.encode('utf-8'), capture_output=True, timeout=timeout)
    assert r.returncode == 0, r.stderr.decode('utf-8', 'replace')
    lines = [l for l in r.stdout.decode('utf-8').splitlines() if l.startswith('[')]
    return {n: m for n, m in map(json.loads, lines)}


def _local(region):
    return _run([sys.executable, '-'], _script(region))


def _bbb(region):
    return _run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', BBB, 'python3', '-'], _script(region))


@pytest.mark.parametrize('fichero', sorted(REGIONS))
def test_veredictos_esperados_en_python_local(fichero):
    veredictos = _local(REGIONS[fichero])
    for name, _, aceptar in CASES:
        assert (veredictos[name] is None) == aceptar, (fichero, name, veredictos[name])


def test_app_y_mock_dan_los_mismos_mensajes():
    assert _local(REGIONS['app.py']) == _local(REGIONS['mock_server.py'])


@pytest.mark.skipif(not BBB, reason='define CHIBIO_BBB=root@192.168.7.2 (SSH por llave) para probar en Python 3.7')
def test_validador_de_app_igual_en_la_bbb():
    en_bbb = _bbb(REGIONS['app.py'])
    en_pc = _local(REGIONS['app.py'])
    assert en_bbb == en_pc


@pytest.mark.skipif(not BBB, reason='define CHIBIO_BBB=root@192.168.7.2 (SSH por llave) para probar en Python 3.7')
def test_app_py_compila_en_el_python_de_la_bbb():
    src = open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read().replace('\r\n', '\n')
    # el script viaja por stdin; el código a compilar va como literal
    script = ('# -*- coding: utf-8 -*-\nSRC = %r\ncompile(SRC, "app.py", "exec")\nprint("[\\"compila\\", null]")\n' % src)
    assert _run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', BBB, 'python3', '-'], script) == {'compila': None}
