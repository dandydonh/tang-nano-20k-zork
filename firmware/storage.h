#ifndef STORAGE_H
#define STORAGE_H
#include <stdint.h>
enum { STORAGE_STORY, STORAGE_SAVE_A, STORAGE_SAVE_B };
/* Fixed-size files on FAT16/FAT32. No allocation or directory writes. */
int storage_init(void);
int storage_read(unsigned file, unsigned sector, uint8_t *data);
int storage_write(unsigned bank, unsigned sector, const uint8_t *data);
int storage_writable(uint32_t sector);
#endif
