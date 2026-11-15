# Requires official STM32CubeF1 CMSIS files; no HAL source is linked.
CUBE_F1 ?= $(HOME)/STM32Cube/Repository/STM32Cube_FW_F1_V1.8.6
CROSS ?= arm-none-eabi-
NODE_BAUD ?= 38400
CC = $(CROSS)gcc
CMSIS = $(CUBE_F1)/Drivers/CMSIS
DEVICE = $(CMSIS)/Device/ST/STM32F1xx
STARTUP = $(DEVICE)/Source/Templates/gcc/startup_stm32f103xb.s
BUILD = build/$(NODE_BAUD)
TARGET = $(BUILD)/hub
SOURCES = src/main.c src/hub.c src/dma_stream.c src/platform.c src/system.c ../common/parser.c
OBJECTS = $(addprefix $(BUILD)/,$(notdir $(SOURCES:.c=.o))) $(BUILD)/startup.o
CPPFLAGS = -DSTM32F103xB -DNODE_BAUD=$(NODE_BAUD) -Iinclude -I../common -I../common/CommSmoke/src -I$(CMSIS)/Include -I$(DEVICE)/Include
CFLAGS = -mcpu=cortex-m3 -mthumb -std=c11 -Os -g3 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -MMD -MP
LDFLAGS = -mcpu=cortex-m3 -mthumb -TSTM32F103RB.ld --specs=nano.specs --specs=nosys.specs -Wl,--gc-sections,-Map=$(TARGET).map
vpath %.c src ../common
.PHONY: all check clean
all: check $(TARGET).elf $(TARGET).bin
check:
	@command -v $(CC) >/dev/null || { echo 'Missing ARM GCC: install gcc-arm-none-eabi and libnewlib-arm-none-eabi'; exit 1; }
	@test -f "$(STARTUP)" || { echo 'Set CUBE_F1 to the installed STM32CubeF1 package root'; exit 1; }
$(BUILD):
	mkdir -p $@
$(BUILD)/%.o: %.c | $(BUILD) check
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@
$(BUILD)/startup.o: | $(BUILD) check
	$(CC) -mcpu=cortex-m3 -mthumb -c "$(STARTUP)" -o $@
$(TARGET).elf: $(OBJECTS) STM32F103RB.ld
	$(CC) $(OBJECTS) $(LDFLAGS) -o $@
	$(CROSS)size $@
$(TARGET).bin: $(TARGET).elf
	$(CROSS)objcopy -O binary $< $@
clean:
	rm -rf build
-include $(OBJECTS:.o=.d)
