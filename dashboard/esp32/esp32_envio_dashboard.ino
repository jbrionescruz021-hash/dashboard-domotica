/*
  Envío de datos de sensores de la ESP32 al dashboard en Render
  Residencial Villa La Paz - Grupo Integrador 4

  Sensores de ejemplo (cámbialos por los tuyos):
    - DHT22 (temperatura y humedad)  -> GPIO 4
    - Sensor de movimiento PIR       -> GPIO 27
    - Sensor magnético de puerta     -> GPIO 26 (a GND, con INPUT_PULLUP)

  Librería necesaria (Gestor de librerías del IDE de Arduino):
    - "DHT sensor library" de Adafruit (instala también "Adafruit Unified Sensor")
*/
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <DHT.h>

// ---------- Configuración ----------
const char* WIFI_SSID     = "NOMBRE_DE_TU_WIFI";
const char* WIFI_PASSWORD = "CLAVE_DE_TU_WIFI";
// Dirección que te da Render + /api/datos
const char* SERVIDOR      = "https://domotica-villa-la-paz.onrender.com/api/datos";
// La misma clave que la variable API_KEY en Render
const char* API_KEY       = "PEGA_AQUI_TU_API_KEY";
const char* DISPOSITIVO   = "casa-1";
const unsigned long INTERVALO_MS = 10000;   // cada 10 segundos

#define PIN_DHT     4
#define PIN_PIR     27
#define PIN_PUERTA  26

DHT dht(PIN_DHT, DHT22);
unsigned long ultimoEnvio = 0;

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

void setup() {
  Serial.begin(115200);
  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_PUERTA, INPUT_PULLUP);
  dht.begin();
  WiFi.mode(WIFI_STA);
  conectarWiFi();
}

void loop() {
  if (millis() - ultimoEnvio < INTERVALO_MS) return;
  ultimoEnvio = millis();
  conectarWiFi();
  if (WiFi.status() != WL_CONNECTED) return;

  float temperatura = dht.readTemperature();
  float humedad     = dht.readHumidity();
  int movimiento    = digitalRead(PIN_PIR);              // 1 = movimiento
  int puerta        = digitalRead(PIN_PUERTA);           // 1 = abierta (imán separado)

  if (isnan(temperatura) || isnan(humedad)) {
    Serial.println("Error al leer el DHT22");
    return;
  }

  char json[200];
  snprintf(json, sizeof(json),
           "{\"dispositivo\":\"%s\",\"temperatura\":%.1f,\"humedad\":%.0f,"
           "\"movimiento\":%d,\"puerta\":%d}",
           DISPOSITIVO, temperatura, humedad, movimiento, puerta);

  WiFiClientSecure cliente;
  cliente.setInsecure();          // HTTPS sin verificar el certificado (suficiente para el proyecto)
  HTTPClient http;
  http.setTimeout(15000);         // Render gratuito puede tardar al "despertar"
  http.begin(cliente, SERVIDOR);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  int codigo = http.POST(json);
  Serial.printf("Enviado %s -> respuesta %d\n", json, codigo);
  http.end();
}
