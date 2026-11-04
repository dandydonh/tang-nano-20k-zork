/* Explicit transcript wrapping, independent of the terminal's autowrap mode.
 * Leave the final column free on an 80-column terminal to avoid pending-wrap
 * cursor behavior during status updates and input editing. */
#include "platform.h"
static unsigned column,word_length;
static char word[CONSOLE_COLUMNS];
void console_reset(void) { column=word_length=0; }
void console_put(int c) {
  if(c=='\n') { console_emit(c);column=0;return; }
  if(c==8) {
    if(column) { column--;console_emit(c); }
    else if(console_previous_line())column=CONSOLE_COLUMNS-1;
    return;
  }
  if(c>=32&&c<=126) {
    if(column==CONSOLE_COLUMNS) { console_emit('\n');column=0; }
    console_emit(c);column++;return;
  }
  console_emit(c);
}
void console_story_flush(void) {
  if(!word_length)return;
  if(column&&column+word_length>CONSOLE_COLUMNS)console_put('\n');
  for(unsigned i=0;i<word_length;i++)console_put(word[i]);
  word_length=0;
}
void console_story_put(int c) {
  if(c>=33&&c<=126) {
    // Split an overlong word into bounded chunks without dropping characters.
    if(word_length==CONSOLE_COLUMNS)console_story_flush();
    word[word_length++]=c;return;
  }
  console_story_flush();
  if(c!=' '||column<CONSOLE_COLUMNS)console_put(c);
}
