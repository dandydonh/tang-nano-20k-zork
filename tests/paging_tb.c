/* Exercise the actual board pager, terminal query and raw UART/PS2 decoder. */
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
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
int main(void){
  const unsigned report[]={27,'[','1','8',';','1','4','3','R',0};uart_input=report;
  assert(terminal_height()==18);
  const unsigned tall[]={27,'[','5','0',';','8','0','R',0};uart_input=tall;
  assert(terminal_height()==32);
  uart_input=0;assert(terminal_height()==18);
  const unsigned typed[]={'x',0};uart_input=typed;assert(terminal_height()==18);assert(raw_console_get()=='x');
  const unsigned early_enter[]={13,10,'x',0};uart_input=early_enter;
  assert(terminal_height()==18);assert(raw_console_get()==13);assert(raw_console_get()=='x');
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
  cells[row*80]='S'|128;uart_input=inverse_ack;console_more();drain();
  assert(cells[row*80]==('S'|128)&&occurrences("\033[7mS"));
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
  puts("PASS board paging: height query/fallback, typeahead, page boundary, prompt erasure, UART/PS2, CRLF, long words");
}
