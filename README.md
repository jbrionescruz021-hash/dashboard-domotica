# Dashboard domótico · Residencial Villa La Paz

Dashboard en Python (Flask) que recibe los datos de los sensores de una ESP32,
los guarda en PostgreSQL y los muestra en gráficas que se actualizan cada 5 segundos.
El dashboard se puede instalar en Android como una app (PWA).

```
ESP32 ──HTTP POST (JSON)──▶ Flask en Render ──▶ PostgreSQL
                                   │
                    navegador / app Android ◀── dashboard
```

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `app.py` | Servidor Flask: recibe datos (`/api/datos`) y sirve el dashboard |
| `templates/index.html` | Página del dashboard (tarjetas, gráficas y tabla) |
| `static/` | Chart.js, íconos, manifest y service worker de la app Android |
| `requirements.txt` | Librerías de Python |
| `render.yaml` | Configuración para crear todo en Render con un clic |
| `esp32/prototipo_domotico.ino` | Programa completo de la placa (sensores, relé, zumbador, LED y control desde el panel) |
| `esp32/esp32_envio_dashboard.ino` | Versión básica anterior (solo envía DHT22, PIR y puerta) |
| `simulador.py` | Envía datos falsos para probar sin la ESP32 |

## 1. Probar en tu computadora (opcional)

```bash
pip install -r requirements.txt
python app.py                       # abre http://localhost:5000
python simulador.py                 # en otra terminal: envía datos de prueba
```

Sin la variable `DATABASE_URL`, los datos se guardan en un archivo local `lecturas.db`.

## 2. Subir el código a GitHub

1. Crea una cuenta en https://github.com y un repositorio nuevo (por ejemplo `dashboard-domotica`).
2. En el repositorio, elige **Add file → Upload files** y arrastra **el contenido** de esta carpeta
   (`app.py`, `requirements.txt`, `render.yaml`, y las carpetas `templates`, `static` y `esp32`).
3. Presiona **Commit changes**.

## 3. Publicar en Render

1. Entra a https://render.com y regístrate con tu cuenta de GitHub (el plan gratuito no pide tarjeta).
2. Elige **New → Blueprint** y selecciona tu repositorio. Render lee `render.yaml` y crea:
   - el servicio web `domotica-villa-la-paz`
   - la base de datos PostgreSQL gratuita `domotica-db`
3. Presiona **Apply** y espera a que termine (unos minutos).
4. Abre el servicio web: arriba aparece tu dirección, por ejemplo
   `https://domotica-villa-la-paz.onrender.com`.
5. En **Environment** copia el valor de `API_KEY` (Render lo genera solo). Esa es la clave
   que debe llevar la ESP32.

> Si prefieres no usar el Blueprint: crea primero una base **PostgreSQL** gratuita, luego un
> **Web Service** con *Build command* `pip install -r requirements.txt` y *Start command*
> `gunicorn app:app`, y agrega las variables `DATABASE_URL` (la *Internal Database URL* de la base)
> y `API_KEY` (una clave que tú inventes).

## 4. Configurar la ESP32

En `esp32/prototipo_domotico.ino` cambia:

```cpp
const char* WIFI_SSID     = "NOMBRE_DE_TU_WIFI";
const char* WIFI_PASSWORD = "CLAVE_DE_TU_WIFI";
const char* SERVIDOR      = "https://TU-DIRECCION.onrender.com/api/datos";
const char* API_KEY       = "LA_API_KEY_DE_RENDER";
```

Instala la librería **DHT sensor library** (Adafruit) y sube el código. En el Monitor Serie
debe aparecer `respuesta 201` en cada envío.

La ESP32 puede enviar cualquier campo numérico; el dashboard crea una tarjeta y una gráfica
por cada uno. Ejemplo:

```json
{"dispositivo": "casa-1", "temperatura": 28.5, "humedad": 70, "movimiento": 1, "puerta": 0}
```

Para darle nombre y unidad a un sensor nuevo, agrégalo en `SENSORES` dentro de
`templates/index.html` (los sensores de encendido/apagado llevan `binario`).

## 5. Instalar la app

El botón **Instalar app** aparece arriba a la derecha del dashboard.

- **Android (Chrome):** toca **Instalar app** y confirma, o menú ⋮ → **Instalar app**.
- **iPhone (Safari):** toca **Instalar app** para ver los pasos: **Compartir → Agregar a pantalla de inicio**.
- **Computadora (Chrome o Edge):** ícono de instalar en la barra de direcciones.

Queda un ícono "Domótica" que abre el dashboard en pantalla completa.

## API

| Ruta | Método | Descripción |
|---|---|---|
| `/api/datos` | POST | Guarda una lectura. Encabezado `X-API-Key` obligatorio |
| `/api/ultimos` | GET | Última lectura de cada dispositivo |
| `/api/historial?horas=6&dispositivo=casa-1` | GET | Lecturas recientes (máximo 2000) |
| `/api/control?dispositivo=casa-1` | GET | Estado de armado y modo del ventilador |
| `/api/control` | POST | Cambia `armado` (0/1) o `ventilador` (0 auto, 1 encendido, 2 apagado). Encabezado `X-Control-Pin` si se definió `CONTROL_PIN` |
| `/api/control/check` | POST | Verifica el PIN del panel sin cambiar nada (encabezado `X-Control-Pin`) |

La ESP32 consulta `/api/control` cada 3 segundos, y la respuesta de `/api/datos` también trae `armado` y `ventilador`.
Así las órdenes del panel se aplican en unos 3 segundos.

## Alarma, ventilador y avisos al teléfono

- El programa completo de la placa con relé, zumbador y LED está en
  `../prototipo/esp32/prototipo_domotico.ino`, y el circuito de Wokwi en `../prototipo/wokwi/`.
- En el panel, la sección **Control** tiene dos interruptores:
  - **Ventilador:** encendido o apagado manual. La casilla **Automático** lo devuelve al control por
    temperatura (enciende a 30 °C y apaga a 28 °C). Debajo se ve si la placa ya confirmó la orden.
  - **Alarma de puerta:** arma o desarma la vigilancia del sensor magnético MC-38 (y del PIR). El panel
    muestra siempre si la puerta está abierta o cerrada, y la tarjeta se marca en rojo si la alarma suena.
    Desarmarla silencia el zumbador.
- Si se definió `CONTROL_PIN`, el panel pide el PIN una vez (en la misma página, junto a los interruptores)
  y lo recuerda en ese dispositivo. **Cambia el PIN `1234` de `render.yaml` por uno propio en Render.**
- **Avisos:** instala la app **ntfy** en el teléfono, toca **+** y suscríbete al mismo tema de la variable
  `NTFY_TOPIC`. Cuando la alarma se dispara llega un aviso, uno por cada disparo.

## Límites del plan gratuito de Render

- El servicio se **duerme** tras 15 minutos sin visitas; la primera petición tarda unos
  segundos. Mientras la ESP32 envíe datos cada 10 segundos, el servicio se mantiene despierto.
- La base PostgreSQL gratuita **vence a los 30 días** de creada (Render avisa por correo).
  Para la presentación basta; después se puede crear otra y cambiar `DATABASE_URL`.
