CC = gcc
COMMON_INC = -Icommon -Icommon/CommSmoke/src -Istm32_hub/include
HOST_FLAGS = -std=c11 -Wall -Wextra -Werror -pedantic -g -O1
CORE = common/parser.c stm32_hub/src/hub.c stm32_hub/src/dma_stream.c
.PHONY: test host-test python-test stm32 arduino clean
# Python tests call the actual C encoder/parser/state code via a shared library.
test: host-test python-test
build:
	mkdir -p build
build/libcommtest.so: $(CORE) tests/host_bridge.c $(wildcard common/*.h common/CommSmoke/src/*.h stm32_hub/include/*.h) | build
	$(CC) $(HOST_FLAGS) $(COMMON_INC) -fPIC -shared $(CORE) tests/host_bridge.c -o $@
build/core_test: $(CORE) tests/core_test.c $(wildcard common/*.h common/CommSmoke/src/*.h stm32_hub/include/*.h) | build
	$(CC) $(HOST_FLAGS) $(COMMON_INC) -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie $(CORE) tests/core_test.c -o $@
host-test: build/core_test
	ASAN_OPTIONS=detect_leaks=0 ./build/core_test
python-test: build/libcommtest.so
	python3 -m unittest discover -s tests -v
stm32:
	$(MAKE) -C stm32_hub
arduino:
	arduino-cli compile --fqbn arduino:avr:uno --libraries "$(CURDIR)/common" arduino_window_sim
	arduino-cli compile --fqbn arduino:avr:uno --libraries "$(CURDIR)/common" arduino_door_sim
	arduino-cli compile --fqbn arduino:avr:uno --libraries "$(CURDIR)/common" arduino_alarm_sim
clean:
	rm -rf build
	$(MAKE) -C stm32_hub clean
