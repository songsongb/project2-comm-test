#include "stm32f1xx.h"
#include "board_pins.h"
uint32_t SystemCoreClock=HUB_CLOCK_HZ;
void SystemInit(void) {
    RCC->CR |= RCC_CR_HSION;
    while (!(RCC->CR & RCC_CR_HSIRDY)) { }
    RCC->CFGR=0; /* HSI, AHB/APB1/APB2 /1, no PLL, no USART remap. */
    while (RCC->CFGR & RCC_CFGR_SWS) { }
    RCC->CR &= ~(RCC_CR_PLLON | RCC_CR_HSEON | RCC_CR_CSSON);
    RCC->CIR=0;
    SCB->VTOR=FLASH_BASE;
}
void SystemCoreClockUpdate(void) { SystemCoreClock=HUB_CLOCK_HZ; }
