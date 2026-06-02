"""
mock_server.py — Servidor de desarrollo Chi.Bio Nexus
=====================================================
Simula 3 reactores (M0, M1, M2) con datos fluctuantes realistas.
No requiere BeagleBone, hardware, ni dependencias de Adafruit.

Uso:
    pip install flask
    python mock_server.py

Abre en el navegador: http://localhost:5000
"""

import os
import copy
import math
import random
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request

# ── Gemini (opcional — requiere config.py con GEMINI_API_KEY) ────
try:
    from config import GEMINI_API_KEY
    GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key=' + GEMINI_API_KEY
    _GEMINI_OK = True
except ImportError:
    _GEMINI_OK = False

def _gemini_request(prompt, system_prompt=None, use_json_mode=False):
    import urllib.request as _req
    import json as _json
    contents = []
    if system_prompt:
        contents.append({'role': 'user', 'parts': [{'text': '<<system>>\n' + system_prompt}]})
    contents.append({'role': 'user', 'parts': [{'text': prompt}]})
    gen_config = {'temperature': 0.1}
    if use_json_mode:
        gen_config['responseMimeType'] = 'application/json'
    body = _json.dumps({
        'contents': contents,
        'generationConfig': gen_config
    }).encode('utf-8')
    req = _req.Request(GEMINI_URL, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    with _req.urlopen(req, timeout=30) as resp:
        data = _json.loads(resp.read().decode('utf-8'))
    return data['candidates'][0]['content']['parts'][0]['text']

# ── Configuración ────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR   = os.path.join(BASE_DIR, 'static')

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# ── Estado del servidor mock ─────────────────────────────────────
_start_time = time.time()
_ui_device  = 'M0'

_cloud = {
    'status'       : 'idle',
    'error_msg'    : '',
    'inject_count' : 0,
}

# Parámetros independientes por reactor para que cada uno tenga
# su propia "personalidad" biológica en la simulación
_REACTOR_CFG = {
    'M0': {'od_base': 0.45, 'od_amp': 0.12, 'od_freq': 0.08,  'temp_base': 37.0, 'stir': 0.65, 'running': True,  'fsm': 2.0, 'pump1': 0.12},
    'M1': {'od_base': 0.31, 'od_amp': 0.08, 'od_freq': 0.11,  'temp_base': 34.5, 'stir': 0.50, 'running': True,  'fsm': 5.0, 'pump1': 0.08},
    'M2': {'od_base': 0.58, 'od_amp': 0.15, 'od_freq': 0.065, 'temp_base': 36.0, 'stir': 0.72, 'running': False, 'fsm': 0.0, 'pump1': 0.00},
}

# ── Generador de sysData simulado ────────────────────────────────
def _make_record(length: int, base: float, amp: float, freq: float, noise: float = 0.02) -> str:
    """Genera una serie temporal como string separado por comas."""
    vals = []
    for i in range(length):
        v = base + amp * math.sin(freq * i) + random.gauss(0, noise)
        vals.append(round(max(0.0, v), 4))
    return ','.join(str(v) for v in vals)

def _build_sysdata(device_id: str) -> dict:
    t    = time.time() - _start_time
    cfg  = _REACTOR_CFG.get(device_id, _REACTOR_CFG['M0'])
    n    = int(t / 5) + 40          # puntos en los records (crece con el tiempo)
    n    = min(n, 120)

    od_now   = cfg['od_base'] + cfg['od_amp'] * math.sin(cfg['od_freq'] * t) + random.gauss(0, 0.005)
    od_now   = max(0.0, od_now)
    temp_now = cfg['temp_base'] + 0.4 * math.sin(0.03 * t) + random.gauss(0, 0.05)
    running  = cfg['running']

    # Records de series temporales
    od_rec   = _make_record(n, cfg['od_base'], cfg['od_amp'],  cfg['od_freq'])
    mu_rec   = _make_record(n, 0.35,           0.10,           cfg['od_freq'] * 1.3, 0.015)
    t_ir_rec = _make_record(n, cfg['temp_base'],0.4,           0.03)
    t_tgt_rec= ','.join([str(cfg['temp_base'])] * n)
    t_int_rec= _make_record(n, cfg['temp_base'] - 0.5, 0.2,   0.025)
    t_ext_rec= _make_record(n, cfg['temp_base'] - 1.2, 0.3,   0.02)
    p1_rec   = _make_record(n, cfg['pump1'], 0.03, 0.05, 0.005) if running else ','.join(['0.0'] * n)
    time_rec = ','.join(str(round(i * 60, 1)) for i in range(n))

    present_devices = {f'M{i}': (1 if f'M{i}' in ['M0', 'M1', 'M2'] else 0) for i in range(8)}

    return {
        'UIDevice'       : device_id,
        'present'        : 1,
        'presentDevices' : present_devices,
        'Version'        : {'value': 'Turbidostat V3.0', 'LED': 1},
        'DeviceID'       : f'MOCK-{device_id}-ABCD',

        'time': {'record': time_rec},

        'Experiment': {
            'indicator'   : 'USR0',
            'startTime'   : datetime.now().strftime('%H:%M:%S') if running else 'Waiting',
            'startTimeRaw': _start_time if running else 0,
            'ON'          : 1 if running else 0,
            'cycles'      : int(t / 60) if running else 0,
            'cycleTime'   : 60.0,
            'threadCount' : 0,
        },

        'OD': {
            'current'      : round(od_now, 4),
            'target'       : 0.5,
            'default'      : 0.5,
            'max'          : 10,
            'min'          : 0,
            'record'       : od_rec,
            'targetrecord' : ','.join(['0.5'] * n),
            'Measuring'    : 0,
            'ON'           : 1 if running else 0,
            'Integral'     : 0.0,
            'Integral2'    : 0.0,
            'device'       : 'LASER650',
        },

        'OD0': {
            'target' : 1240.0,
            'raw'    : 1238.0 + random.gauss(0, 2),
            'max'    : 100000.0,
            'min'    : 0.0,
        },

        'GrowthRate': {
            'current': round(0.35 + 0.05 * math.sin(0.04 * t), 4),
            'record' : mu_rec,
            'default': 2.0,
        },

        'Thermostat': {
            'default'   : cfg['temp_base'],
            'target'    : cfg['temp_base'],
            'max'       : 50.0,
            'min'       : 0.0,
            'ON'        : 1 if running else 0,
            'record'    : t_tgt_rec,
            'cycleTime' : 30.0,
            'Integral'  : 0.0,
            'last'      : -1,
        },

        'ThermometerExternal': {'current': round(temp_now - 1.2, 3), 'record': t_ext_rec},
        'ThermometerInternal': {'current': round(temp_now - 0.5, 3), 'record': t_int_rec},
        'ThermometerIR'      : {'current': round(temp_now, 3),       'record': t_ir_rec},

        'Volume': {'target': 20.0, 'max': 50.0, 'min': 0.0, 'ON': 0},

        'Stir': {
            'target' : cfg['stir'] if running else 0.0,
            'default': cfg['stir'],
            'max'    : 1.0,
            'min'    : 0.0,
            'ON'     : 1 if running else 0,
        },

        'Pump1': {'target': round(cfg['pump1'], 4), 'default': 0.0, 'max': 1.0, 'min': -1.0, 'direction': 1.0, 'ON': 1 if (running and cfg['pump1'] > 0) else 0, 'record': p1_rec, 'thread': 0},
        'Pump2': {'target': 0.0, 'default': 0.0, 'max': 1.0, 'min': -1.0, 'direction': 1.0, 'ON': 0, 'record': ','.join(['0.0'] * n), 'thread': 0},
        'Pump3': {'target': 0.0, 'default': 0.0, 'max': 1.0, 'min': -1.0, 'direction': 1.0, 'ON': 0, 'record': ','.join(['0.0'] * n), 'thread': 0},
        'Pump4': {'target': 0.0, 'default': 0.0, 'max': 1.0, 'min': -1.0, 'direction': 1.0, 'ON': 0, 'record': ','.join(['0.0'] * n), 'thread': 0},

        'Light': {'target': 0.0, 'default': 0.5, 'max': 1.0, 'min': 0.0, 'ON': 0, 'Excite': 'LEDD', 'record': []},

        'Custom': {
            'Status' : cfg['fsm'],
            'default': 0.0,
            'Program': 'C8',
            'ON'     : 1 if running else 0,
            'param1' : 0, 'param2': 0, 'param3': 0.0,
            'record' : [],
        },

        'Heat'    : {'default': 0.0, 'target': 0.0, 'max': 1.0, 'min': 0.0, 'ON': 0, 'record': []},
        'Chemostat': {'ON': 0, 'p1': 0.0, 'p2': 0.1},
        'Zigzag'  : {'ON': 0, 'Zig': 0.04, 'target': 0.0, 'SwitchPoint': 0},

        # LEDs (todos apagados por defecto en mock)
        'LEDB'    : {'WL': '457',  'default': 0.1, 'target': 0.0, 'max': 1.0, 'min': 0.0, 'ON': 0},
        'LEDC'    : {'WL': '500',  'default': 0.1, 'target': 0.0, 'max': 1.0, 'min': 0.0, 'ON': 0},
        'LEDD'    : {'WL': '523',  'default': 0.1, 'target': 0.0, 'max': 1.0, 'min': 0.0, 'ON': 0},
        'LEDF'    : {'WL': '623',  'default': 0.1, 'target': 0.0, 'max': 1.0, 'min': 0.0, 'ON': 0},
        'LEDG'    : {'WL': '6500K','default': 0.1, 'target': 0.0, 'max': 1.0, 'min': 0.0, 'ON': 0},
        'LEDH'    : {'WL': '600',  'default': 0.1, 'target': 0.0, 'max': 1.0, 'min': 0.0, 'ON': 0},
        'LEDI'    : {'WL': '550',  'default': 0.1, 'target': 0.0, 'max': 1.0, 'min': 0.0, 'ON': 0},
        'LASER650': {'name': 'LASER650', 'default': 0.5, 'target': 0.0, 'max': 1.0, 'min': 0.0, 'ON': 0},
        'UV'      : {'WL': 'UV',   'default': 0.5, 'target': 0.0, 'max': 1.0, 'min': 0.0, 'ON': 0},

        'Terminal': {'text': [
            {'time': '12:04', 'msg': 'Cycle 3 Started'},
            {'time': '12:03', 'msg': 'Cycle 2 Complete'},
            {'time': '12:01', 'msg': '[MOCK] ' + device_id + ' activo'},
            {'time': '12:01', 'msg': 'Cycle 2 Started'},
            {'time': '12:00', 'msg': 'Cycle 1 Complete'},
            {'time': '11:59', 'msg': 'Cycle 1 Started'},
            {'time': '11:58', 'msg': 'Experiment Started'},
            {'time': '11:57', 'msg': 'System Initialised'},
        ]},

        'FP1': {'ON': 0, 'LED': 0, 'BaseBand': 0, 'Emit1Band': 0, 'Emit2Band': 0,
                'Base': random.uniform(0, 0.1), 'Emit1': random.uniform(0, 0.05), 'Emit2': 0.0,
                'BaseRecord': [], 'Emit1Record': [], 'Emit2Record': [], 'Gain': 0},
        'FP2': {'ON': 0, 'LED': 0, 'BaseBand': 0, 'Emit1Band': 0, 'Emit2Band': 0,
                'Base': 0.0, 'Emit1': 0.0, 'Emit2': 0.0,
                'BaseRecord': [], 'Emit1Record': [], 'Emit2Record': [], 'Gain': 0},
        'FP3': {'ON': 0, 'LED': 0, 'BaseBand': 0, 'Emit1Band': 0, 'Emit2Band': 0,
                'Base': 0.0, 'Emit1': 0.0, 'Emit2': 0.0,
                'BaseRecord': [], 'Emit1Record': [], 'Emit2Record': [], 'Gain': 0},

        'AS7341': {
            'spectrum': {
                'nm410': round(random.uniform(800, 1200)),
                'nm440': round(random.uniform(900, 1400)),
                'nm470': round(random.uniform(1100, 1600)),
                'nm510': round(random.uniform(1000, 1500)),
                'nm550': round(random.uniform(1200, 1800)),
                'nm583': round(random.uniform(950,  1400)),
                'nm620': round(random.uniform(700,  1100)),
                'nm670': round(random.uniform(600,  1000)),
                'CLEAR': round(random.uniform(5000, 8000)),
                'NIR'  : round(random.uniform(2000, 4000)),
                'DARK' : round(random.uniform(50, 200)),
                'ExtGPIO': 0, 'ExtINT': 0, 'FLICKER': 0,
            },
            'channels': {k: 0 for k in ['nm410','nm440','nm470','nm510','nm550','nm583','nm620','nm670','CLEAR','NIR','DARK','ExtGPIO','ExtINT','FLICKER']},
            'current': {f'ADC{i}': 0 for i in range(6)},
        },
    }


# ── Rutas Flask ──────────────────────────────────────────────────

@app.route('/mobile-blocked')
def mobile_blocked():
    return render_template('mobile_blocked.html'), 403

@app.route('/')
def index():
    data = _build_sysdata(_ui_device)
    return render_template('index.html', **data)

@app.route('/architect')
def architect():
    return render_template('architect.html')

@app.route('/getSysdata/')
def getSysdata():
    global _ui_device
    return jsonify(_build_sysdata(_ui_device))

@app.route('/getCloudStatus/')
def getCloudStatus():
    return jsonify({
        'status'       : _cloud['status'],
        'error_msg'    : _cloud['error_msg'],
        'inject_count' : _cloud['inject_count'],
    })

@app.route('/changeDevice/<M>', methods=['POST'])
def changeDevice(M):
    global _ui_device
    if M in ['M0', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7']:
        _ui_device = M
        print(f'[MOCK] Dispositivo cambiado a {M}')
    return ('', 204)

@app.route('/scanDevices/<which>', methods=['POST'])
def scanDevices(which):
    print(f'[MOCK] Escaneo solicitado: {which}')
    return ('', 204)

@app.route('/Experiment/<int:on>/<int:M>', methods=['POST'])
def experiment(on, M):
    global _REACTOR_CFG, _ui_device
    _REACTOR_CFG[_ui_device]['running'] = bool(on)
    print(f'[MOCK] Experimento {"INICIADO" if on else "DETENIDO"} en {_ui_device}')
    return ('', 204)

@app.route('/ExperimentReset', methods=['POST'])
def experimentReset():
    global _start_time, _REACTOR_CFG, _ui_device
    _start_time = time.time()
    _REACTOR_CFG[_ui_device]['running'] = False
    _REACTOR_CFG[_ui_device]['fsm']     = 0.0
    print(f'[MOCK] Experimento RESET en {_ui_device}')
    return ('', 204)

# Endpoints especializados — simulan cambio de estado visible en sysData
@app.route('/Direction/<pump>/<M>', methods=['POST'])
def direction(pump, M):
    global _REACTOR_CFG, _ui_device
    dev = M if M in _REACTOR_CFG else _ui_device
    if pump == 'Pump1' and dev in _REACTOR_CFG:
        _REACTOR_CFG[dev]['pump1'] *= -1
    print(f'[MOCK] Dirección {pump} invertida en {dev}')
    return ('', 204)

@app.route('/SetFPMeasurement/<fp>/<exc>/<base>/<em1>/<em2>/<gain>', methods=['POST'])
def setFPMeasurement(fp, exc, base, em1, em2, gain):
    print(f'[MOCK] FP config: {fp} exc={exc} base={base} em1={em1} em2={em2} gain={gain}')
    return ('', 204)

@app.route('/CalibrateOD/<param>/<M>/<raw>/<actual>', methods=['POST'])
def calibrateOD(param, M, raw, actual):
    print(f'[MOCK] CalibrateOD {param} raw={raw} actual={actual} en {M}')
    return ('', 204)

@app.route('/GetSpectrum/<gain>/<M>', methods=['POST'])
def getSpectrum(gain, M):
    print(f'[MOCK] GetSpectrum gain={gain} en {M}')
    return ('', 204)

@app.route('/MeasureFP/<M>', methods=['POST'])
def measureFP(M):
    print(f'[MOCK] MeasureFP en {M}')
    return ('', 204)

# Endpoints de control genérico — aceptan la petición y responden 204
_GENERIC_ENDPOINTS = [
    '/SetOutputTarget/<param>/<a>/<val>',
    '/SetOutputOn/<param>/<a>/<b>',
    '/MeasureOD/<M>',
    '/MeasureTemp/<sensor>/<M>',
    '/SetOutputTarget/Volume/<M>/<val>',
    '/ClearTerminal/<M>',
    '/SetCustom/<prog>/<state>',
    '/SetLightActuation/<led>',
]

def _generic_handler(**kwargs):
    print(f'[MOCK] {request.path}')
    return ('', 204)

for _path in _GENERIC_ENDPOINTS:
    app.add_url_rule(_path, endpoint=_path, view_func=_generic_handler, methods=['POST'])

# Endpoints de Nexus IA
@app.route('/analyzeProtocol/', methods=['POST'])
def analyzeProtocol():
    mock_code = (
        "# protocolo.py — MOCK\n"
        "def protocol(M, data):\n"
        "    if data['Custom']['Status'] == 0:\n"
        "        data['Thermostat']['target'] = 37.0\n"
        "        data['OD']['target'] = 0.5\n"
        "        data['Stir']['target'] = 0.6\n"
        "        data['Custom']['Status'] = 1\n"
        "    elif data['Custom']['Status'] == 1:\n"
        "        if data['OD']['current'] > 0.5:\n"
        "            data['Pump1']['target'] = 0.1\n"
        "            data['Pump1']['ON'] = 1\n"
        "        else:\n"
        "            data['Pump1']['ON'] = 0\n"
    )
    mock_analysis = (
        "El protocolo inicializa el biorreactor a 37°C, OD objetivo de 0.5 "
        "y agitación al 60%. Una vez iniciado, entra en modo turbidostato: "
        "cuando el OD supera 0.5, activa la bomba de entrada al 10% de "
        "potencia para diluir el cultivo. La bomba se apaga cuando el OD "
        "vuelve a estar por debajo del umbral."
    )
    return jsonify({'analysis': mock_analysis, 'code': mock_code})

@app.route('/generateProtocol/', methods=['POST'])
def generateProtocol():
    if not _GEMINI_OK:
        return jsonify({'error': 'config.py con GEMINI_API_KEY no encontrado. Crea el archivo con tu API key de Google.'}), 500
    try:
        prompt_text = request.get_json().get('prompt', '').strip()
        if not prompt_text:
            return jsonify({'error': 'No se recibió prompt'}), 400
        system_prompt = (
            'Eres un copiloto experto en automatización de biorreactores Chi.Bio.\n'
            'Traduce las instrucciones en lenguaje natural a un array de objetos JSON que representa el AST del protocolo.\n'
            'DEBES responder ÚNICAMENTE con un array JSON válido. Nada de texto extra, ni markdown.\n\n'
            'Bloques permitidos y rangos exactos:\n'
            '- "init_temp": {"type":"init_temp","temp":Float} — temp en [25.0, 50.0] °C. SIEMPRE primer bloque.\n'
            '- "init_od": {"type":"init_od","od":Float} — od en [0.01, 2.0]. SIEMPRE segundo bloque.\n'
            '- "init_stir": {"type":"init_stir","speed":Float} — speed en [0.0, 1.0] (0.5 es estándar). SIEMPRE tercer bloque.\n'
            '- "thermostat": {"type":"thermostat","temp":Float} — temp en [25.0, 50.0]\n'
            '- "ramp_temp": {"type":"ramp_temp","temp_start":Float,"temp_end":Float,"duration":Int} — duration en ciclos >= 1 (1 ciclo ≈ 1 min). NUNCA duration=0. Para "1 hora" usa duration=60, para "30 minutos" usa duration=30.\n'
            '- "led": {"type":"led","led":String,"power":Float,"mode":String,"duration":Float,"unit":String}\n'
            '  led DEBE ser uno de: "LEDB" (457nm azul), "LEDC" (500nm), "LEDD" (523nm verde), "LEDF" (623nm), "LEDG" (blanco 6500K), "LEDH" (600nm), "LEDI" (550nm). NUNCA "blue", "red", "green" u otros.\n'
            '  power en [0.0, 1.0] — 0.1=10%, 0.5=50%, 1.0=100%. Convierte siempre porcentajes: 20%→0.2, 50%→0.5. NUNCA valores > 1.0.\n'
            '  mode en ["pulse", "on", "off"]. Con tiempo SIEMPRE mode="pulse". unit en ["sec" (max 15s), "min"].\n'
            '- "uv": {"type":"uv","power":Float,"mode":String,"duration":Float,"unit":String} — mismos rangos que led.\n'
            '- "pump": {"type":"pump","pump":String,"duration":Float} — pump en ["Pump1","Pump2","Pump3","Pump4"] (NUNCA "1","2","3","4"). duration en segundos (max 20). Las bombas son on/off; el caudal se calibra aparte, NO uses "power".\n'
            '- "turbidostat": {"type":"turbidostat","state":"on"}\n'
            '- "chemostat": {"type":"chemostat","state":"on","p1":Float,"p2":Float} — p1 y p2 en [0.0, 1.0], p2 > p1.\n'
            '- "zigzag": {"type":"zigzag","state":"on","zig":Float} — zig en [0.01, 0.5]\n'
            '- "wait": {"type":"wait","duration":Float,"unit":String} — unit en ["sec" (max 15), "min", "gen"]\n'
            '- "loop": {"type":"loop","count":Int,"children":[...bloques...]} — children NUNCA vacío. count >= 2. Los bloques que se repiten van DENTRO de children, no fuera.\n'
            '  Ejemplo de loop correcto: {"type":"loop","count":5,"children":[{"type":"led","led":"LEDB","power":0.5,"mode":"pulse","duration":1,"unit":"min"},{"type":"wait","duration":2,"unit":"min"}]}\n'
            '- "trigger": {"type":"trigger","tvar":String,"op":String,"val":Float,"behavior":String,"children":[...bloques...]}\n'
            '  tvar DEBE ser exactamente uno de (respeta mayúsculas): "OD", "GrowthRate", "Temp", "FP1", "FP2", "FP3", "Generations". NUNCA "pH", "od" u otras variables no listadas.\n'
            '  op DEBE ser exactamente uno de: ">", "<", ">=", "<=", "==". NUNCA "gt", "lt", "ge", "le", "eq".\n'
            '  behavior en ["wait", "if"]. Las acciones condicionales van DENTRO de children.\n'
            '- "log": {"type":"log","msg":String}\n\n'
            'REGLAS:\n'
            '1. SIEMPRE incluir init_temp, init_od, init_stir como primeros 3 bloques. Son obligatorios.\n'
            '2. Solo UN modo de control (turbidostat, chemostat o zigzag). NUNCA dos a la vez.\n'
            '3. init_temp, init_od, init_stir solo pueden aparecer UNA vez cada uno.\n'
            '4. LEDs con tiempo: mode="pulse". NO uses mode="on" con tiempo.\n'
            '5. NO generes la propiedad "id".\n'
            '6. En "loop": children SIEMPRE contiene al menos un bloque. NUNCA "children":[]. NO pierdas bloques que el usuario describió dentro del loop.\n'
            '7. En "trigger": children SIEMPRE contiene los bloques de acción descritos. NO pierdas LEDs, pumps o logs que el usuario asocie al disparo.\n'
            '8. Convierte porcentajes a decimales: 20%→0.2, 50%→0.5, 60%→0.6, 100%→1.0.\n'
            '9. Agitación (speed) y potencias (power) siempre en [0.0, 1.0]. Nunca RPM ni valores absolutos.\n'
            '10. Preserva TODOS los pasos del usuario en orden. No omitas esperas, logs, ni acciones intermedias.\n'
            '11. En un trigger con behavior="wait": los children son acciones que se ejecutan cuando la condición YA se cumplió. NUNCA incluyas un bloque "wait" dentro de children de un trigger behavior="wait" — esa espera ya la gestiona el propio trigger.\n'
            '12. Antes de generar un "loop", cuenta explícitamente los bloques que el usuario describió dentro de él. children debe contener EXACTAMENTE esos bloques, en orden, sin omitir ninguno.\n'
            '13. Convierte horas a minutos para el campo duration: 1 hora=60 min, 2 horas=120 min, 0.5 horas=30 min. Usa siempre unit="min".\n'
            '14. init_temp, init_od, init_stir SOLO pueden aparecer UNA VEZ en todo el array. NUNCA los repitas ni los generes con valores distintos en otro punto del array.'
        )
        import json as _json
        text = _gemini_request(prompt_text, system_prompt, use_json_mode=True)
        text_clean = text.strip()
        if text_clean.startswith('```'):
            text_clean = text_clean.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
        parsed = _json.loads(text_clean)
        return jsonify({'ast': _json.dumps(parsed, ensure_ascii=False)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/injectProtocol/', methods=['POST'])
def injectProtocol():
    global _cloud
    data = request.get_json()
    code = (data or {}).get('code', '').strip()
    if not code:
        return jsonify({'error': 'No se recibió código'}), 400

    _cloud['status']        = 'ok'
    _cloud['inject_count'] += 1
    print(f'[MOCK] Protocolo inyectado (#{_cloud["inject_count"]}) — {len(code)} chars')

    # Guardar en disco para pruebas locales (opcional)
    proto_path = os.path.join(BASE_DIR, 'protocolo_mock.py')
    with open(proto_path, 'w') as f:
        f.write(code)

    return jsonify({'ok': True, 'path': proto_path})


# ── Entry point ──────────────────────────────────────────────────
if __name__ == '__main__':
    print('\n' + '='*55)
    print('  Chi.Bio Nexus — Servidor Mock de Desarrollo')
    print('='*55)
    print(f'  Reactores activos : M0, M1, M2')
    print(f'  Templates         : {TEMPLATE_DIR}')
    print(f'  Static            : {STATIC_DIR}')
    print(f'  URL               : http://localhost:5000')
    print('='*55 + '\n')
    app.run(debug=False, host='127.0.0.1', port=5000)
