/* Raw set-2 make/break tests; no UART decoder or interpreter mocks. */
#include <assert.h>
#include <stdio.h>
#include "platform.h"
#include "ps2.h"
static const char normal[]="`1234567890-=qwertyuiop[]\\asdfghjkl;'zxcvbnm,./ ";
static const char shifted[]="~!@#$%^&*()_+QWERTYUIOP{}|ASDFGHJKL:\"ZXCVBNM<>? ";
static const unsigned scans[]={0x0e,0x16,0x1e,0x26,0x25,0x2e,0x36,0x3d,0x3e,0x46,0x45,0x4e,0x55,
 0x15,0x1d,0x24,0x2d,0x2c,0x35,0x3c,0x43,0x44,0x4d,0x54,0x5b,0x5d,
 0x1c,0x1b,0x23,0x2b,0x34,0x33,0x3b,0x42,0x4b,0x4c,0x52,
 0x1a,0x22,0x21,0x2a,0x32,0x31,0x3a,0x41,0x49,0x4a,0x29};
static int event(unsigned c){return KEY_UNICODE_BASE+c;}
static void press(unsigned scan,unsigned ext,int expected){if(ext)assert(!ps2_key(0xe0));assert(ps2_key(scan)==expected);}
static void release(unsigned scan,unsigned ext){if(ext)assert(!ps2_key(0xe0));assert(!ps2_key(0xf0));assert(!ps2_key(scan));}
static void tap(unsigned scan,unsigned ext,int expected){press(scan,ext,expected);release(scan,ext);}
static void text_key(unsigned c,int expected){
  unsigned i=0,shift=0;
  for(;normal[i];i++)if(normal[i]==(int)c)break;
  if(!normal[i]){for(i=0;shifted[i];i++)if(shifted[i]==(int)c)break;assert(shifted[i]);shift=1;}
  if(shift)press(0x12,0,0);
  tap(scans[i],0,expected);
  if(shift)release(0x12,0);
}
static void compose(unsigned a,unsigned b,unsigned c){tap(0x11,1,0);text_key(a,0);text_key(b,event(c));}
static void start_hex(void){press(0x14,0,0);press(0x12,0,0);tap(0x3c,0,0);release(0x12,0);release(0x14,0);}
static void hex_text(const char *p){while(*p)text_key(*p++,0);}
static void hex(const char *p,unsigned c){start_hex();hex_text(p);tap(0x5a,0,c?event(c):0);}
int main(void){
  assert(sizeof(normal)==sizeof(shifted));assert(sizeof(scans)/sizeof(scans[0])==sizeof(normal)-1);
  ps2_reset();
  for(unsigned i=0;normal[i];i++){text_key(normal[i],event(normal[i]));text_key(shifted[i],event(shifted[i]));}
  press(0x24,0,event('e'));press(0x24,0,event('e'));release(0x24,0);
  press(0x58,0,0);press(0x58,0,0);text_key('e',event('E'));release(0x58,0);
  press(0x59,0,0);text_key('e',event('e'));release(0x59,0);tap(0x58,0,0);
  tap(0x75,1,KEY_UP);tap(0x72,1,KEY_DOWN);tap(0x5a,1,event(13));
  compose('\'','e',0xe9);compose('"','u',0xfc);compose('~','n',0xf1);compose('^','O',0xd4);
  compose('`','a',0xe0);compose(',','c',0xe7);compose('o','A',0xc5);compose('/','o',0xf8);
  compose('a','e',0xe6);compose('O','E',0x152);compose('s','s',0xdf);compose('t','h',0xfe);
  compose('D','H',0xd0);compose('L','-',0xa3);compose('<','<',0xab);compose('?','?',0xbf);
  compose('e','=',0x20ac);compose('-','-',0x2013);
  tap(0x2f,1,0);text_key('\'',0);text_key('E',event(0xc9));
  tap(0x11,1,0);text_key('\'',0);tap(0x66,0,0);text_key('~',0);text_key('n',event(0xf1));
  tap(0x11,1,0);text_key('x',0);text_key('z',0);text_key('e',event('e'));
  tap(0x11,1,0);text_key('\'',0);tap(0x76,0,0);text_key('e',event('e'));
  /* Consumed entry keys cannot leak via typematic after completion. */
  tap(0x11,1,0);press(0x52,0,0);press(0x52,0,0);press(0x24,0,event(0xe9));
  press(0x24,0,0);press(0x52,0,0);release(0x24,0);release(0x52,0);text_key('e',event('e'));
  hex("00e9",0xe9);hex("0100",0x100);hex("754C",0x754c);hex("1f680",0x1f680);hex("10fffd",0x10fffd);
  const char *bad[]={"","0","0000","001f","007f","009b","d800","dfff","fffe","ffff","110000","ffffff","1234567","g"};
  for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++)hex(bad[i],0);
  start_hex();hex_text("0ff");tap(0x66,0,0);hex_text("a");tap(0x29,0,event(0xfa));
  start_hex();hex_text("1234567");tap(0x66,0,0);hex_text("e9");tap(0x5a,0,event(0xe9));
  start_hex();hex_text("e9");tap(0x76,0,0);text_key('x',event('x'));
  start_hex();hex_text("e9");press(0x5a,0,event(0xe9));press(0x5a,0,0);release(0x5a,0);tap(0x5a,0,event(13));
  /* Chord repeats, both modifier sides and chord-held digit entry. */
  press(0x14,1,0);press(0x59,0,0);press(0x3c,0,0);press(0x3c,0,0);
  tap(0x16,0,0);tap(0x45,0,0);tap(0x45,0,0);tap(0x5a,0,event(0x100));
  release(0x3c,0);release(0x59,0);release(0x14,1);
  const unsigned pause[]={0xe1,0x14,0x77,0xe1,0xf0,0x14,0xf0,0x77};
  const unsigned printscreen[]={0xe0,0x12,0xe0,0x7c,0xe0,0xf0,0x7c,0xe0,0xf0,0x12};
  for(unsigned i=0;i<8;i++)assert(!ps2_key(pause[i]));
  for(unsigned i=0;i<10;i++)assert(!ps2_key(printscreen[i]));
  text_key('u',event('u'));
  start_hex();hex_text("e9");assert(!ps2_key(0xaa));text_key('e',event('e'));
  tap(0x11,1,0);assert(!ps2_key(0xff));text_key('e',event('e'));
  puts("PASS PS/2: US layout/modifiers, compose, hex/BMP/supplementary entry, cancellation, overflow, typematic, Pause/PrintScreen and reset");
}
