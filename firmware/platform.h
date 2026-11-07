#ifndef PLATFORM_H
#define PLATFORM_H
#include <stdint.h>
enum { KEY_UP=256, KEY_DOWN=257 };
#define CONSOLE_COLUMNS 79U
void console_reset(void);
/* Usable serial columns, excluding the physical terminal's right margin. */
void console_width(unsigned columns);
void console_input_begin(void);
void console_serial_emit(int c);
void console_serial_previous(unsigned width);
void console_put(int c);
void console_story_put(int c);
void console_story_flush(void);
/* Count completed lower-window lines; input starts a fresh page. Height zero
 * disables paging for noninteractive native tests. */
void console_page_height(unsigned rows);
void console_page_reset(void);
unsigned console_menu_rows(void);
unsigned console_menu_columns(void);
void console_menu_reset(void);
void console_clear(void);
void console_page(unsigned top);
void console_more(void);
/* HDMI backend: emit one unwrapped character or move to the previous
 * transcript line's last used column. Serial has a separate sink above. */
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
