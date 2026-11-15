#include <node_sim.h>
NodeSimulator simulator(NODE_WINDOW);
void setup() { simulator.begin(); }
void loop() { simulator.loop(); }
