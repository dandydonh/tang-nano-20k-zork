/* US set-2 keys, explicit Compose, and Ctrl+Shift+U hexadecimal entry. */
#include "platform.h"
#include "unicode.h"
#include "ps2.h"
static const uint8_t keymap[128]={
 [0x1c]='a',[0x32]='b',[0x21]='c',[0x23]='d',[0x24]='e',[0x2b]='f',
 [0x34]='g',[0x33]='h',[0x43]='i',[0x3b]='j',[0x42]='k',[0x4b]='l',
 [0x3a]='m',[0x31]='n',[0x44]='o',[0x4d]='p',[0x15]='q',[0x2d]='r',
 [0x1b]='s',[0x2c]='t',[0x3c]='u',[0x2a]='v',[0x1d]='w',[0x22]='x',
 [0x35]='y',[0x1a]='z',[0x45]='0',[0x16]='1',[0x1e]='2',[0x26]='3',
 [0x25]='4',[0x2e]='5',[0x36]='6',[0x3d]='7',[0x3e]='8',[0x46]='9',
 [0x29]=' ',[0x5a]=13,[0x66]=8,[0x0d]=9,[0x4e]='-',[0x55]='=',
 [0x54]='[',[0x5b]=']',[0x5d]=92,[0x4c]=';',[0x52]=39,
 [0x41]=',',[0x49]='.',[0x4a]='/',[0x0e]='`',[0x76]=27
};
static const struct compose_pair { uint8_t first,second;uint16_t value; } pairs[]={
 {'\'', 'A',0xc1},{'\'', 'E',0xc9},{'\'', 'I',0xcd},{'\'', 'O',0xd3},{'\'', 'U',0xda},{'\'', 'Y',0xdd},
 {'\'', 'a',0xe1},{'\'', 'e',0xe9},{'\'', 'i',0xed},{'\'', 'o',0xf3},{'\'', 'u',0xfa},{'\'', 'y',0xfd},
 {'`','A',0xc0},{'`','E',0xc8},{'`','I',0xcc},{'`','O',0xd2},{'`','U',0xd9},
 {'`','a',0xe0},{'`','e',0xe8},{'`','i',0xec},{'`','o',0xf2},{'`','u',0xf9},
 {'"','A',0xc4},{'"','E',0xcb},{'"','I',0xcf},{'"','O',0xd6},{'"','U',0xdc},{'"','Y',0x178},
 {'"','a',0xe4},{'"','e',0xeb},{'"','i',0xef},{'"','o',0xf6},{'"','u',0xfc},{'"','y',0xff},
 {'^','A',0xc2},{'^','E',0xca},{'^','I',0xce},{'^','O',0xd4},{'^','U',0xdb},
 {'^','a',0xe2},{'^','e',0xea},{'^','i',0xee},{'^','o',0xf4},{'^','u',0xfb},
 {'~','A',0xc3},{'~','N',0xd1},{'~','O',0xd5},{'~','a',0xe3},{'~','n',0xf1},{'~','o',0xf5},
 {',','C',0xc7},{',','c',0xe7},{'o','A',0xc5},{'o','a',0xe5},{'/','O',0xd8},{'/','o',0xf8},
 {'a','e',0xe6},{'A','E',0xc6},{'o','e',0x153},{'O','E',0x152},{'s','s',0xdf},
 {'t','h',0xfe},{'T','H',0xde},{'d','h',0xf0},{'D','H',0xd0},{'L','-',0xa3},
 {'<','<',0xab},{'>','>',0xbb},{'!','!',0xa1},{'?','?',0xbf},{'e','=',0x20ac},
 {'-','-',0x2013},{'-','_',0x2014}
};
static uint8_t down[32],consumed[32];
static unsigned extended,released,pause_left,caps,mode,first,hex_value,hex_digits,hex_overflow;
static int held(unsigned key){return (down[key/8]>>(key%8))&1;}
void ps2_reset(void) {
  for(unsigned i=0;i<32;i++)down[i]=consumed[i]=0;
  extended=released=pause_left=caps=mode=first=hex_value=hex_digits=hex_overflow=0;
}
static int character(unsigned c){return KEY_UNICODE_BASE+c;}
int ps2_key(unsigned scan) {
  if(scan==0xaa||scan==0||scan==0xff){ps2_reset();return 0;}
  if(pause_left){pause_left--;return 0;}
  if(scan==0xe1){pause_left=7;extended=released=0;return 0;}
  if(scan==0xe0){extended=1;return 0;}
  if(scan==0xf0){released=1;return 0;}
  if(scan>=128){extended=released=0;return 0;}
  unsigned ext=extended,up=released,key=scan+(ext?128:0),mask=1U<<(key%8),was=held(key);
  extended=released=0;
  if(up){down[key/8]&=~mask;consumed[key/8]&=~mask;return 0;}
  down[key/8]|=mask;
  if(scan==0x58&&!ext){if(!was)caps^=1;return 0;}
  if((scan==0x12||scan==0x59||scan==0x14||scan==0x11)&&!ext)return 0;
  if(scan==0x14&&ext)return 0;
  if(was&&(consumed[key/8]&mask))return 0;
  if(ext&&(scan==0x11||scan==0x2f)) {
    consumed[key/8]|=mask;mode=1;first=0;return 0;
  }
  unsigned shift=held(0x12)||held(0x59),ctrl=held(0x14)||held(0x94);
  if(!ext&&scan==0x3c&&ctrl&&shift&&!was) {
    consumed[key/8]|=mask;mode=2;hex_value=hex_digits=hex_overflow=0;return 0;
  }
  unsigned c=ext?(scan==0x5a?13:scan==0x75?KEY_UP:scan==0x72?KEY_DOWN:0):keymap[scan];
  if(!c)return 0;
  if(c>='a'&&c<='z'){if(!!shift^caps)c-=32;}
  else if(shift){const char *normal="1234567890-=[];'/.,`",*upper="!@#$%^&*()_+{}:\"?><~";
    for(unsigned i=0;normal[i];i++)if(c==(unsigned char)normal[i]){c=upper[i];break;}if(c==92)c='|';}
  if(!mode)return c==27?0:(c==KEY_UP||c==KEY_DOWN?(int)c:character(c));
  consumed[key/8]|=mask;
  if(was)return 0;
  if(c==27){mode=first=0;return 0;}
  if(mode==1) {
    if(c==8){first=0;return 0;}
    if(c<32||c>126){mode=first=0;return 0;}
    if(!first){first=c;return 0;}
    mode=0;
    for(unsigned i=0;i<sizeof(pairs)/sizeof(pairs[0]);i++)
      if(pairs[i].first==first&&pairs[i].second==c)return character(pairs[i].value);
    return 0;
  }
  if(c==8){if(hex_overflow)hex_value=hex_digits=hex_overflow=0;else if(hex_digits){hex_digits--;hex_value>>=4;}return 0;}
  if(c==13||c==' ') {
    mode=0;return hex_digits&&!hex_overflow&&unicode_printable(hex_value)?character(hex_value):0;
  }
  /* The entry chord may still be held: hexadecimal digits use unshifted keys. */
  unsigned digit=ext?c:keymap[scan];
  if(digit>='0'&&digit<='9')digit-='0';
  else if(digit>='a'&&digit<='f')digit=digit-'a'+10;
  else {hex_overflow=1;return 0;}
  if(hex_digits==6)hex_overflow=1;
  else {hex_value=(hex_value<<4)|digit;hex_digits++;}
  return 0;
}
