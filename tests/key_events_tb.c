/* Exercise the actual interpreter decoder with interleaved input sources. */
#include <assert.h>
#include <stdio.h>
#define main interpreter_main
#include "../firmware/zmachine.c"
#undef main
static const unsigned events[]={
  0xc3,KEY_UNICODE_BASE+'x',0xa9,
  0xc4,KEY_UP,KEY_UNICODE_BASE+0x754c,0x80,
  0xf0,KEY_UNICODE_BASE+0x100,0x9f,0x98,0x80,
  0xed,0xa0,0x80,KEY_UNICODE_BASE+0xe9,'X',
  0xc3,13,KEY_UNICODE_BASE+13
};
static unsigned next;
int console_event_get(void){assert(next<sizeof(events)/sizeof(events[0]));return events[next++];}
int main(void){
  const unsigned expected[]={'x',0xe9,KEY_UP,0x754c,0x100,0x100,0x1f600,0xe9,'X',13,13};
  for(unsigned i=0;i<sizeof(expected)/sizeof(expected[0]);i++)assert((unsigned)unicode_key()==expected[i]);
  assert(next==sizeof(events)/sizeof(events[0]));
  puts("PASS input sources: atomic PS/2 Unicode/ASCII/events interleave with partial UART UTF-8; malformed UART resynchronizes");
}
