"""
Dashboard domótico - Residencial Villa La Paz (Grupo Integrador 4)

Recibe lecturas de sensores enviadas por una ESP32 (HTTP POST en JSON),
las guarda en una base de datos y las muestra en un dashboard web que
se puede instalar en Android como aplicación (PWA).

Rutas:
  POST /api/datos      La ESP32 envía una lectura (requiere la clave X-API-Key).
                       La respuesta trae el estado de la alarma y del ventilador.
  GET  /api/ultimos    Última lectura de cada dispositivo
  GET  /api/historial  Lecturas recientes (parámetros: horas, dispositivo)
  GET  /api/control    Estado de armado y modo del ventilador de un dispositivo
  POST /api/control    Cambia el armado o el modo del ventilador (PIN opcional)
  GET  /               Dashboard

Avisos al teléfono: si se define la variable NTFY_TOPIC, el servidor envía una
notificación a la app ntfy cuando se dispara la alarma de un dispositivo.
Si además se definen CALLMEBOT_PHONE y CALLMEBOT_APIKEY, envía el mismo aviso
por WhatsApp con el servicio gratuito CallMeBot.
"""
import json
import os
import sqlite3
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, render_template, request, send_from_directory

app = Flask(__name__)

API_KEY = os.environ.get("API_KEY", "cambia-esta-clave")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USA_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
SQLITE_PATH = os.environ.get("SQLITE_PATH", "lecturas.db")
CONTROL_PIN = os.environ.get("CONTROL_PIN", "")      # vacío = sin PIN
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")        # vacío = sin avisos
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
CALLMEBOT_PHONE = os.environ.get("CALLMEBOT_PHONE", "")    # p. ej. +50588887777; vacío = sin WhatsApp
CALLMEBOT_APIKEY = os.environ.get("CALLMEBOT_APIKEY", "")

# Modos del ventilador (los mismos que usa la ESP32)
VENT_AUTO, VENT_ON, VENT_OFF = 0, 1, 2


# ---------------------------------------------------------------- base de datos
def conectar():
    if USA_POSTGRES:
        import psycopg
        return psycopg.connect(DATABASE_URL)
    return sqlite3.connect(SQLITE_PATH)


def ph():
    """Marcador de parámetro según el motor."""
    return "%s" if USA_POSTGRES else "?"


