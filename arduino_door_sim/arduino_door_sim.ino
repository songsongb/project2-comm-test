#include <node_sim.h>
NodeSimulator simulator(NODE_DOOR);
void setup() { simulator.begin(); }
void loop() { simulator.loop(); }
