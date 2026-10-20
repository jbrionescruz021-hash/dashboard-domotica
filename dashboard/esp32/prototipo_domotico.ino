/*
  Prototipo domótico - Residencial Villa La Paz (Grupo Integrador 4)
  ESP32 + sensores + actuadores, con envío al dashboard en Render.

  Entradas:
    - DHT22 (temperatura y humedad)          -> GPIO 4
    - Sensor de movimiento PIR HC-SR501      -> GPIO 27
    - Sensor magnético de puerta MC-38       -> GPIO 26 (a GND, con INPUT_PULLUP)
    - Fotorresistencia (LDR a GND y 10 kΩ a 3,3 V) -> GPIO 34 (entrada analógica)
  Salidas:
    - Módulo de relé (ventilador)            -> GPIO 25
    - Zumbador (buzzer) de alarma            -> GPIO 33
    - LED rojo de alarma (con 220 Ω)         -> GPIO 32

  Funcionamiento:
    - Ventilador: en modo automático se enciende a 30 °C o más y se apaga
      a 28 °C o menos (histéresis). Desde la app se puede forzar encendido
      o apagado.
    - Alarma: si el sistema está ARMADO desde la app y se abre la puerta
      o hay movimiento, suenan el zumbador y el LED, y la lectura se envía
      de inmediato para que el servidor mande el aviso al teléfono.
      La alarma se apaga al desarmar el sistema desde la app.
    - Envío: una lectura cada 10 s, o al instante si cambia la puerta,
      el movimiento o la alarma. La respuesta del servidor trae el estado
      de "armado" y el modo del ventilador.

  Librería necesaria (Gestor de librerías del IDE de Arduino):
    - "DHT sensor library" de Adafruit (instala también "Adafruit Unified Sensor")
*/
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <DHT.h>

// ---------- Configuración ----------
const char* WIFI_SSID     = "NOMBRE_DE_TU_WIFI";   // En Wokwi: "Wokwi-GUEST"
const char* WIFI_PASSWORD = "CLAVE_DE_TU_WIFI";    // En Wokwi: ""
const char* SERVIDOR      = "https://domotica-villa-la-paz.onrender.com/api/datos";
const char* API_KEY       = "PEGA_AQUI_TU_API_KEY";
const char* DISPOSITIVO   = "casa-1";

const unsigned long INTERVALO_MS = 10000;  // envío periódico
const unsigned long MINIMO_MS    = 2000;   // separación mínima entre envíos por evento
const float T_ENCENDER = 30.0;             // °C
const float T_APAGAR   = 28.0;             // °C

#define PIN_DHT       4
#define PIN_PIR       27
#define PIN_PUERTA    26
#define PIN_LDR       34
#define PIN_RELE      25
#define PIN_BUZZER    33
#define PIN_LED       32

// Modos del ventilador que envía el servidor
#define VENT_AUTO     0
#define VENT_ON       1
#define VENT_OFF      2

DHT dht(PIN_DHT, DHT22);

// Variables internas
bool  armado = false;          // estado de la alarma (lo decide la app)
int   modoVentilador = VENT_AUTO;
bool  alarma = false;          // alarma disparada
bool  ventilador = false;      // estado del relé
float temperatura = NAN, humedad = NAN;
int   movimiento = 0, puerta = 0, luz = 0;
int   movAnterior = -1, puertaAnterior = -1;
bool  alarmaAnterior = false;
unsigned long ultimoEnvio = 0, ultimaLecturaDHT = 0;

void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.print("Conectando a WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? " conectado" : " sin conexión");
}

// Busca "clave":numero en la respuesta JSON del servidor
int leerEntero(const String& json, const char* clave, int porDefecto) {
  String patron = String("\"") + clave + "\":";
  int i = json.indexOf(patron);
  if (i < 0) return porDefecto;
  return json.substring(i + patron.length()).toInt();
}

void leerSensores() {
  if (millis() - ultimaLecturaDHT >= 2000) {      // el DHT22 admite 1 lectura cada 2 s
    ultimaLecturaDHT = millis();
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    if (!isnan(t) && !isnan(h)) { temperatura = t; humedad = h; }
  }
  movimiento = digitalRead(PIN_PIR);              // 1 = movimiento
  puerta     = digitalRead(PIN_PUERTA);           // 1 = abierta (imán separado)
  // Con más luz baja la resistencia de la LDR y baja el voltaje en GPIO 34
  luz        = 100 - map(analogRead(PIN_LDR), 0, 4095, 0, 100);  // 0 = oscuro, 100 = mucha luz
}

void controlarActuadores() {
  // Ventilador con histéresis
  if (modoVentilador == VENT_ON)       ventilador = true;
  else if (modoVentilador == VENT_OFF) ventilador = false;
  else if (!isnan(temperatura)) {
    if (temperatura >= T_ENCENDER)     ventilador = true;
    else if (temperatura <= T_APAGAR)  ventilador = false;
  }
  digitalWrite(PIN_RELE, ventilador ? HIGH : LOW);

  // Alarma: se dispara con el sistema armado y se apaga al desarmar
  if (!armado) alarma = false;
  else if (puerta == 1 || movimiento == 1) alarma = true;

  static bool sonando = false;
  bool encendido = alarma && ((millis() / 250) % 2);   // parpadeo 2 veces por segundo
  digitalWrite(PIN_LED, encendido ? HIGH : LOW);
  if (encendido && !sonando)      tone(PIN_BUZZER, 2000);
  else if (!encendido && sonando) noTone(PIN_BUZZER);
  sonando = encendido;
}

void enviar() {
  conectarWiFi();
  if (WiFi.status() != WL_CONNECTED || isnan(temperatura)) return;

  char json[256];
  snprintf(json, sizeof(json),
           "{\"dispositivo\":\"%s\",\"temperatura\":%.1f,\"humedad\":%.0f,"
           "\"movimiento\":%d,\"puerta\":%d,\"luz\":%d,"
           "\"ventilador\":%d,\"alarma\":%d}",
           DISPOSITIVO, temperatura, humedad, movimiento, puerta, luz,
           ventilador ? 1 : 0, alarma ? 1 : 0);

  WiFiClientSecure cliente;
  cliente.setInsecure();          // HTTPS sin verificar el certificado (suficiente para el proyecto)
  HTTPClient http;
  http.setTimeout(15000);         // Render gratuito puede tardar al "despertar"
  http.begin(cliente, SERVIDOR);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  int codigo = http.POST(json);
  if (codigo == 201) {
    String resp = http.getString();             // {"ok":true,"armado":1,"ventilador":0}
    armado = leerEntero(resp, "armado", armado) == 1;
    modoVentilador = leerEntero(resp, "ventilador", modoVentilador);
  }
  Serial.printf("Enviado %s -> respuesta %d (armado=%d, modo ventilador=%d)\n",
                json, codigo, armado, modoVentilador);
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_PUERTA, INPUT_PULLUP);
  pinMode(PIN_RELE, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  dht.begin();
  WiFi.mode(WIFI_STA);
  conectarWiFi();
}

void loop() {
  leerSensores();
  controlarActuadores();

  bool evento = (movimiento != movAnterior) || (puerta != puertaAnterior) || (alarma != alarmaAnterior);
  unsigned long transcurrido = millis() - ultimoEnvio;
  if (transcurrido >= INTERVALO_MS || (evento && transcurrido >= MINIMO_MS)) {
    ultimoEnvio = millis();
    movAnterior = movimiento;
    puertaAnterior = puerta;
    alarmaAnterior = alarma;
    enviar();
  }
  delay(20);
}
