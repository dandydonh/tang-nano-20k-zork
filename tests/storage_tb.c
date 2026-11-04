/* Exercise storage bounds and low-level write authorization independently of VM. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "platform.h"
#include "storage.h"
static FILE *image;
static unsigned reads, writes;
static uint32_t fail_sector=UINT32_MAX;
int sd_read_sector(uint32_t sector, uint8_t *data) {
  assert(++reads<20000); /* A corrupt chain must terminate. */
  if(sector==fail_sector)return 0;
  return !fseek(image,512L*sector,SEEK_SET)&&fread(data,1,512,image)==512;
}
int sd_write_sector(uint32_t sector, const uint8_t *data) {
  (void)data;
  assert(storage_writable(sector));writes++;return 1;
}
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
    unsigned size=file?64:180;
    for(unsigned sector=0;sector<size;sector++)assert(storage_read(file,sector,data));
    assert(!storage_read(file,size,data));
  }
  assert(!storage_read(3,0,data));
  assert(!storage_read(UINT32_MAX,0,data));
  assert(!storage_write(0,64,data));
  assert(!storage_write(2,0,data));
  assert(!storage_write(UINT32_MAX,0,data));
  assert(!storage_writable(0)&&!storage_writable(UINT32_MAX));
  for(unsigned bank=0;bank<2;bank++)
    for(unsigned sector=0;sector<64;sector++)assert(storage_write(bank,sector,data));
  assert(writes==128);
  /* A failed remount must revoke every previous write authorization. */
  fail_sector=0;
  assert(!storage_init());
  assert(!storage_write(0,0,data));
  assert(writes==128);
  fclose(image);
  puts("PASS storage bounds, write authorization and failed-remount revocation");
  return 0;
}
