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

while True:
    t = time.time()
    if random.random() < 0.05:
        puerta = 1 - puerta
    lectura = {
        "dispositivo": "casa-1",
        "temperatura": round(28 + 3 * math.sin(t / 600) + random.uniform(-0.3, 0.3), 1),
        "humedad": round(70 + 8 * math.cos(t / 900) + random.uniform(-1, 1)),
        "movimiento": int(random.random() < 0.2),
        "puerta": puerta,
    }
    req = urllib.request.Request(url, data=json.dumps(lectura).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-API-Key": clave})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(r.status, lectura)
    except Exception as e:
        print("Error:", e)
    time.sleep(5)
