#ifndef PLATFORM_H
#define PLATFORM_H
#include <stdint.h>
/* Key events must not overlap Unicode scalar values such as U+0100. */
enum { KEY_UP=0x110000, KEY_DOWN=0x110001 };
/* Complete PS/2 characters (including ASCII) are distinct from UART bytes. */
#define KEY_UNICODE_BASE 0x200000U
static inline int key_is_unicode(unsigned event) {
  return event>=KEY_UNICODE_BASE&&event<=KEY_UNICODE_BASE+0x10ffff;
}
static inline int key_plain(unsigned event) {
  return key_is_unicode(event)?event-KEY_UNICODE_BASE:event;
}
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
void console_edit_begin(unsigned initial_cells);
void console_edit_clear(void);
void console_edit_end(void);
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
/* Source-aware input for UTF-8 decoding: UART bytes or atomic PS/2 events. */
int console_event_get(void);
void status_put(unsigned col, int c);
void status_flush(unsigned right_start);
int sd_read_sector(uint32_t sector, uint8_t *data);
int sd_write_sector(uint32_t sector, const uint8_t *data);
void platform_init(void);
void fatal(const char *message);
#endif
