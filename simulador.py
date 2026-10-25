"""
Simulador de la ESP32: envía lecturas falsas al dashboard para probarlo
sin tener el hardware conectado.

Uso:
  python simulador.py http://localhost:5000 cambia-esta-clave
  python simulador.py https://domotica-villa-la-paz.onrender.com TU_API_KEY
"""
import json
import math
import random
import sys
import time
import urllib.request

url = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000").rstrip("/") + "/api/datos"
clave = sys.argv[2] if len(sys.argv) > 2 else "cambia-esta-clave"
puerta = 0
armado, modo_ventilador, modo_alarma, led_azul = 0, 0, 0, 0   # los envía el servidor en cada respuesta
ventilador, alarma = 0, 0

while True:
    t = time.time()
    if random.random() < 0.05:
        puerta = 1 - puerta
    temperatura = round(28 + 3 * math.sin(t / 600) + random.uniform(-0.3, 0.3), 1)
    movimiento = int(random.random() < 0.2)
    # Misma lógica que la ESP32: ventilador con histéresis y alarma con el sistema armado
    if modo_ventilador == 1:
        ventilador = 1
    elif modo_ventilador == 2:
        ventilador = 0
    elif temperatura >= 30:
        ventilador = 1
    elif temperatura <= 28:
        ventilador = 0
    if modo_alarma == 1:
        alarma = 1
    elif modo_alarma == 2 or not armado:
        alarma = 0
    else:
        alarma = int(alarma or puerta == 1 or movimiento == 1)
    lectura = {
        "dispositivo": "casa-1",
        "temperatura": temperatura,
        "humedad": round(70 + 8 * math.cos(t / 900) + random.uniform(-1, 1)),
        "movimiento": movimiento,
        "puerta": puerta,
        "luz": max(0, min(100, round(50 + 45 * math.sin(t / 1800)))),
        "ventilador": ventilador,
        "alarma": alarma,
        "led_azul": led_azul,
    }
    req = urllib.request.Request(url, data=json.dumps(lectura).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-API-Key": clave})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read())
            armado, modo_ventilador = resp.get("armado", 0), resp.get("ventilador", 0)
            modo_alarma, led_azul = resp.get("alarma_modo", 0), resp.get("led_azul", 0)
            print(r.status, lectura, "| armado:", armado, "ventilador:", modo_ventilador,
                  "alarma:", modo_alarma, "led azul:", led_azul)
    except Exception as e:
        print("Error:", e)
    time.sleep(5)
