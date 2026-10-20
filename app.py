"""
Dashboard domótico - Residencial Villa La Paz (Grupo Integrador 4)

Recibe lecturas de sensores enviadas por una ESP32 (HTTP POST en JSON),
las guarda en una base de datos y las muestra en un dashboard web que
se puede instalar en Android como aplicación (PWA).

Rutas:
  POST /api/datos      La ESP32 envía una lectura (requiere la clave X-API-Key)
  GET  /api/ultimos    Última lectura de cada dispositivo
  GET  /api/historial  Lecturas recientes (parámetros: horas, dispositivo)
  GET  /               Dashboard
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, render_template, request, send_from_directory

app = Flask(__name__)

API_KEY = os.environ.get("API_KEY", "cambia-esta-clave")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USA_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
SQLITE_PATH = os.environ.get("SQLITE_PATH", "lecturas.db")


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


crear_tabla()


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
        con.execute(
            f"INSERT INTO lecturas (ts, dispositivo, datos) VALUES ({ph()}, {ph()}, {ph()})",
            (ahora(), dispositivo, json.dumps(datos)),
        )
    return jsonify(ok=True), 201


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
