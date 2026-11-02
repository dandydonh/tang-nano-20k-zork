#include <stdio.h>
#include <stdlib.h>
#include "platform.h"
static FILE *disk;
void platform_init(void){const char *p=getenv("ZORK_SD_IMAGE");disk=fopen(p?p:"assets/zork-sd.img","r+b");if(!disk){perror("SD image");exit(1);}setbuf(stdout,NULL);}
void console_put(int c){putchar(c);}
int console_get(void){int c=getchar();if(c==EOF)exit(0);return c;}
static char status_line[81];
void status_put(unsigned col,int c){if(col<80)status_line[col]=c;}
void status_flush(unsigned right_start){(void)right_start;fprintf(stderr,"%s\n",status_line);}
int disk_read(uint32_t sector,uint8_t *p){return !fseek(disk,512L*sector,SEEK_SET)&&fread(p,1,512,disk)==512;}
int disk_write(uint32_t sector,const uint8_t *p){int ok=!fseek(disk,512L*sector,SEEK_SET)&&fwrite(p,1,512,disk)==512;fflush(disk);return ok;}
