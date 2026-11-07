/* Real disk writes, direct storage API, transient metadata authority checks. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "platform.h"
#include "storage.h"
static FILE *image;
static unsigned writes;
int sd_read_sector(uint32_t sector,uint8_t *data) {
  return !fseek(image,512L*sector,SEEK_SET)&&fread(data,1,512,image)==512;
}
int sd_write_sector(uint32_t sector,const uint8_t *data) {
  assert(storage_writable(sector));assert(!storage_writable(0));writes++;
  return !fseek(image,512L*sector,SEEK_SET)&&fwrite(data,1,512,image)==512&&!fflush(image);
}
void console_put(int c){(void)c;}
unsigned console_menu_rows(void){return 32;}
unsigned console_menu_columns(void){return 79;}
void console_menu_reset(void){}
void console_clear(void){}
void console_page_reset(void){}
int console_get(void){abort();}
int main(int argc,char **argv) {
  assert(argc==2);image=fopen(argv[1],"r+b");assert(image);
  uint8_t data[512];assert(storage_init());assert(storage_game_slots()==5);
  for(unsigned slot=0;slot<5;slot++) {
    assert(storage_select_save(slot));
    for(unsigned bank=1;bank<=2;bank++) {
      memset(data,0xa5,sizeof data);assert(storage_read(bank,0,data));
      for(unsigned j=0;j<512;j++)assert(!data[j]);
    }
  }
  assert(!writes);
  for(unsigned sector=0;sector<16384;sector++)assert(!storage_writable(sector));
  assert(!storage_write(2,0,data)&&!storage_write(0,256,data));
  data[0]=0xa5;assert(storage_write(0,0,data));
  assert(storage_read(STORAGE_SAVE_A,0,data)&&data[0]==0xa5);
  unsigned count=0;
  for(unsigned sector=0;sector<16384;sector++)count+=storage_writable(sector)!=0;
  assert(count==512); /* Only chosen A/B snapshots, no FAT/directory/index writes. */
  assert(!storage_writable(0)&&!storage_writable(UINT32_MAX));
  assert(storage_init());count=0;
  for(unsigned sector=0;sector<16384;sector++)count+=storage_writable(sector)!=0;
  assert(count==512&&storage_select_save(4));
  assert(storage_read(STORAGE_SAVE_A,0,data)&&data[0]==0xa5);
  fclose(image);puts("PASS direct API: lazy zero reads, five positions, revoked metadata writes, exact pair permissions and remount");
}
