#include <stdio.h>
#include <stdlib.h>
#include "platform.h"
#include "storage.h"
#include "screen.h"
static FILE *disk;
static long cut_after=-1,writes;
void platform_init(void){const char *p=getenv("ZORK_SD_IMAGE");disk=fopen(p?p:"assets/zork-fat.img","r+b");if(!disk){perror("SD image");exit(1);}const char *cut=getenv("ZORK_CUT_AFTER_WRITES");if(cut)cut_after=strtol(cut,NULL,10);setbuf(stdout,NULL);const char *rows=getenv("ZORK_PAGE_ROWS");if(rows)console_page_height(strtoul(rows,NULL,10));}
void console_emit(int c){putchar(c);}
int console_previous_line(void){fputs("\033[1A\033[78C",stdout);return 1;}
int console_get(void){screen_flush();console_story_flush();console_page_reset();int c=getchar();if(c==EOF)exit(0);return c;}
void console_more(void){fputs("[MORE]",stdout);int c;do{c=getchar();if(c==EOF)exit(0);}while(c!=' '&&c!='\r'&&c!='\n');fputs("\b\b\b\b\b\b      \b\b\b\b\b\b",stdout);}
static char status_line[81];
void status_put(unsigned col,int c){if(col<80)status_line[col]=c;}
void status_flush(unsigned right_start){(void)right_start;fprintf(stderr,"%s\n",status_line);}
int sd_read_sector(uint32_t sector,uint8_t *p){return !fseek(disk,512L*sector,SEEK_SET)&&fread(p,1,512,disk)==512;}
int sd_write_sector(uint32_t sector,const uint8_t *p){if(!storage_writable(sector))return 0;if(cut_after>=0&&writes==cut_after)exit(99);int ok=!fseek(disk,512L*sector,SEEK_SET)&&fwrite(p,1,512,disk)==512;fflush(disk);if(ok)writes++;return ok;}

static unsigned display_row,display_col;
void display_move(unsigned r,unsigned c){if(getenv("ZORK_SCREEN"))printf("\033[%u;%uH",r+1,c+1);else if(r!=display_row)putchar('\n');display_row=r;display_col=c;}
void display_cell(unsigned r,unsigned c,int ch,unsigned inverse){if(r!=display_row||c!=display_col)display_move(r,c);if(getenv("ZORK_SCREEN"))fputs(inverse?"\033[7m":"\033[0m",stdout);putchar(ch);display_row=r;display_col=c+1;}
void display_scroll(unsigned top){if(getenv("ZORK_SCREEN"))printf("\033[%u;32r\033[32;1H",top+1);putchar('\n');display_row=31;display_col=0;}
void display_clear(unsigned first,unsigned last){if(getenv("ZORK_SCREEN"))for(unsigned r=first;r<last;r++)printf("\033[%u;1H\033[2K",r+1);display_row=99;display_col=99;}
