#ifndef PLATFORM_H
#define PLATFORM_H
#include <stdint.h>
enum { KEY_UP=256, KEY_DOWN=257 };
void console_put(int c);
int console_get(void);
void status_put(unsigned col, int c);
int disk_read(uint32_t sector, uint8_t *data);
int disk_write(uint32_t sector, const uint8_t *data);
void platform_init(void);
void fatal(const char *message);
#endif
