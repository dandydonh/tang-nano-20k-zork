#ifndef SCREEN_H
#define SCREEN_H
#include "platform.h"
/* V5 owns the complete 79 by 32 character screen, including its status area. */
struct screen_state { uint16_t row[2],col[2],split,window,style,font,buffer,word_length,pc_graphics; char word[79]; };
extern struct screen_state screen;
void screen_reset(void);
void screen_put(int c);
/* Unicode scalars after the interpreter translates ZSCII. */
void screen_unicode_put(unsigned c);
void screen_name_put(unsigned c);
void screen_edit_begin(unsigned initial_cells);
void screen_edit_clear(void);
void screen_edit_end(void);
void screen_flush(void);
void screen_split(unsigned lines);
void screen_window(unsigned window);
void screen_cursor(unsigned row,unsigned col);
void screen_erase(int window);
void screen_erase_line(void);
void screen_style(unsigned style);
void display_cell(unsigned row,unsigned col,int c,unsigned inverse);
void display_scroll(unsigned top);
void display_clear(unsigned first,unsigned last);
void display_move(unsigned row,unsigned col);
#endif
