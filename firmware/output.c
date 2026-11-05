/* HDMI and UART share words, but wrap and count columns independently. */
#include "platform.h"
static unsigned column,serial_column,serial_width=CONSOLE_COLUMNS,word_length,word_continued;
static char word[CONSOLE_COLUMNS];
static unsigned page_height,page_lines;
void console_page_height(unsigned rows) { page_height=rows;page_lines=0; }
void console_page_reset(void) { page_lines=0; }
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
void console_reset(void) { column=serial_column=word_length=word_continued=0;serial_width=CONSOLE_COLUMNS; }
static void hdmi_put(int c) {
  if(c=='\n') { console_emit(c);column=0;return; }
  if(c==8) {
    if(column) { column--;console_emit(c); }
    else if(console_previous_line())column=CONSOLE_COLUMNS-1;
    return;
  }
  if(c>=32&&c<=126) {
    if(column==CONSOLE_COLUMNS)hdmi_put('\n');
    console_emit(c);column++;return;
  }
  console_emit(c);
}
static void serial_put(int c) {
  if(c=='\n') { console_serial_emit(c);serial_column=0;console_page(1);return; }
  if(c==8) {
    if(serial_column){serial_column--;console_serial_emit(c);}
    else {console_serial_previous(serial_width);serial_column=serial_width-1;}
    return;
  }
  if(c>=32&&c<=126) {
    if(serial_column==serial_width)serial_put('\n');
    console_serial_emit(c);serial_column++;return;
  }
  console_serial_emit(c);
}
void console_put(int c) { hdmi_put(c);serial_put(c); }
void console_story_flush(void) {
  if(!word_length)return;
  if(!word_continued&&column&&column+word_length>CONSOLE_COLUMNS)hdmi_put('\n');
  if(!word_continued&&serial_column&&serial_column+word_length>serial_width)serial_put('\n');
  for(unsigned i=0;i<word_length;i++){hdmi_put(word[i]);serial_put(word[i]);}
  word_length=word_continued=0;
}
void console_story_put(int c) {
  if(c>=33&&c<=126) {
    // Bounded chunks also handle words longer than either display.
    if(word_length==CONSOLE_COLUMNS){console_story_flush();word_continued=1;}
    word[word_length++]=c;return;
  }
  console_story_flush();
  if(c!=' '||column<CONSOLE_COLUMNS)hdmi_put(c);
  if(c!=' '||serial_column<serial_width)serial_put(c);
}
