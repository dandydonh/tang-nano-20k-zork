#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "platform.h"
#include "storage.h"
#include "screen.h"
#include "unicode.h"
#include "ps2.h"
static FILE *disk;
static long cut_after=-1,writes,attempts;
static FILE *ps2_input;
void platform_init(void){const char *p=getenv("ZORK_SD_IMAGE");disk=fopen(p?p:"assets/zork-fat.img","r+b");if(!disk){perror("SD image");exit(1);}const char *cut=getenv("ZORK_CUT_AFTER_WRITES");if(cut)cut_after=strtol(cut,NULL,10);setbuf(stdout,NULL);const char *cols=getenv("ZORK_TERM_COLUMNS");if(cols)console_width(strtoul(cols,NULL,10)-1);const char *rows=getenv("ZORK_PAGE_ROWS");if(rows)console_page_height(strtoul(rows,NULL,10));}
/* Opt-in position-1 driver for gameplay regressions.
 * Exercise the real menu: select position 1, confirm overwrites, cancel empty
 * restores. Dedicated UI tests leave this unset and supply every keystroke. */
static char menu_tail[80];
static unsigned menu_tail_count,menu_reply,menu_reply_pos,empty_restore;
static void menu_driver_emit(int c){
  const char *automatic=getenv("ZORK_TEST_DEFAULT_SLOT");if(!automatic||!*automatic)return;
  if(menu_tail_count==sizeof(menu_tail)-1){memmove(menu_tail,menu_tail+1,--menu_tail_count);}
  menu_tail[menu_tail_count++]=c;menu_tail[menu_tail_count]=0;
  if(strstr(menu_tail,"Slot is empty.")) {empty_restore=1;menu_tail_count=0;}
  if(strstr(menu_tail,"Slot number [Enter=1, 0=cancel]: ")) {
    menu_reply=empty_restore?2:1;menu_reply_pos=0;empty_restore=0;menu_tail_count=0;
  }
  if(strstr(menu_tail,"? [y/N]: ")) {menu_reply=3;menu_reply_pos=0;menu_tail_count=0;}
}
void console_serial_emit(int c){putchar(c);menu_driver_emit(c);}
void console_clear(void){fputs("\033[0m\033[2J\033[2;1H",stdout);}
void console_emit(int c){(void)c;}
int console_previous_line(void){return 1;}
void console_serial_previous(unsigned width){printf("\033[1A\033[%uC",width-1);}
void console_input_begin(void){}
int console_event_get(void){
  screen_flush();console_story_flush();console_page_reset();int c;
  if(menu_reply){c=menu_reply_pos?10:menu_reply==1?49:menu_reply==2?48:121;if(menu_reply_pos++)menu_reply=0;return c;}
  static unsigned opened;
  if(!opened){const char *p=getenv("ZORK_PS2_SCANS");if(p){ps2_input=fopen(p,"rb");if(!ps2_input)exit(98);}opened=1;}
  while(ps2_input){c=fgetc(ps2_input);if(c==EOF){fclose(ps2_input);ps2_input=0;break;}int key=ps2_key(c);if(key)return key;}
  c=getchar();if(c==EOF)exit(0);return c;
}
int console_get(void){return key_plain(console_event_get());}
void console_more(void){fputs("[MORE]",stdout);int c;do{c=getchar();if(c==EOF)exit(0);}while(c!=' '&&c!='\r'&&c!='\n');fputs("\b\b\b\b\b\b      \b\b\b\b\b\b",stdout);}
static char status_line[81];
void status_put(unsigned col,int c){if(col<80)status_line[col]=c;}
void status_flush(unsigned right_start){(void)right_start;fprintf(stderr,"%s\n",status_line);}
int sd_read_sector(uint32_t sector,uint8_t *p){const char *trace=getenv("ZORK_READ_LOG");if(trace){FILE *log=fopen(trace,"a");if(!log)exit(98);fprintf(log,"%u\n",sector);fclose(log);}return !fseek(disk,512L*sector,SEEK_SET)&&fread(p,1,512,disk)==512;}
int sd_write_sector(uint32_t sector,const uint8_t *p){
  if(!storage_writable(sector))return 0;
  if(cut_after>=0&&writes==cut_after)exit(99);
  const char *fail=getenv("ZORK_FAIL_WRITE"),*trace=getenv("ZORK_WRITE_LOG");
  if(getenv("ZORK_READ_ONLY"))return 0;
  if(trace){FILE *log=fopen(trace,"a");if(!log)exit(98);fprintf(log,"%u\n",sector);fclose(log);}
  if(fail&&attempts++==strtol(fail,NULL,10)) {
    const char *torn=getenv("ZORK_TORN_BYTES");
    if(torn){unsigned n=strtoul(torn,NULL,10);if(n>512)n=512;if(!fseek(disk,512L*sector,SEEK_SET))fwrite(p,1,n,disk);fflush(disk);}
    return 0;
  }
  int ok=!fseek(disk,512L*sector,SEEK_SET)&&fwrite(p,1,512,disk)==512;fflush(disk);if(ok)writes++;return ok;
}

static unsigned display_row,display_col;
void display_move(unsigned r,unsigned c){if(getenv("ZORK_SCREEN"))printf("\033[%u;%uH",r+1,c+1);else if(r!=display_row)putchar('\n');display_row=r;display_col=c;}
void display_cell(unsigned r,unsigned c,int ch,unsigned inverse){if(r!=display_row||c!=display_col)display_move(r,c);if(getenv("ZORK_SCREEN"))fputs(inverse?"\033[7m":"\033[0m",stdout);uint8_t bytes[4];unsigned n=unicode_encode(ch,bytes);for(unsigned i=0;i<n;i++)putchar(bytes[i]);menu_driver_emit(ch);display_row=r;display_col=c+unicode_columns(ch);}
void display_scroll(unsigned top){if(getenv("ZORK_SCREEN"))printf("\033[%u;32r\033[32;1H",top+1);putchar('\n');display_row=31;display_col=0;}
void display_clear(unsigned first,unsigned last){if(getenv("ZORK_SCREEN"))for(unsigned r=first;r<last;r++)printf("\033[%u;1H\033[2K",r+1);display_row=99;display_col=99;}
