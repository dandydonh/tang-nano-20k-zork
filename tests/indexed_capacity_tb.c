/* Allocate all 1000 owners without depending on the separate menu capacity. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "platform.h"
#include "storage.h"
static FILE *image;
static uint32_t story_sector;
static unsigned reads,writes,max_reads;
int sd_read_sector(uint32_t sector,uint8_t *data) {
  reads++;return !fseek(image,512L*sector,SEEK_SET)&&fread(data,1,512,image)==512;
}
int sd_write_sector(uint32_t sector,const uint8_t *data) {
  assert(storage_writable(sector));writes++;
  return !fseek(image,512L*sector,SEEK_SET)&&fwrite(data,1,512,image)==512&&!fflush(image);
}
void console_put(int c){(void)c;}
unsigned console_menu_rows(void){return 32;}
unsigned console_menu_columns(void){return 79;}
void console_menu_reset(void){}
void console_clear(void){}
void console_page_reset(void){}
int console_get(void){abort();}
static void mount_story(unsigned owner) {
  uint8_t header[512];assert(sd_read_sector(story_sector,header));
  header[2]=owner>>8;header[3]=owner;
  char serial[7];snprintf(serial,sizeof serial,"%06u",owner);
  memcpy(header+18,serial,6);
  assert(!fseek(image,512L*story_sector,SEEK_SET));assert(fwrite(header,1,512,image)==512);fflush(image);
  reads=0;assert(storage_init());
  if(reads>max_reads)max_reads=reads;
  assert(reads<600); /* FAT allocation walk + 128 metadata sectors, no snapshot scan. */
}
int main(int argc,char **argv) {
  assert(argc==3);image=fopen(argv[1],"r+b");assert(image);
  story_sector=(uint32_t)strtoul(argv[2],0,0);
  uint8_t data[512]={0},readback[512];
  for(unsigned owner=1;owner<=1000;owner++) {
    unsigned before=writes;
    mount_story(owner);assert(writes==before&&storage_saves_available());
    assert(storage_game_slots()==5&&storage_select_save(4));
    assert(!storage_writable(0)&&!storage_writable(story_sector));
    assert(!storage_write(2,0,data)&&!storage_write(0,STORAGE_BANK_SECTORS,data));
    memset(data,0,sizeof data);data[0]=owner;data[1]=owner>>8;
    memcpy(data+16,storage_story_id(),STORAGE_ID_BYTES);
    assert(storage_write(0,0,data));assert(writes==before+3);
    assert(!storage_writable(story_sector+64)&&!storage_writable(story_sector+66));
    assert(storage_read(STORAGE_SAVE_A,0,readback)&&!memcmp(data,readback,512));
  }
  memset(data,0xa5,sizeof data);
  assert(storage_write(1,STORAGE_BANK_SECTORS-1,data));
  assert(storage_read(STORAGE_SAVE_B,STORAGE_BANK_SECTORS-1,readback)&&!memcmp(data,readback,512));
  mount_story(1001);assert(!storage_saves_available());
  assert(!storage_write(0,0,data)&&writes==3001);
  for(unsigned owner=1000;owner;owner--) {
    mount_story(owner);assert(storage_saves_available()&&storage_select_save(4));
    assert(storage_read(STORAGE_SAVE_A,0,readback));
    assert(readback[0]==(owner&255)&&readback[1]==(owner>>8));
  }
  assert(writes==3001);fclose(image);
  printf("PASS all 1000 indexed save owners, final position, owner 1001 refusal, reset/readback and write isolation; max mount reads %u\n",max_reads);
}
