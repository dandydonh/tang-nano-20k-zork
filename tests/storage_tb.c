/* Exercise storage bounds and low-level write authorization independently of VM. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "platform.h"
#include "storage.h"
static FILE *image;
static unsigned reads, writes;
static uint32_t last_write;
static uint32_t fail_sector=UINT32_MAX;
int sd_read_sector(uint32_t sector, uint8_t *data) {
  assert(++reads<20000); /* A corrupt chain must terminate. */
  if(sector==fail_sector)return 0;
  return !fseek(image,512L*sector,SEEK_SET)&&fread(data,1,512,image)==512;
}
int sd_write_sector(uint32_t sector, const uint8_t *data) {
  (void)data;
  assert(storage_writable(sector));last_write=sector;writes++;return 1;
}
void console_put(int c){(void)c;}
unsigned console_menu_rows(void){return 32;}
unsigned console_menu_columns(void){return 79;}
void console_menu_reset(void){}
void console_clear(void){}
void console_page_reset(void){}
int console_get(void){abort();}
int main(int argc, char **argv) {
  assert(argc==2 || argc==3);
  image=fopen(argv[1],"rb");assert(image);
  if(argc==3)fail_sector=(uint32_t)strtoul(argv[2],NULL,0);
  uint8_t data[512]={0};
  assert(!storage_writable(0));
  assert(!storage_read(STORAGE_STORY,0,data));
  assert(!storage_write(0,0,data));
  if(!storage_init()) {
    assert(!storage_write(0,0,data)&&!storage_writable(0)&&!writes);
    return 2;
  }
  for(unsigned file=0;file<3;file++) {
    unsigned size=file?STORAGE_BANK_SECTORS:(storage_story_size()+511)/512;
    if(file&&!storage_saves_available())break;
    for(unsigned sector=0;sector<size;sector++)assert(storage_read(file,sector,data));
    assert(!storage_read(file,size,data));
  }
  if(!storage_saves_available()){assert(!storage_write(0,0,data));fclose(image);return 3;}
  assert(!storage_read(3,0,data));
  assert(!storage_read(UINT32_MAX,0,data));
  assert(!storage_write(0,STORAGE_BANK_SECTORS,data));
  assert(!storage_write(2,0,data));
  assert(!storage_write(UINT32_MAX,0,data));
  assert(!storage_writable(0)&&!storage_writable(UINT32_MAX));
  unsigned slots=storage_game_slots();assert(slots>=1&&slots<=STORAGE_GAME_SLOTS);
  assert(!storage_select_save(slots)&&!storage_select_save(UINT32_MAX));
  for(unsigned slot=0;slot<slots;slot++) {
    uint32_t previous=last_write;
    assert(storage_select_save(slot));
    if(slot)assert(!storage_writable(previous));
    for(unsigned bank=0;bank<2;bank++)
      for(unsigned sector=0;sector<STORAGE_BANK_SECTORS;sector++)assert(storage_write(bank,sector,data));
  }
  assert(writes==slots*2*STORAGE_BANK_SECTORS);
  /* A failed remount must revoke every previous write authorization. */
  fail_sector=0;
  assert(!storage_init());
  assert(!storage_write(0,0,data));
  assert(writes==slots*2*STORAGE_BANK_SECTORS);
  fclose(image);
  puts("PASS storage bounds, write authorization and failed-remount revocation");
  return 0;
}
