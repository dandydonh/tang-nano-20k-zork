#include "platform.h"
#include "storage.h"
#include "screen.h"
#ifndef REG
#define REG(n) (*(volatile uint32_t *)(0x20000000U+(n)))
#endif
#ifndef TEXT
#define TEXT ((volatile uint32_t *)0x10000000U)
#endif
static unsigned row=1,column=0;
static uint8_t pending_keys[64],report_bytes[16];
static unsigned pending_count,pending_read,report_length,report_state,report_rows,report_columns;
static unsigned report_received;
static unsigned terminal_rows=18,terminal_columns=80;
static void terminal_size(void);
static int high_capacity;
static char status_line[80];
static void serial_string(const char *s){while(*s)REG(20)=*s++;}
static void newline(void) {
  column=0;if(++row<32)return;row=31;
  for(unsigned i=80;i<2480;i++)TEXT[i]=TEXT[i+80];
  for(unsigned i=2480;i<2560;i++)TEXT[i]=' ';
}
void console_emit(int c) {
  if(c=='\n'){newline();return;}
  if(c==8){if(column){column--;TEXT[row*80+column]=' ';}return;}
  if(c<32||c>126)return;
  TEXT[row*80+column]=c;
  column++;
}
int console_previous_line(void) {
  if(row<=1)return 0;
  row--;column=CONSOLE_COLUMNS-1;
  return 1;
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
static unsigned display_row=99,display_col=99,display_inverse=99;
static void serial_number(unsigned n) { if(n>=10)serial_number(n/10);REG(20)='0'+n%10; }
void display_move(unsigned r,unsigned c) {
  serial_string("\033[");serial_number(r+1);REG(20)=';';serial_number(c+1);REG(20)='H';
  display_row=r;display_col=c;row=r;column=c;
}
void display_cell(unsigned r,unsigned c,int ch,unsigned inverse) {
  if(r>=32||c>=79)return;
  if(display_row!=r||display_col!=c)display_move(r,c);
  if(display_inverse!=inverse){serial_string(inverse?"\033[7m":"\033[0m");display_inverse=inverse;}
  TEXT[r*80+c]=ch|(inverse?128:0);REG(20)=ch;display_col=c+1;column=c+1;
}
void display_clear(unsigned first,unsigned last) {
  for(unsigned r=first;r<last;r++){
    display_move(r,0);serial_string("\033[0m\033[2K");
    for(unsigned c=0;c<80;c++)TEXT[r*80+c]=' ';
  }
  display_inverse=0;display_row=display_col=99;
}
void display_scroll(unsigned top) {
  for(unsigned i=top*80;i<2480;i++)TEXT[i]=TEXT[i+80];
  for(unsigned i=2480;i<2560;i++)TEXT[i]=' ';
  serial_string("\033[0m\033[");serial_number(top+1);serial_string(";32r\033[32;1H\r\n");
  display_inverse=0;
  display_row=31;display_col=0;row=31;column=0;
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
/* Only a complete cursor report is consumed. Arrow keys and ordinary input
 * survive a probe, and a delayed reply cannot become a game command. */
static void terminal_byte(unsigned c) {
  if(report_length==sizeof(report_bytes)){
    for(unsigned i=0;i<report_length;i++)pending_keys[pending_count++]=report_bytes[i];
    report_length=0;
  }
  if(!report_length&&c!=27){pending_keys[pending_count++]=c;return;}
  report_bytes[report_length++]=c;
  if(report_length==1){report_state=1;report_rows=report_columns=0;return;}
  if(report_state==1&&c=='['){report_state=2;return;}
  if(report_state==2&&c>='0'&&c<='9'&&report_rows<100){report_rows=report_rows*10+c-'0';return;}
  if(report_state==2&&c==';'&&report_length>3){report_state=3;return;}
  if(report_state==3&&c>='0'&&c<='9'&&report_columns<100){report_columns=report_columns*10+c-'0';return;}
  if(report_state==3&&c=='R'&&report_rows>=4&&report_columns>=8){
    terminal_rows=report_rows;terminal_columns=report_columns;report_received=1;
  }else for(unsigned i=0;i<report_length;i++)pending_keys[pending_count++]=report_bytes[i];
  report_length=0;
}
static int raw_console_get(void) {
  static unsigned shifts,release,extended,caps,previous_cr;
  for(;;) {
    uint32_t v;
    if(pending_read<pending_count){v=pending_keys[pending_read++]|256;if(pending_read==pending_count)pending_read=pending_count=0;}
    else {v=REG(0);if(v&256){terminal_byte(v&255);continue;}}
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
int console_get(void) {
  screen_flush();console_story_flush();console_page_reset();
  return raw_console_get();
}
void console_more(void) {
  // Called at column zero after a newline. Preserve cells under the prompt,
  // and read keys without recursively flushing the active output word.
  unsigned saved[6];
  for(unsigned i=0;i<6;i++)saved[i]=TEXT[row*80+i];
  serial_string("\033[0m[MORE]");
  for(unsigned i=0;i<6;i++)TEXT[row*80+i]="[MORE]"[i];
  int c;do{c=raw_console_get();}while(c!=' '&&c!='\r'&&c!='\n');
  serial_string("\b\b\b\b\b\b");
  for(unsigned i=0;i<6;i++){
    TEXT[row*80+i]=saved[i];serial_string(saved[i]&128?"\033[7m":"\033[0m");REG(20)=screen.font?(saved[i]&127):' ';
  }
  serial_string("\b\b\b\b\b\b");display_row=display_col=display_inverse=99;
  terminal_size();
}
/* Save/restore the cursor so probing never moves an in-progress prompt.
 * Failed probes retain the last known dimensions and preserve typed input. */
static void terminal_size(void) {
  if(!pending_count&&!report_length){
    report_received=0;
    serial_string("\0337\033[999;999H\033[6n\0338");
    for(unsigned wait=0;wait<100000&&!report_received&&pending_count<48;wait++) {
      unsigned v=REG(0);if(v&256)terminal_byte(v&255);
    }
  }
  // A terminal may retain the old scrolling bottom after a window resize.
  if(report_received&&!screen.font)serial_string("\0337\033[2;r\0338");
  console_width(terminal_columns-1);
  console_page_height(screen.font&&terminal_rows>32?32:terminal_rows);
}
void console_input_begin(void) {
  screen_flush();console_story_flush();terminal_size();console_page_reset();
}
void console_serial_emit(int c) { if(c=='\n')REG(20)='\r';REG(20)=c; }
void console_serial_previous(unsigned width) {
  serial_string("\033[1A\033[");serial_number(width-1);REG(20)='C';
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
int sd_read_sector(uint32_t sector,uint8_t *data){
  if(!high_capacity&&sector>UINT32_MAX/512U)return 0;
  if(command(17,high_capacity?sector:sector*512)){deselect();return 0;}
  unsigned r=255;for(unsigned i=0;i<100000;i++){r=spi(255);if(r!=255)break;}
  if(r!=254){deselect();return 0;}
  for(unsigned i=0;i<512;i++)data[i]=spi(255);spi(255);spi(255);deselect();return 1;
}
int sd_write_sector(uint32_t sector,const uint8_t *data){
  /* Only mapped save-file data sectors are writable. */
  if(!storage_writable(sector))return 0;
  if(!high_capacity&&sector>UINT32_MAX/512U)return 0;
  if(command(24,high_capacity?sector:sector*512)){deselect();return 0;}
  spi(255);spi(254);for(unsigned i=0;i<512;i++)spi(data[i]);spi(255);spi(255);
  unsigned r=spi(255);if((r&31)!=5){deselect();return 0;}
  for(unsigned i=0;i<200000;i++)if(spi(255)==255){deselect();return 1;}
  deselect();return 0;
}
static void check_sdram(void) {
  unsigned wait;
  for(wait=0;wait<100000&&!REG(24);wait++){}
  if(!REG(24))fatal("SDRAM initialization timeout");
  volatile uint32_t *memory=(volatile uint32_t*)0x30000000U;
  /* Walking data and byte enables, then simultaneous address-line probes.
   * A broken upper address line must not silently alias the live story. */
  for(unsigned bit=0;bit<32;bit++) {
    memory[0]=1U<<bit;if(memory[0]!=(1U<<bit))fatal("SDRAM data test");
    memory[0]=~(1U<<bit);if(memory[0]!=~(1U<<bit))fatal("SDRAM data test");
  }
  memory[0]=0;
  volatile uint8_t *bytes=(volatile uint8_t*)memory;
  for(unsigned i=0;i<4;i++)bytes[i]=0x12+0x21*i;
  if(memory[0]!=0x75543312U)fatal("SDRAM byte enables");
  memory[0]=0xa55a1234U;
  for(unsigned bit=0;bit<21;bit++)memory[1U<<bit]=0x31415926U^bit;
  memory[2097151]=0x89abcdefU;
  if(memory[0]!=0xa55a1234U||memory[2097151]!=0x89abcdefU)fatal("SDRAM address test");
  for(unsigned bit=0;bit<21;bit++)if(memory[1U<<bit]!=(0x31415926U^bit))fatal("SDRAM address alias");
}
void platform_init(void){
  row=1;column=0;
  console_reset();
  // Initialize the serial terminal independently of its previous display state.
  // Keep the terminal's default background: ANSI palette black may be gray.
  // Reserve row 1 for status; the scrolling region extends to the terminal bottom.
  serial_string("\033[0m\033[37;49m\033[2J\033[2;r\033[2;1H");
  terminal_rows=18;terminal_columns=80;pending_count=pending_read=report_length=0;terminal_size();
  for(unsigned i=0;i<2560;i++)TEXT[i]=' ';
  check_sdram();
  if(!sd_init())fatal("SD initialization failed; insert prepared card and reset");
}
/* Freestanding compiler helpers. */
void *memcpy(void *d,const void *s,unsigned n){uint8_t *a=d;const uint8_t *b=s;while(n--)*a++=*b++;return d;}
void *memset(void *d,int v,unsigned n){uint8_t *a=d;while(n--)*a++=v;return d;}
