#include <stdio.h>
#include <stdlib.h>
#include "platform.h"
#include "storage.h"
static FILE *disk;
static long cut_after=-1,writes;
void platform_init(void){const char *p=getenv("ZORK_SD_IMAGE");disk=fopen(p?p:"assets/zork-fat.img","r+b");if(!disk){perror("SD image");exit(1);}const char *cut=getenv("ZORK_CUT_AFTER_WRITES");if(cut)cut_after=strtol(cut,NULL,10);setbuf(stdout,NULL);}
void console_emit(int c){putchar(c);}
int console_previous_line(void){fputs("\033[1A\033[78C",stdout);return 1;}
int console_get(void){console_story_flush();int c=getchar();if(c==EOF)exit(0);return c;}
static char status_line[81];
void status_put(unsigned col,int c){if(col<80)status_line[col]=c;}
void status_flush(unsigned right_start){(void)right_start;fprintf(stderr,"%s\n",status_line);}
int sd_read_sector(uint32_t sector,uint8_t *p){return !fseek(disk,512L*sector,SEEK_SET)&&fread(p,1,512,disk)==512;}
int sd_write_sector(uint32_t sector,const uint8_t *p){if(!storage_writable(sector))return 0;if(cut_after>=0&&writes==cut_after)exit(99);int ok=!fseek(disk,512L*sector,SEEK_SET)&&fwrite(p,1,512,disk)==512;fflush(disk);if(ok)writes++;return ok;}
