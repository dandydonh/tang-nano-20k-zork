OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { ram (rwx) : ORIGIN = 0, LENGTH = 64K }
SECTIONS {
  .text : { *(.text.start) *(.text*) *(.rodata*) } > ram
  .data : { *(.data*) *(.sdata*) } > ram
  PROVIDE(__global_pointer$ = . + 0x800);
  . = ALIGN(4);
  __bss_start = .;
  .bss (NOLOAD) : { *(.bss*) *(.sbss*) *(COMMON) . = ALIGN(4); } > ram
  __bss_end = .;
  ASSERT(__bss_end < 57344, "Firmware leaves less than 8K C stack")
}
