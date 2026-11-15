#include <Arduino.h>
const uint8_t BIT0_PIN=2, BIT1_PIN=3;
uint8_t current=255, candidate=255;
unsigned long candidateSince;
// Optional RGB/buzzer work belongs only in this function; keep it nonblocking.
void updateOutputs(uint8_t state,unsigned long now) {
    bool on=false;
    switch (state) {
    case 0: on=false; break;                   // NORMAL: off
    case 1: on=(now%1000UL)<500; break;        // SUSPECT: 1 Hz
    case 2: on=true; break;                    // ALARM: solid
    case 3: on=(now%250UL)<125; break;         // FAULT: 4 Hz
    }
    digitalWrite(LED_BUILTIN,on?HIGH:LOW);
}
void setup() {
    // External 10k pull-downs are required; Uno has no INPUT_PULLDOWN.
    pinMode(BIT0_PIN,INPUT); pinMode(BIT1_PIN,INPUT); pinMode(LED_BUILTIN,OUTPUT);
    Serial.begin(9600); Serial.println(F("Alarm GPIO simulator: bit1 bit0; NO UART from hub"));
}
void loop() {
    unsigned long now=millis();
    uint8_t bits=(digitalRead(BIT1_PIN)?2:0) | (digitalRead(BIT0_PIN)?1:0);
    // Suppress the short intermediate code while STM32 writes separate GPIO ports.
    if (bits!=candidate) { candidate=bits; candidateSince=now; }
    if (candidate!=current && now-candidateSince>=10UL) {
        current=candidate;
        Serial.print(F("t=")); Serial.print(now); Serial.print(F(" bit1bit0="));
        Serial.print((current>>1)&1); Serial.print(current&1); Serial.print(' ');
        switch (current) {
        case 0: Serial.println(F("NORMAL")); break;
        case 1: Serial.println(F("SUSPECT")); break;
        case 2: Serial.println(F("ALARM")); break;
        default: Serial.println(F("FAULT")); break;
        }
    }
    updateOutputs(current==255?0:current,now);
}
