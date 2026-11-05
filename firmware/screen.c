#include "screen.h"
struct screen_state screen;
void screen_reset(void) {
  for(unsigned i=0;i<sizeof(screen);i++)((uint8_t*)&screen)[i]=0;
  screen.font=1;screen.buffer=1;
  display_clear(0,32);display_move(0,0);
}
void screen_split(unsigned lines) {
  screen_flush();if(lines>31)lines=31;screen.split=lines;
  if(screen.row[0]<lines)screen.row[0]=lines;
  if(screen.row[1]>=lines)screen.row[1]=0;
}
void screen_window(unsigned window) {
  screen_flush();if(window>1)fatal("invalid window");screen.window=window;
  if(window)screen.row[1]=screen.col[1]=0;
  display_move(screen.row[window],screen.col[window]);
}
void screen_cursor(unsigned row,unsigned col) {
  if(!screen.window)return;
  screen_flush();if(!row||!col||col>CONSOLE_COLUMNS||row>32)fatal("invalid cursor");
  unsigned w=screen.window;
  if(w&&row>screen.split)screen_split(row);
  screen.row[w]=row-1;screen.col[w]=col-1;display_move(row-1,col-1);
}
static void screen_char(int c) {
  unsigned w=screen.window,r=screen.row[w],col=screen.col[w];
  if(c==8){if(col)col--;else if(!w&&r>screen.split){r--;col=CONSOLE_COLUMNS-1;}screen.row[w]=r;screen.col[w]=col;display_move(r,col);return;}
  if(c==13)c='\n';
  if(screen.pc_graphics){if(c>=179&&c<=218)c=c==179?'|':c==186?'#':c==196?'-':c==205?'=':'+';else if(c==24)c='^';else if(c==25)c='v';}
  if(c!='\n'&&(c<32||c>126)){if(c==9||c==11)c=' ';else if(c>=155)c='?';else return;}
  if(c=='\n'||col==CONSOLE_COLUMNS) {
    col=0;r++;
    if(w){if(r>=screen.split)r=0;}
    else if(r==32){display_scroll(screen.split);r=31;}
    display_move(r,col);
    if(!w)console_page(screen.split);
    if(c=='\n'){screen.row[w]=r;screen.col[w]=col;return;}
  }
  if(!w||screen.split)display_cell(r,col,c,screen.style&1);
  screen.row[w]=r;screen.col[w]=col+1;
}
void screen_flush(void) {
  unsigned len=screen.word_length;if(!len)return;
  screen.word_length=0;
  if(screen.col[0]&&screen.col[0]+len>CONSOLE_COLUMNS)screen_char('\n');
  for(unsigned i=0;i<len;i++)screen_char(screen.word[i]);
}
void screen_put(int c) {
  if(screen.buffer&&!screen.window&&c>=33&&c<=126){
    if(screen.word_length==CONSOLE_COLUMNS)screen_flush();
    screen.word[screen.word_length++]=c;return;
  }
  screen_flush();screen_char(c);
}
void screen_erase(int window) {
  screen_flush();
  if(window==-1){screen_split(0);screen.window=0;display_clear(0,32);screen.row[0]=0;screen.col[0]=0;}
  else if(window==-2)display_clear(0,32);
  else if(window==0){display_clear(screen.split,32);screen.row[0]=screen.split;screen.col[0]=0;}
  else if(window==1){display_clear(0,screen.split);screen.row[1]=screen.col[1]=0;}
  else fatal("invalid erase window");
  display_move(screen.row[screen.window],screen.col[screen.window]);
}
void screen_erase_line(void) {
  screen_flush();
  unsigned w=screen.window;
  for(unsigned c=screen.col[w];c<CONSOLE_COLUMNS;c++)display_cell(screen.row[w],c,' ',0);
  display_move(screen.row[w],screen.col[w]);
}
void screen_style(unsigned style) { screen_flush();screen.style=style?screen.style|style:0; }
