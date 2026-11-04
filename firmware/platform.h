#ifndef PLATFORM_H
#define PLATFORM_H
#include <stdint.h>
enum { KEY_UP=256, KEY_DOWN=257 };
#define CONSOLE_COLUMNS 79U
void console_reset(void);
void console_put(int c);
void console_story_put(int c);
void console_story_flush(void);
/* Platform backend: emit one unwrapped character or move to the previous
 * transcript line's last used column. Status output bypasses the formatter. */
void console_emit(int c);
int console_previous_line(void);
int console_get(void);
void status_put(unsigned col, int c);
void status_flush(unsigned right_start);
int sd_read_sector(uint32_t sector, uint8_t *data);
int sd_write_sector(uint32_t sector, const uint8_t *data);
void platform_init(void);
void fatal(const char *message);
#endif
