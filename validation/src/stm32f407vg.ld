/* Verified STM32F407G-DISC1 only. CCM is deliberately unused. */
ENTRY(Reset_Handler)
MEMORY {
    FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 1024K
    RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 128K
}
_stack_top = ORIGIN(RAM) + LENGTH(RAM);
_stack_bottom = _stack_top - 32K;
SECTIONS {
    .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
    .text : { *(.text*) *(.rodata*) . = ALIGN(4); } > FLASH
    .ARM.extab : { *(.ARM.extab*) } > FLASH
    .ARM.exidx : { *(.ARM.exidx*) } > FLASH
    .results (NOLOAD) : { KEEP(*(.results)) . = ALIGN(4); } > RAM
    .data : {
        . = ALIGN(4); _data_start = .; *(.data*) . = ALIGN(4); _data_end = .;
    } > RAM AT > FLASH
    _data_load = LOADADDR(.data);
    .bss (NOLOAD) : {
        . = ALIGN(4); _bss_start = .; *(.bss*) *(COMMON) . = ALIGN(4); _bss_end = .;
    } > RAM
    .stack _stack_bottom (NOLOAD) : { . += 32K; } > RAM
    /DISCARD/ : { *(.comment) *(.note*) }
}
ASSERT(_bss_end <= _stack_bottom, "Static RAM overlaps reserved stack")
ASSERT(SIZEOF(.results) == 1264, "Unexpected result structure size")
ASSERT(ADDR(.results) == 0x20000000, "Unexpected result address")
