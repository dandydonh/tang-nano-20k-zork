/* Drive the same formatter used by the board, retaining actual UART CRLF. */
#include <stdio.h>
#include <string.h>
#include "platform.h"
void console_emit(int c) { if(c=='\n')putchar('\r');putchar(c); }
int console_previous_line(void) { fputs("\033[1A\033[78C",stdout);return 1; }
void console_more(void) { fputs("[MORE]",stdout); }
int main(int argc,char **argv) {
  int raw=argc>1&&!strcmp(argv[1],"raw");
  int edit=argc>1&&!strcmp(argv[1],"edit");
  console_reset();
  if(edit)for(const char *p="Input> ";*p;p++)console_put(*p);
  int c;
  while((c=getchar())!=EOF) {
    if(edit&&c==8) { console_put(8);console_put(' ');console_put(8); }
    else if(raw||edit)console_put(c);
    else console_story_put(c);
  }
  console_story_flush();return 0;
}
