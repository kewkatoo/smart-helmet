#include <HardwareSerial.h>
#include <TinyGPS++.h>

// ==========================================
// PIN DEFINITIONS & CONFIGURATION
// ==========================================
// GPS Module (NEO-6M / compatible)
#define GPS_RX 16
#define GPS_TX 17
HardwareSerial gpsSerial(2); // Use UART2 for GPS
TinyGPSPlus gps;

// MQ-3 Alcohol / Gas Sensor
#define MQ3_PIN 34

// Proximity Warning Actuators
#define BUZZER_PIN 23   // Optional active buzzer
#define LED_PIN    2    // Onboard or external status LED

// Baud Rate (Must match backend app.py)
#define SERIAL_BAUD 115200
#define GPS_BAUD    9600

// Proximity state
String currentProximity = "SAFE";
unsigned long lastSensorSendTime = 0;
const unsigned long SENSOR_SEND_INTERVAL = 500; // Send telemetry every 500ms

void setup() {
  // Initialize USB Serial for PC Communication
  Serial.begin(SERIAL_BAUD);

  // Initialize Hardware Serial for GPS
  gpsSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX, GPS_TX);

  // Initialize Sensor & Actuator Pins
  pinMode(MQ3_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);

  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(LED_PIN, LOW);

  Serial.println("[ESP32] Smart Helmet Initialized (Baud: 115200)");
}

void loop() {
  // 1. Read incoming GPS data from UART2
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }

  // 2. Read incoming Proximity commands from PC (USB Serial)
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();

    if (command.startsWith("PROXIMITY:")) {
      currentProximity = command.substring(10);
      handleProximityAlert(currentProximity);
    }
  }

  // 3. Periodically stream GPS & MQ3 telemetry to PC
  unsigned long now = millis();
  if (now - lastSensorSendTime >= SENSOR_SEND_INTERVAL) {
    lastSensorSendTime = now;

    // Send GPS data
    if (gps.location.isValid()) {
      Serial.print("GPS:");
      Serial.print(gps.location.lat(), 6);
      Serial.print(",");
      Serial.print(gps.location.lng(), 6);
      Serial.print(",");
      Serial.println(gps.speed.kmph());
    } else {
      // Fallback placeholder when acquiring GPS satellite lock
      Serial.println("GPS:N/A,N/A,0.0");
    }

    // Send MQ-3 Sensor Data
    int mq3Value = analogRead(MQ3_PIN);
    Serial.print("MQ3:");
    Serial.println(mq3Value);
  }
}

// Handle LED / Buzzer pattern based on proximity level
void handleProximityAlert(String level) {
  if (level == "DANGER") {
    digitalWrite(LED_PIN, HIGH);
    digitalWrite(BUZZER_PIN, HIGH);
  } else if (level == "WARNING") {
    digitalWrite(LED_PIN, HIGH);
    digitalWrite(BUZZER_PIN, LOW);
  } else { // SAFE
    digitalWrite(LED_PIN, LOW);
    digitalWrite(BUZZER_PIN, LOW);
  }
}