def crear_tabla():
    id_col = "SERIAL PRIMARY KEY" if USA_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    with conectar() as con:
        con.execute(f"""
            CREATE TABLE IF NOT EXISTS lecturas (
                id {id_col},
                ts TEXT NOT NULL,
                dispositivo TEXT NOT NULL,
                datos TEXT NOT NULL
            )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_lecturas_ts ON lecturas (ts)")
        con.execute("""
            CREATE TABLE IF NOT EXISTS control (
                dispositivo TEXT PRIMARY KEY,
                armado INTEGER NOT NULL DEFAULT 0,
                ventilador INTEGER NOT NULL DEFAULT 0
            )""")


crear_tabla()


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def leer_control(con, dispositivo):
    fila = con.execute(
        f"SELECT armado, ventilador FROM control WHERE dispositivo = {ph()}", (dispositivo,)
    ).fetchone()
    return {"armado": fila[0], "ventilador": fila[1]} if fila else {"armado": 0, "ventilador": VENT_AUTO}


def ultima_alarma(con, dispositivo):
    fila = con.execute(
        f"SELECT datos FROM lecturas WHERE dispositivo = {ph()} ORDER BY id DESC LIMIT 1", (dispositivo,)
    ).fetchone()
    return json.loads(fila[0]).get("alarma", 0) if fila else 0


def enviar_aviso(dispositivo, datos):
    """Aviso al teléfono con ntfy y WhatsApp (en segundo plano para no demorar a la ESP32)."""
    if not NTFY_TOPIC and not (CALLMEBOT_PHONE and CALLMEBOT_APIKEY):
        return
    causa = "se abrió la puerta" if datos.get("puerta") == 1 else "se detectó movimiento"
    mensaje = f"Alarma en {dispositivo}: {causa}."

    def tarea():
        if NTFY_TOPIC:
            try:
                req = urllib.request.Request(
                    f"{NTFY_SERVER}/{NTFY_TOPIC}", data=mensaje.encode("utf-8"),
                    headers={"Title": "Alarma domotica", "Priority": "high", "Tags": "rotating_light"})
                urllib.request.urlopen(req, timeout=10)
                app.logger.warning("Aviso enviado por ntfy al tema %s", NTFY_TOPIC)
            except Exception as e:  # el aviso no debe interrumpir el registro de la lectura
                app.logger.warning("No se pudo enviar el aviso por ntfy: %s", e)
        if CALLMEBOT_PHONE and CALLMEBOT_APIKEY:
            try:
                consulta = urllib.parse.urlencode(
                    {"phone": CALLMEBOT_PHONE, "text": "🚨 " + mensaje, "apikey": CALLMEBOT_APIKEY})
                with urllib.request.urlopen(f"https://api.callmebot.com/whatsapp.php?{consulta}", timeout=15) as r:
                    # CallMeBot responde 200 aunque falle; su texto dice si el mensaje salió
                    app.logger.warning("Respuesta de CallMeBot: %s", r.read(300).decode("utf-8", "replace"))
            except Exception as e:
                app.logger.warning("No se pudo enviar el aviso por WhatsApp: %s", e)

    threading.Thread(target=tarea, daemon=True).start()


# ---------------------------------------------------------------- API
@app.post("/api/datos")
def recibir():
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify(error="clave inválida"), 401
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        return jsonify(error="se esperaba un JSON"), 400

    dispositivo = str(cuerpo.pop("dispositivo", "esp32-1"))[:40]
    # Solo se guardan valores numéricos o booleanos (los booleanos como 0/1)
    datos = {}
    for k, v in cuerpo.items():
        if isinstance(v, bool):
            datos[str(k)[:40]] = int(v)
        elif isinstance(v, (int, float)):
            datos[str(k)[:40]] = v
    if not datos:
        return jsonify(error="no hay valores numéricos"), 400

    with conectar() as con:
        alarma_previa = ultima_alarma(con, dispositivo)
        con.execute(
            f"INSERT INTO lecturas (ts, dispositivo, datos) VALUES ({ph()}, {ph()}, {ph()})",
            (ahora(), dispositivo, json.dumps(datos)),
        )
        control = leer_control(con, dispositivo)
    if datos.get("alarma") == 1 and alarma_previa != 1:
        app.logger.warning("Alarma disparada en %s: enviando avisos", dispositivo)
        enviar_aviso(dispositivo, datos)
    # La ESP32 lee de esta respuesta si el sistema está armado y el modo del ventilador
    return jsonify(ok=True, **control), 201


@app.get("/api/control")
def ver_control():
    dispositivo = request.args.get("dispositivo", "casa-1")[:40]
    with conectar() as con:
        control = leer_control(con, dispositivo)
    return jsonify(dispositivo=dispositivo, pin=bool(CONTROL_PIN), **control)


@app.post("/api/control")
def cambiar_control():
    if CONTROL_PIN and request.headers.get("X-Control-Pin") != CONTROL_PIN:
        return jsonify(error="PIN incorrecto"), 401
    cuerpo = request.get_json(silent=True) or {}
    dispositivo = str(cuerpo.get("dispositivo", "casa-1"))[:40]
    with conectar() as con:
        control = leer_control(con, dispositivo)
        if cuerpo.get("armado") in (0, 1, True, False):
            control["armado"] = int(cuerpo["armado"])
        if cuerpo.get("ventilador") in (VENT_AUTO, VENT_ON, VENT_OFF):
            control["ventilador"] = int(cuerpo["ventilador"])
        con.execute(
            f"""INSERT INTO control (dispositivo, armado, ventilador) VALUES ({ph()}, {ph()}, {ph()})
                ON CONFLICT (dispositivo) DO UPDATE SET armado = excluded.armado,
                ventilador = excluded.ventilador""",
            (dispositivo, control["armado"], control["ventilador"]),
        )
    return jsonify(ok=True, dispositivo=dispositivo, **control)


@app.get("/api/ultimos")
def ultimos():
    with conectar() as con:
        filas = con.execute("""
            SELECT l.ts, l.dispositivo, l.datos FROM lecturas l
            JOIN (SELECT dispositivo, MAX(id) AS mid FROM lecturas GROUP BY dispositivo) u
              ON l.id = u.mid
            ORDER BY l.dispositivo""").fetchall()
    return jsonify([{"ts": ts, "dispositivo": d, "datos": json.loads(j)} for ts, d, j in filas])


@app.get("/api/historial")
def historial():
    horas = min(max(request.args.get("horas", 6, type=float), 0.1), 168)
    desde = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat(timespec="seconds")
    dispositivo = request.args.get("dispositivo")
    sql = f"SELECT ts, dispositivo, datos FROM lecturas WHERE ts >= {ph()}"
    params = [desde]
    if dispositivo:
        sql += f" AND dispositivo = {ph()}"
        params.append(dispositivo)
    sql += " ORDER BY id DESC LIMIT 2000"
    with conectar() as con:
        filas = con.execute(sql, params).fetchall()
    filas.reverse()
    return jsonify([{"ts": ts, "dispositivo": d, "datos": json.loads(j)} for ts, d, j in filas])


# ---------------------------------------------------------------- páginas
@app.get("/")
def dashboard():
    return render_template("index.html")


# El service worker debe servirse desde la raíz para controlar todo el sitio
@app.get("/sw.js")
def service_worker():
    resp = send_from_directory("static", "sw.js", mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/manifest.webmanifest")
def manifest():
    return send_from_directory("static", "manifest.webmanifest",
                               mimetype="application/manifest+json")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
