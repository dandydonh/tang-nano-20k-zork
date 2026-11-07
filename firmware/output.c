/* HDMI and UART share words, but wrap and count columns independently. */
#include "platform.h"
#include "unicode.h"
static unsigned column,serial_column,serial_width=CONSOLE_COLUMNS,word_length,word_columns,word_continued;
#ifdef __riscv
/* After the VM and its 512-byte sector scratch at 0x300f2000. */
#define word ((uint32_t *)0x300f2200U)
#else
static uint32_t word[CONSOLE_COLUMNS];
#endif
static unsigned edit_column,edit_serial_column,edit_lines,edit_serial_lines,edit_initial;
static unsigned editing;
static unsigned page_height,page_lines;
void console_page_height(unsigned rows) { page_height=rows;page_lines=0; }
void console_page_reset(void) { page_lines=0; }
unsigned console_menu_rows(void) { return page_height&&page_height<32?page_height:32; }
unsigned console_menu_columns(void) { return serial_width<CONSOLE_COLUMNS?serial_width:CONSOLE_COLUMNS; }
void console_menu_reset(void) { column=serial_column=word_length=word_columns=word_continued=page_lines=editing=0; }
void console_width(unsigned columns) {
  if(columns<7||columns>998)return;
  serial_width=columns;
  if(serial_column>columns)serial_column=columns;
}
void console_page(unsigned top) {
  if(page_height&&++page_lines>=(page_height>top+1?page_height-top-1:1)) {
    console_more();page_lines=0;
  }
}
void console_reset(void) { column=serial_column=word_length=word_columns=word_continued=editing=0;serial_width=CONSOLE_COLUMNS; }
static void hdmi_put(int c) {
  if(c>=128&&!unicode_printable(c))c='?';
  if(c=='\n') { console_emit(c);column=0;edit_lines++;return; }
  if(c==8) {
    if(column) { column--;console_emit(c); }
    else if(console_previous_line())column=CONSOLE_COLUMNS-1;
    return;
  }
  if(unicode_printable(c)) {
    unsigned width=unicode_columns(c);if(!width)return;
    if(column+width>CONSOLE_COLUMNS)hdmi_put('\n');
    console_emit(c<128?c:'?');column++;
    if(width==2){console_emit(' ');column++;}
    return;
  }
  console_emit(c);
}
static void serial_put(int c) {
  if(c>=128&&!unicode_printable(c))c='?';
  if(c=='\n') { console_serial_emit(c);serial_column=0;edit_serial_lines++;if(!editing)console_page(1);return; }
  if(c==8) {
    if(serial_column){serial_column--;console_serial_emit(c);}
    else {console_serial_previous(serial_width);serial_column=serial_width-1;}
    return;
  }
  if(unicode_printable(c)) {
    unsigned width=unicode_columns(c);
    if(width&&serial_column+width>serial_width)serial_put('\n');
    uint8_t bytes[4];unsigned count=unicode_encode(c,bytes);
    for(unsigned i=0;i<count;i++)console_serial_emit(bytes[i]);
    serial_column+=width;return;
  }
  console_serial_emit(c);
}
void console_put(int c) { hdmi_put(c);serial_put(c); }
void console_edit_begin(unsigned initial_cells) {
  console_story_flush();
  edit_column=column;edit_serial_column=serial_column;
  edit_lines=edit_serial_lines=0;edit_initial=initial_cells;
  editing=1;
}
void console_edit_end(void){editing=0;}
void console_edit_clear(void) {
  unsigned cells=edit_initial+edit_lines*CONSOLE_COLUMNS+column-edit_column;
  while(cells--){hdmi_put(8);hdmi_put(' ');hdmi_put(8);}
  cells=edit_initial+edit_serial_lines*serial_width+serial_column-edit_serial_column;
  while(cells--){serial_put(8);serial_put(' ');serial_put(8);}
  console_edit_begin(0);
}
void console_story_flush(void) {
  if(!word_length)return;
  if(!word_continued&&column&&column+word_columns>CONSOLE_COLUMNS)hdmi_put('\n');
  if(!word_continued&&serial_column&&serial_column+word_columns>serial_width)serial_put('\n');
  for(unsigned i=0;i<word_length;i++){hdmi_put(word[i]);serial_put(word[i]);}
  word_length=word_columns=word_continued=0;
}
void console_story_put(int c) {
  if(c>32&&unicode_printable(c)) {
    // Bounded chunks also handle words longer than either display.
    if(word_length==CONSOLE_COLUMNS){console_story_flush();word_continued=1;}
    word[word_length++]=c;word_columns+=unicode_columns(c);return;
  }
  console_story_flush();
  if(c!=' '||column<CONSOLE_COLUMNS)hdmi_put(c);
  if(c!=' '||serial_column<serial_width)serial_put(c);
}
