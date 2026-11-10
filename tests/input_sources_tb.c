/* Run the board's input arbiter and decoders with all three sources active. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
static const unsigned *inputs[3];
static uint32_t value;
static unsigned reads;
static volatile uint32_t *test_register(unsigned offset) {
  assert(++reads<10000); /* A missing event must fail instead of hanging. */
  unsigned source=offset==0?0:offset==16?1:2;
  assert(offset==0||offset==16||offset==28);
  value=0;
  if(inputs[source]&&*inputs[source])value=256|*inputs[source]++;
  return &value;
}
#define REG(n) (*test_register(n))
#include "../firmware/platform.c"
static void setup(const unsigned *uart,const unsigned *ps2,const unsigned *usb) {
  inputs[0]=uart;inputs[1]=ps2;inputs[2]=usb;reads=0;ps2_reset();
  pending_count=pending_read=report_length=0;
}
static int event(unsigned c){return KEY_UNICODE_BASE+c;}
static void pair(int a,int b) {
  int first=raw_console_event_get(),second=raw_console_event_get();
  assert((first==a&&second==b)||(first==b&&second==a));
}
int main(void) {
  const unsigned extended[]={0xe0,0},a[]={0x1c,0},up[]={0x75,0};
  setup(0,extended,a);
  assert(raw_console_event_get()==event('a'));
  inputs[1]=up;assert(raw_console_event_get()==KEY_UP);

  const unsigned shift[]={0x12,0},usb_reset[]={0xaa,0x1c,0};
  setup(0,shift,usb_reset);
  assert(raw_console_event_get()==event('a'));
  inputs[1]=a;assert(raw_console_event_get()==event('A'));

  /* Interleave break prefixes with the other keyboard's ordinary input. */
  const unsigned release_shift[]={0xf0,0x12,0x1c,0};
  const unsigned usb_shift[]={0x12,0x32,0};
  inputs[1]=release_shift;inputs[2]=usb_shift;
  pair(event('a'),event('B'));

  /* Compose and hexadecimal entry must keep separate partial state. */
  const unsigned compose[]={0xe0,0x11,0xe0,0xf0,0x11,0x52,0xf0,0x52,0x24,0};
  const unsigned hex[]={0x14,0x12,0x3c,0xf0,0x3c,0xf0,0x12,0xf0,0x14,0x16,0x45,0xf0,0x45,0x45,0x5a,0};
  setup(0,compose,hex);pair(event(0xe9),event(0x100));

  const unsigned caps_a[]={0x58,0x1c,0};
  setup(0,caps_a,a);pair(event('A'),event('a'));

  /* A busy terminal cannot starve either keyboard. Serial remains raw UTF-8. */
  unsigned uart[101];for(unsigned i=0;i<100;i++)uart[i]='x';uart[100]=0;
  const unsigned ps2_b[]={0x32,0};
  setup(uart,a,ps2_b);
  unsigned seen=0;
  for(unsigned i=0;i<6&&seen!=3;i++) {
    int key=raw_console_event_get();
    if(key==event('a'))seen|=1;else if(key==event('b'))seen|=2;else assert(key=='x');
  }
  assert(seen==3);
  const unsigned utf8[]={0xc3,0xa9,13,10,'z',0};
  setup(utf8,0,0);
  assert(raw_console_event_get()==0xc3);assert(raw_console_event_get()==0xa9);
  assert(raw_console_event_get()==13);assert(raw_console_event_get()=='z');
  puts("PASS combined input: independent prefixes/modifiers/reset/Compose/hex, fair UART/PS2/USB polling, UTF-8 and CRLF");
}
