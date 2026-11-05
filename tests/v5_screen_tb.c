#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "screen.h"
static unsigned char cells[32][80];
static unsigned cursor_row,cursor_col;
void console_page(unsigned top){(void)top;}
void fatal(const char *s){fprintf(stderr,"%s\n",s);exit(1);}
void display_move(unsigned r,unsigned c){assert(r<32&&c<80);cursor_row=r;cursor_col=c;}
void display_cell(unsigned r,unsigned c,int ch,unsigned inverse){assert(r<32&&c<79);cells[r][c]=ch|(inverse?128:0);}
void display_scroll(unsigned top){assert(top<32);memmove(cells[top],cells[top+1],(31-top)*80);memset(cells[31],' ',80);}
void display_clear(unsigned first,unsigned last){assert(first<=last&&last<=32);memset(cells[first],' ',(last-first)*80);}
static void text(const char *p){while(*p)screen_put(*p++);screen_flush();}
int main(void){
  screen_reset();assert(cursor_row==0&&cursor_col==0);
  screen_split(2);screen_window(1);screen_cursor(1,2);screen_style(1);text("STATUS");
  assert(cells[0][1]==('S'|128));screen_style(0);screen_window(0);
  for(unsigned i=0;i<45;i++)text("a long lower window paragraph must scroll without losing the upper window\n");
  assert(cells[0][1]==('S'|128)&&cells[31][79]==' ');
  text("one ");screen_window(1);screen_cursor(2,3);text("two");screen_window(0);text("three");
  assert(memcmp(&cells[31][0],"one three",9)==0);
  assert(memcmp(&cells[1][2],"two",3)==0);
  screen_window(1);screen_cursor(2,3);screen_erase_line();assert(cells[1][2]==' ');
  screen_window(0);screen_erase(0);assert(cells[0][1]==('S'|128));
  for(unsigned i=0;i<90;i++)screen_put('x');screen_flush();
  for(unsigned i=0;i<90;i++){screen_put(8);screen_put(' ');screen_put(8);}
  text("look");assert(memcmp(cells[2],"look",4)==0);
  screen_erase(-1);assert(screen.split==0&&screen.window==0&&cursor_row==0);
  screen.pc_graphics=1;screen_put(179);screen_put(196);screen_put(218);screen_flush();
  assert(memcmp(cells[0],"|-+",3)==0);
  puts("PASS V5 screen: inverse status, independent cursors, lower scrolling, erase, wrap/backspace, ASCII graphics");
}
