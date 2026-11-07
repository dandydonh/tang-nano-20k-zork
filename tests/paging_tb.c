/* Exercise the actual board pager, terminal query and raw UART/PS2 decoder. */
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
static uint32_t cells[2560],reg_value,tx_value;
static const unsigned *uart_input,*ps2_input;
static char serial[20000];
static unsigned serial_len,tx_pending;
static void drain(void){if(tx_pending){assert(serial_len<sizeof(serial)-1);serial[serial_len++]=tx_value;serial[serial_len]=0;tx_pending=0;}}
static volatile uint32_t *test_register(unsigned n){
  drain();reg_value=0;
  if(n==20){tx_pending=1;return &tx_value;}
  if(n==0&&uart_input&&*uart_input)reg_value=*uart_input++|256;
  if(n==16&&ps2_input&&*ps2_input)reg_value=*ps2_input++|256;
  return &reg_value;
}
#define REG(n) (*test_register(n))
#define TEXT cells
#include "../firmware/platform.c"
void fatal(const char *message){(void)message;assert(0);}
#include "../firmware/screen.c"
static unsigned occurrences(const char *needle){unsigned count=0;for(unsigned i=0;i<serial_len;i++){unsigned j=0;while(needle[j]&&serial[i+j]==needle[j])j++;if(!needle[j])count++;}return count;}
int main(int argc,char **argv){
  if(argc==4){
    unsigned width=strtoul(argv[1],0,10),height=strtoul(argv[2],0,10);
    char reply[32];snprintf(reply,sizeof(reply),"\033[%u;%uR",height,width);
    unsigned response[32]={0};for(unsigned i=0;reply[i];i++)response[i]=(unsigned char)reply[i];
    uart_input=response;console_reset();terminal_size();drain();serial_len=0;serial[0]=0;
    uart_input=0;console_page_height(0);for(unsigned i=0;i<2560;i++)cells[i]=' ';
    if(argv[3][0]=='e'){
      for(const char *p="Input> ";*p;p++)console_put(*p);
      for(unsigned i=0;i<119;i++)console_put('x');
      for(unsigned i=0;i<119;i++){console_put(8);console_put(' ');console_put(8);}
      for(const char *p="look";*p;p++)console_put(*p);
      for(unsigned i=0;i<11;i++)assert(cells[80+i]==(unsigned char)"Input> look"[i]);
      for(unsigned i=91;i<2560;i++)assert(cells[i]==' ');
    }else if(argv[3][0]=='l'){
      for(unsigned i=0;i<500;i++)console_story_put('x');console_story_flush();
      for(unsigned i=159;i<2560;i+=80)assert(cells[i]==' ');
    }else{
      for(unsigned i=0;i<200;i++){char w[16];snprintf(w,sizeof(w),"word%03u ",i);for(char *p=w;*p;p++)console_story_put(*p);}
      console_story_flush();
      for(unsigned i=159;i<2560;i+=80)assert(cells[i]==' ');
    }
    drain();fwrite(serial,1,serial_len,stdout);return 0;
  }

  const unsigned report[]={27,'[','1','8',';','1','4','3','R',0};uart_input=report;
  terminal_size();assert(terminal_rows==18&&terminal_columns==143);
  const unsigned tall[]={27,'[','5','0',';','8','0','R',0};uart_input=tall;
  terminal_size();assert(terminal_rows==50&&terminal_columns==80);
  uart_input=0;terminal_size();assert(terminal_rows==50&&terminal_columns==80);
  const unsigned typed[]={'x',0};uart_input=typed;terminal_size();assert(raw_console_get()=='x');
  const unsigned early_enter[]={13,10,'x',0};uart_input=early_enter;
  terminal_size();assert(raw_console_get()==13);assert(raw_console_get()=='x');
  // Interleaved typeahead and arrow keys survive the complete size reply.
  const unsigned interleaved[]={'l',27,'[','A',27,'[','3','5',';','1','4','9','R','o',0};uart_input=interleaved;
  terminal_size();assert(terminal_rows==35&&terminal_columns==149);
  assert(raw_console_get()=='l');assert(raw_console_get()==27);assert(raw_console_get()=='[');assert(raw_console_get()=='A');assert(raw_console_get()=='o');
  // Overlong/malformed replies must remain bounded, including leading zeros.
  const unsigned zeros[]={27,'[','0','0','0','0','0','0','0','0','0','0','0','0','0','0','0','R','z',0};
  uart_input=zeros;terminal_size();for(unsigned i=0;i<19;i++)assert(raw_console_get()==(int)zeros[i]);
  // A response arriving after the bounded wait is filtered from game input.
  uart_input=0;terminal_size();
  const unsigned late[]={27,'[','2','4',';','1','0','0','R','n',0};uart_input=late;
  assert(raw_console_get()=='n');
  terminal_rows=18;terminal_columns=80;
  console_reset();console_page_height(18);row=1;column=0;
  const unsigned keys[]={'z',' ', 'l',0};uart_input=keys;
  for(unsigned i=0;i<15;i++)console_put('\n');drain();assert(!occurrences("[MORE]"));
  console_put('\n');drain();assert(occurrences("[MORE]")==1);assert(row==17&&column==0);
  for(unsigned i=0;i<6;i++)assert(cells[row*80+i]==0);
  assert(console_get()=='l');
  // Enter acknowledgement consumes CRLF rather than submitting an empty command.
  const unsigned enter[]={13,10,'n',0};uart_input=enter;console_more();assert(console_get()=='n');
  // PS/2 acknowledgement uses the same board decoder as game input.
  const unsigned ps2[]={0x29,0xf0,0x29,0x5a,0};uart_input=0;ps2_input=ps2;
  console_more();assert(console_get()==13);ps2_input=0;
  // Restoring the temporarily covered cells preserves inverse text on UART.
  const unsigned inverse_ack[]={' ',0};
  screen.font=1;cells[row*80]='S'|128;uart_input=inverse_ack;console_more();drain();
  assert(cells[row*80]==('S'|128)&&occurrences("\033[7mS"));screen.font=0;
  // Long unbroken strings count their automatic wraps, too.
  console_reset();console_page_height(4);const unsigned space[]={' ',0};uart_input=space;
  unsigned before=occurrences("[MORE]");for(unsigned i=0;i<159;i++)console_put('a');drain();
  assert(occurrences("[MORE]")==before+1);
  // Upper-window drawing never pages; lower-window capacity excludes the split.
  console_page_height(18);screen_reset();screen_split(3);screen_window(1);screen_style(1);
  for(unsigned i=0;i<30;i++)screen_put('\n');drain();
  unsigned upper_pages=occurrences("[MORE]");screen_cursor(1,1);screen_put('S');
  screen_style(0);screen_window(0);uart_input=space;
  for(unsigned i=0;i<14;i++)screen_put('\n');drain();
  assert(occurrences("[MORE]")==upper_pages+1);assert(cells[0]==('S'|128));
  // The 35-row serial page can outgrow HDMI, then shrink without reset.
  screen.font=0;console_reset();row=1;column=0;
  const unsigned wide[]={27,'[','3','5',';','1','4','9','R',0};uart_input=wide;
  console_input_begin();assert(terminal_rows==35&&terminal_columns==149);
  before=occurrences("[MORE]");uart_input=space;
  for(unsigned i=0;i<32;i++)console_put('\n');drain();assert(occurrences("[MORE]")==before);
  console_put('\n');drain();assert(occurrences("[MORE]")==before+1&&row==31);
  uart_input=report;console_input_begin();before=occurrences("[MORE]");uart_input=space;
  for(unsigned i=0;i<16;i++)console_put('\n');drain();assert(occurrences("[MORE]")==before+1);
  // Fixed V5 windows still page within the 32-row screen.
  screen.font=1;uart_input=wide;console_input_begin();before=occurrences("[MORE]");uart_input=space;
  for(unsigned i=0;i<30;i++)console_page(1);drain();assert(occurrences("[MORE]")==before+1);
  // Unicode filename labels keep UTF-8 byte sequences intact on UART and use
  // bounded ASCII fallbacks on the existing HDMI font, including V5 windows.
  console_reset();console_page_height(0);console_width(7);row=1;column=0;
  serial_len=0;serial[0]=0;
  for(const char *p="12345";*p;p++)console_put(*p);
  console_put(0x754c);console_put('X');drain();
  assert(occurrences("12345\xe7\x95\x8c\r\nX")==1);
  assert(cells[85]=='?'&&cells[86]==' '&&cells[87]=='X');
  screen_reset();screen_cursor(1,1);serial_len=0;serial[0]=0;
  screen_name_put(0xe9);screen_name_put(0x1f680);screen_name_put('X');drain();
  assert(occurrences("\xc3\xa9\xf0\x9f\x9a\x80X")==1);
  assert(cells[0]=='?'&&cells[1]=='?'&&cells[2]==' '&&cells[3]=='X');
  assert(screen.col[0]==4);
  // Editing reverses independent wrap gaps on UART/HDMI and clears combining
  // marks with their base cells, preserving the preceding prompt/transcript.
  console_reset();console_page_height(0);console_width(20);row=1;column=0;
  for(unsigned i=0;i<2560;i++)cells[i]=' ';
  for(unsigned i=0;i<78;i++)console_put('p');
  console_edit_begin(0);console_put(0x754c);console_put(0x301);console_put(0xe9);
  console_edit_clear();assert(row==1&&column==78);
  for(unsigned i=0;i<78;i++)assert(cells[80+i]=='p');
  for(unsigned i=158;i<2560;i++)assert(cells[i]==' ');
  screen_reset();for(unsigned i=0;i<78;i++)screen_put('p');screen_flush();
  screen_edit_begin(0);screen_unicode_put(0x754c);screen_unicode_put(0x301);screen_unicode_put(0xe9);screen_flush();
  screen_edit_clear();assert(screen.row[0]==0&&screen.col[0]==78);
  for(unsigned i=0;i<78;i++)assert(cells[i]=='p');
  for(unsigned i=78;i<2560;i++)assert(cells[i]==' ');
  console_edit_end();console_reset();row=1;column=0;drain();serial_len=0;serial[0]=0;
  console_put(0xd800);console_put(0xfffe);console_put(0x110000);drain();
  assert(serial_len==3&&serial[0]=='?'&&serial[1]=='?'&&serial[2]=='?');
  puts("PASS board paging: height query/fallback, typeahead, page boundary, prompt erasure, UART/PS2, CRLF, long words, Unicode UART/HDMI filename labels");
}
