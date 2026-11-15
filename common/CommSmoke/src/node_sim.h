#ifndef NODE_SIM_H
#define NODE_SIM_H
#include <Arduino.h>
#include <SoftwareSerial.h>
#include <stdlib.h>
#include <string.h>
#include "comm_protocol.h"
#ifndef NODE_BAUD
#define NODE_BAUD 38400UL
#endif
/* All ADC-like and event values below are synthetic. No sensors are read. */
class NodeSimulator {
    SoftwareSerial link;
    uint8_t id,seq;
    bool paused,doorOpen,lineOverflow;
    char line[40];
    uint8_t used;
    unsigned burstLeft;
    unsigned long lastHeartbeat,lastBurst;
    void sendFrame(uint8_t type,const uint8_t *payload,uint8_t len,bool corrupt=false) {
        comm_frame_t f={}; uint8_t bytes[COMM_MAX_FRAME];
        f.sender=id; f.type=type; f.len=len;
        memcpy(f.payload,payload,len);
        size_t n=comm_encode(bytes,sizeof(bytes),&f);
        if (corrupt && n) bytes[n-1]^=0x01;
        link.write(bytes,n);
    }
    void heartbeat(bool corrupt=false) {
        uint8_t p[2]={seq++,0}; sendFrame(MSG_HEARTBEAT,p,2,corrupt);
    }
    static bool number(const char *s,unsigned long low,unsigned long high,unsigned long &v) {
        if (!*s) return false;
        for (const char *p=s;*p;p++) if (*p<'0' || *p>'9') return false;
        char *end; v=strtoul(s,&end,10);
        return !*end && v>=low && v<=high;
    }
    void command() {
        unsigned long value; uint8_t p[4]={0};
        if (!strcmp(line,"pause")) { paused=true; Serial.println(F("HEARTBEAT paused; events remain enabled")); }
        else if (!strcmp(line,"resume")) {
            paused=false; heartbeat(); lastHeartbeat=millis(); Serial.println(F("HEARTBEAT resumed"));
        } else if (!strcmp(line,"badcrc")) { heartbeat(true); Serial.println(F("Injected bad XOR (SIMULATED)")); }
        else if (!strncmp(line,"burst ",6) && number(line+6,1,100,value)) {
            burstLeft=(unsigned)value; Serial.println(F("Queued heartbeat burst"));
        } else if (id==NODE_WINDOW && !strncmp(line,"beam ",5) && number(line+5,1,6553,value)) {
            comm_put_u16(p,(uint16_t)(value*10)); comm_put_u16(p+2,100);
            sendFrame(MSG_BEAM,p,4); Serial.println(F("SIMULATED beam sent (0.1ms units; synthetic min_adc=100)"));
        } else if (id==NODE_WINDOW && !strncmp(line,"sound ",6) && number(line+6,0,65535,value)) {
            comm_put_u16(p,(uint16_t)value); sendFrame(MSG_SOUND,p,2); Serial.println(F("SIMULATED sound RMS sent"));
        } else if (id==NODE_DOOR && (!strcmp(line,"door open") || !strcmp(line,"door close"))) {
            doorOpen=!strcmp(line,"door open"); p[0]=doorOpen?1:0;
            comm_put_u16(p+1,doorOpen?900:100);
            sendFrame(MSG_DOOR,p,3); Serial.println(doorOpen?F("SIMULATED door OPEN"):F("SIMULATED door CLOSED"));
        } else if (id==NODE_DOOR && !strncmp(line,"shock ",6) && number(line+6,1,255,value)) {
            p[0]=(uint8_t)value; sendFrame(MSG_SHOCK,p,1); Serial.println(F("SIMULATED shock sent"));
        } else if (!strcmp(line,"help")) {
            Serial.println(F("pause | resume | badcrc | burst 1..100 | help"));
            Serial.println(id==NODE_WINDOW?F("beam 1..6553 (ms) | sound 0..65535 (synthetic RMS)"):
                                           F("door open | door close | shock 1..255"));
        } else Serial.println(F("Invalid command; use help (lowercase, newline)"));
    }
public:
    explicit NodeSimulator(uint8_t node):link(10,11),id(node),seq(0),paused(false),doorOpen(false),
        lineOverflow(false),used(0),burstLeft(0),lastHeartbeat(0),lastBurst(0) {}
    void begin() {
        Serial.begin(9600); link.begin(NODE_BAUD); link.stopListening();
        Serial.println(F("Project2 SIMULATED node; NO physical sensor acquisition. Type help."));
        heartbeat(); lastHeartbeat=millis();
    }
    void loop() {
        unsigned budget=16;
        while (budget-- && Serial.available()) {
            char c=(char)Serial.read();
            if (c=='\n' || c=='\r') {
                if (lineOverflow) Serial.println(F("Command too long; discarded"));
                else if (used) { line[used]=0; command(); }
                used=0; lineOverflow=false;
            } else if (used<sizeof(line)-1) line[used++]=c;
            else lineOverflow=true;
        }
        unsigned long now=millis();
        if (!paused && now-lastHeartbeat>=200UL) { heartbeat(); lastHeartbeat=now; }
        if (!paused && burstLeft && now-lastBurst>=10UL) { heartbeat(); burstLeft--; lastBurst=now; }
    }
};
#endif
