#include "platform.h"
#include "storage.h"
#include "screen.h"
#include "unicode.h"
#include "ps2.h"
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
static const char *input_mode_label;
static void serial_string(const char *s){while(*s)REG(20)=*s++;}
static void input_mode_header(void) {
  if(!input_mode_label)return;
  const char *label=input_mode_label;
  for(unsigned i=0;i<80;i++)TEXT[i]=(*label?*label++:' ')|128;
}
void console_clear(void) {
  for(unsigned i=0;i<2560;i++)TEXT[i]=' ';
  input_mode_header();
  row=1;column=0;
  serial_string("\033[0m\033[2J\033[2;1H");
}
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
  unsigned width=unicode_columns(ch);
  if(r>=32||c>79||(c==79&&width))return;
  if(display_row!=r||display_col!=c)display_move(r,c);
  if(display_inverse!=inverse){serial_string(inverse?"\033[7m":"\033[0m");display_inverse=inverse;}
  if(width)TEXT[r*80+c]=(ch<128?ch:'?')|(inverse?128:0);
  if(width==2&&c+1<79)TEXT[r*80+c+1]=' '|(inverse?128:0);
  uint8_t bytes[4];unsigned count=unicode_encode(ch,bytes);
  for(unsigned i=0;i<count;i++)REG(20)=bytes[i];
  display_col=c+width;column=c+width;
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
static int raw_console_event_get(void) {
  static unsigned previous_cr,next_source;
  for(;;) {
    unsigned source=next_source;
    next_source=(next_source+1)%3;
    uint32_t v;
    if(source==0) {
      if(pending_read<pending_count){v=pending_keys[pending_read++]|256;if(pending_read==pending_count)pending_read=pending_count=0;}
      else {v=REG(0);if(v&256){terminal_byte(v&255);continue;}}
      if(v&256){int c=v&255;if(c==10&&previous_cr){previous_cr=0;continue;}previous_cr=c==13;return c;}
    } else {
      v=source==1?REG(16):REG(28);
      if(v&256){int key=ps2_key_source(source-1,v&255);if(key)return key;}
    }
  }
}
static int raw_console_get(void){return key_plain(raw_console_event_get());}
int console_event_get(void) {
  screen_flush();console_story_flush();console_page_reset();
  return raw_console_event_get();
}
int console_get(void){return key_plain(console_event_get());}
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
  ps2_reset();
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
  // Show the latched FPGA input mode on both HDMI and its serial stream.
  // Legacy profiles return zero for this otherwise unused register.
  unsigned input_mode=REG(32);
  input_mode_label=(input_mode&1)?((input_mode&2)?"Input: serial terminal + PS/2":"Input: USB keyboard + PS/2"):0;
  if(input_mode&1)switch((input_mode>>12)&15) {
    case 2:input_mode_label="Input: USB keyboard + PS/2 (manual)";break;
    case 4:input_mode_label="Input: serial terminal + PS/2 (Companion not detected)";break;
    case 5:input_mode_label="Input: serial terminal + PS/2 (Companion not ready; UART blocked)";break;
    case 6:input_mode_label="Input: serial terminal + PS/2 (legacy activity; UART blocked)";break;
  }
  if((input_mode&11)==11)
    input_mode_label="Input: serial terminal + PS/2 (Companion conflict; UART blocked)";
  if(input_mode_label) {
    input_mode_header();
    const char *label=input_mode_label;
    while(*label)console_put(*label++);
    console_put('\n');
  }
}
/* Freestanding compiler helpers. */
void *memcpy(void *d,const void *s,unsigned n){uint8_t *a=d;const uint8_t *b=s;while(n--)*a++=*b++;return d;}
void *memset(void *d,int v,unsigned n){uint8_t *a=d;while(n--)*a++=v;return d;}
