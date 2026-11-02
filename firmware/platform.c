#include "platform.h"
#define REG(n) (*(volatile uint32_t *)(0x20000000U+(n)))
#define TEXT ((volatile uint32_t *)0x10000000U)
static unsigned row=1,column=0;
static int high_capacity;
static char status_line[80];
static void serial_string(const char *s){while(*s)REG(20)=*s++;}
static void newline(void) {
  column=0;if(++row<32)return;row=31;
  for(unsigned i=80;i<2480;i++)TEXT[i]=TEXT[i+80];
  for(unsigned i=2480;i<2560;i++)TEXT[i]=' ';
}
void console_put(int c) {
  // Serial terminals need CR+LF; the HDMI console handles LF below.
  if(c=='\n')REG(20)='\r';
  REG(20)=c;
  if(c=='\n'){newline();return;}
  if(c==8){if(column){column--;TEXT[row*80+column]=' ';}return;}
  if(c<32||c>126)return;
  TEXT[row*80+column]=c;
  if(++column==80)newline();
}
void status_put(unsigned col,int c){if(col<80){TEXT[col]=c|128;status_line[col]=c;}}
void status_flush(unsigned right_start){
  unsigned left_end=right_start;
  while(left_end&&status_line[left_end-1]==' ')left_end--;
  // Save the input cursor, update the reserved first row, then restore it.
  serial_string("\0337\033[1;1H\033[2K");
  for(unsigned i=0;i<left_end;i++)REG(20)=status_line[i];
  // Clamp to the actual terminal's right edge, leaving one blank column.
  serial_string("\033[999C\033[");
  unsigned width=79-right_start,k=0;char digits[3];
  do{digits[k++]='0'+width%10;width/=10;}while(width);
  while(k)REG(20)=digits[--k];
  REG(20)='D';
  for(unsigned i=right_start;i<79;i++)REG(20)=status_line[i];
  serial_string("\0338");
}
static const uint8_t keymap[128]={
 [0x1c]='a',[0x32]='b',[0x21]='c',[0x23]='d',[0x24]='e',[0x2b]='f',
 [0x34]='g',[0x33]='h',[0x43]='i',[0x3b]='j',[0x42]='k',[0x4b]='l',
 [0x3a]='m',[0x31]='n',[0x44]='o',[0x4d]='p',[0x15]='q',[0x2d]='r',
 [0x1b]='s',[0x2c]='t',[0x3c]='u',[0x2a]='v',[0x1d]='w',[0x22]='x',
 [0x35]='y',[0x1a]='z',[0x45]='0',[0x16]='1',[0x1e]='2',[0x26]='3',
 [0x25]='4',[0x2e]='5',[0x36]='6',[0x3d]='7',[0x3e]='8',[0x46]='9',
 [0x29]=' ',[0x5a]=13,[0x66]=8,[0x0d]=9,[0x4e]='-',[0x55]='=',
 [0x54]='[',[0x5b]=']',[0x5d]=92,[0x4c]=';',[0x52]=39,
 [0x41]=',',[0x49]='.',[0x4a]='/',[0x0e]='`'
};
int console_get(void) {
  static unsigned shifts,release,extended,caps,previous_cr;
  for(;;) {
    uint32_t v=REG(0);
    if(v&256){int c=v&255;if(c==10&&previous_cr){previous_cr=0;continue;}previous_cr=c==13;return c;}
    v=REG(16);if(!(v&256))continue;unsigned scan=v&255;
    if(scan==0xf0){release=1;continue;}if(scan==0xe0){extended=1;continue;}
    if(scan==0x12||scan==0x59){unsigned mask=scan==0x12?1:2;if(release)shifts&=~mask;else shifts|=mask;}
    else if(scan==0x58&&!release)caps^=1;
    else if(!release&&extended&&(scan==0x75||scan==0x72)){
      extended=0;return scan==0x75?KEY_UP:KEY_DOWN;
    }
    else if(!release&&scan<128&&(!extended||scan==0x5a)){
      int c=keymap[scan];release=0;extended=0;
      if(c>='a'&&c<='z'){if(!!shifts^caps)c-=32;}
      else if(shifts){const char *normal="1234567890-=[];'/.,`";const char *upper="!@#$%^&*()_+{}:\"?><~";
        for(unsigned i=0;normal[i];i++)if(c==normal[i]){c=upper[i];break;}if(c==92)c='|';}
      if(c)return c;
    }
    release=0;extended=0;
  }
}
static uint8_t spi(unsigned value){REG(4)=value;while(REG(4)&256){}return REG(4);}
static void deselect(void){REG(8)=1;spi(255);}
static unsigned command(unsigned cmd,uint32_t arg){
  deselect();REG(8)=0;spi(255);spi(0x40|cmd);
  spi(arg>>24);spi(arg>>16);spi(arg>>8);spi(arg);spi(cmd==0?0x95:cmd==8?0x87:1);
  for(unsigned i=0;i<16;i++){unsigned r=spi(255);if(!(r&128))return r;}return 255;
}
static int sd_init(void){
  REG(12)=39;REG(8)=1;for(unsigned i=0;i<16;i++)spi(255);
  if(command(0,0)!=1){deselect();return 0;}
  unsigned r=command(8,0x1aa);int v2=r==1;
  if(v2){unsigned reply=0;for(unsigned i=0;i<4;i++)reply=(reply<<8)|spi(255);if((reply&0xfff)!=0x1aa){deselect();return 0;}}
  else if(r!=5){deselect();return 0;}
  for(unsigned i=0;i<20000;i++){
    command(55,0);r=command(41,v2?0x40000000:0);if(!r)break;
  }
  if(r){deselect();return 0;}
  if(command(58,0)){deselect();return 0;}
  unsigned ocr=spi(255);for(unsigned i=0;i<3;i++)spi(255);high_capacity=v2&&!!(ocr&64);
  if(!high_capacity&&command(16,512)){deselect();return 0;}
  deselect();REG(12)=3;return 1;
}
int disk_read(uint32_t sector,uint8_t *data){
  if(command(17,high_capacity?sector:sector*512)){deselect();return 0;}
  unsigned r=255;for(unsigned i=0;i<100000;i++){r=spi(255);if(r!=255)break;}
  if(r!=254){deselect();return 0;}
  for(unsigned i=0;i<512;i++)data[i]=spi(255);spi(255);spi(255);deselect();return 1;
}
int disk_write(uint32_t sector,const uint8_t *data){
  /* The story and card metadata are never writable by the interpreter. */
  if(sector<256||sector>=384)return 0;
  if(command(24,high_capacity?sector:sector*512)){deselect();return 0;}
  spi(255);spi(254);for(unsigned i=0;i<512;i++)spi(data[i]);spi(255);spi(255);
  unsigned r=spi(255);if((r&31)!=5){deselect();return 0;}
  for(unsigned i=0;i<200000;i++)if(spi(255)==255){deselect();return 1;}
  deselect();return 0;
}
void platform_init(void){
  row=1;column=0;
  // Initialize the serial terminal independently of its previous display state.
  // Keep the terminal's default background: ANSI palette black may be gray.
  // Reserve row 1 for status; the scrolling region extends to the terminal bottom.
  serial_string("\033[0m\033[37;49m\033[2J\033[2;r\033[2;1H");
  for(unsigned i=0;i<2560;i++)TEXT[i]=' ';
  if(!sd_init())fatal("SD initialization failed; insert prepared card and reset");
}
/* Freestanding compiler helpers. */
void *memcpy(void *d,const void *s,unsigned n){uint8_t *a=d;const uint8_t *b=s;while(n--)*a++=*b++;return d;}
void *memset(void *d,int v,unsigned n){uint8_t *a=d;while(n--)*a++=v;return d;}
