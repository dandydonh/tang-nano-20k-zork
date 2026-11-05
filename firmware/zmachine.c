/* Version 3/5 Z-machine interpreter. All story addresses are byte addresses. */
#include "platform.h"
#include "storage.h"
#include "screen.h"
#define STACK_MAX 2048
#define FRAME_MAX 96
#define SAVE_MAGIC (version==5?0x36564d5aU:STORAGE_SAVE_MAGIC)
struct frame { uint32_t pc; uint16_t base; uint8_t result, pad; uint16_t locals[15]; };
struct machine {
  uint32_t pc, random;
  uint16_t sp, depth;
  uint16_t stack[STACK_MAX];
  struct frame frames[FRAME_MAX];
};
static struct machine vm;
/* Optional snapshot trailer keeps ordinary ZMV5 snapshots byte-compatible. */
struct output_streams {
  uint16_t table[16], length[16];
  uint8_t depth, screen;
  uint16_t reserved;
};
static struct output_streams streams;
typedef char snapshot_fits_bank[(sizeof(struct machine)+sizeof(streams)+sizeof(struct screen_state)+V3_DYNAMIC_MAX+511)/512+1<=STORAGE_BANK_SECTORS?1:-1];
#ifdef HOST
static uint8_t story_image[Z_STORY_MAX], dynamic_memory[65536];
#else
/* Pristine image retained for restart/verify; mutable image in a separate region. */
#define story_image ((volatile uint8_t *)0x30000000U)
#define dynamic_memory ((volatile uint8_t *)0x30040000U)
#endif
static uint8_t sector_buf[512];
static uint16_t dynamic_size, objects, globals, dictionary, abbreviations;
static int stopped, output_window, split_lines;
static unsigned version;
static unsigned undo_size;
#ifdef HOST
static uint8_t undo_image[STORAGE_BANK_BYTES];
#else
#define undo_image ((volatile uint8_t *)0x30060000U)
#endif
static uint32_t packed(unsigned p) { return (version==5?4U:2U)*p; }
static const char alphabet[] = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ \n0123456789.,!?_#'\"/\\-:()";
static void ui_put(int c) { if(version==5)screen_put(c);else console_put(c); }
static void say(const char *s) { while (*s) ui_put(*s++); }
void fatal(const char *s) { console_story_flush();if(version==5)screen_flush();say("\nCORE ERROR: "); say(s); say("\n"); stopped=1;
#ifdef HOST
  extern void exit(int); exit(2);
#else
  for (;;) {}
#endif
}
static uint8_t story(uint32_t a) {
  if(a >= storage_story_size()) { fatal("story address"); return 0; }
  return story_image[a];
}
static uint8_t rb(uint32_t a) { return a<dynamic_size ? dynamic_memory[a] : story(a); }
static uint16_t rw(uint32_t a) { return (rb(a)<<8)|rb(a+1); }
static void wb(uint32_t a,uint16_t v) {
  if(a>=dynamic_size)fatal("write outside dynamic memory");
  if(a==17)v&=~1; /* Transcript requests cannot enable an unavailable file backend. */
  dynamic_memory[a]=(uint8_t)v;
}
static void ww(uint32_t a,uint16_t v) { wb(a,v>>8);wb(a+1,v); }
static uint8_t fetch(void) { return rb(vm.pc++); }
static uint16_t fetchw(void) { uint16_t v=fetch();return (v<<8)|fetch(); }
static void push(uint16_t v) { if(vm.sp==STACK_MAX) fatal("stack overflow");vm.stack[vm.sp++]=v; }
static uint16_t pop(void) { if(vm.sp<=vm.frames[vm.depth].base) fatal("stack underflow");return vm.stack[--vm.sp]; }
static uint16_t variable(unsigned n,int indirect) {
  if(!n) { if(indirect) { if(vm.sp<=vm.frames[vm.depth].base) fatal("empty stack variable");return vm.stack[vm.sp-1]; } return pop(); }
  if(n<16) return vm.frames[vm.depth].locals[n-1];
  return rw(globals+2*(n-16));
}
static void setvar(unsigned n,uint16_t v,int indirect) {
  if(!n) { if(indirect) { if(vm.sp<=vm.frames[vm.depth].base) fatal("empty stack variable");vm.stack[vm.sp-1]=v; } else push(v); }
  else if(n<16) vm.frames[vm.depth].locals[n-1]=v;
  else ww(globals+2*(n-16),v);
}
static void store(uint16_t v) { setvar(fetch(),v,0); }
static void ret(uint16_t v) {
  if(!vm.depth) { stopped=1;return; }
  struct frame *f=&vm.frames[vm.depth];
  vm.sp=f->base;vm.pc=f->pc;unsigned dest=f->result,discard=f->pad&128;vm.depth--;if(!discard)setvar(dest,v,0);
}
static void branch(int condition) {
  unsigned b=fetch();int offset=b&63;
  if(!(b&64)) {offset=(offset<<8)|fetch();if(offset&8192)offset-=16384;}
  if(!!condition == !!(b&128)) { if(offset<2 && offset>=0)ret(offset);else vm.pc+=offset-2; }
}
static uint32_t obj(unsigned n) {
  if(!n||(version==3&&n>255))fatal("object number");
  uint32_t at=objects+(version==5?126U:62U)+(version==5?14U:9U)*(n-1);
  if(at+(version==5?14U:9U)>dynamic_size)fatal("object outside dynamic memory");return at;
}
static unsigned relation(unsigned n,unsigned field) { if(!n)return 0;uint32_t at=obj(n)+(version==5?6+2*field:4+field);return version==5?rw(at):rb(at); }
static void set_relation(unsigned n,unsigned field,unsigned value) { uint32_t at=obj(n)+(version==5?6+2*field:4+field);if(version==5)ww(at,value);else wb(at,value); }
static unsigned parent(unsigned n) { return relation(n,0); }
static unsigned sibling(unsigned n) { return relation(n,1); }
static unsigned child(unsigned n) { return relation(n,2); }
static void remove_obj(unsigned n) {
  unsigned p=parent(n);if(!p)return;
  unsigned c=child(p);
  if(c==n)set_relation(p,2,sibling(n));
  else { while(c&&sibling(c)!=n)c=sibling(c);if(!c)fatal("broken object tree");set_relation(c,1,sibling(n)); }
  set_relation(n,0,0);set_relation(n,1,0);
}
static uint32_t prop_table(unsigned n) { return rw(obj(n)+(version==5?12:7)); }
static uint32_t prop_start(unsigned n) { uint32_t a=prop_table(n);return a+1+2*rb(a); }
static unsigned prop_number(uint32_t p) { return rb(p)&(version==5?63:31); }
static unsigned prop_header(uint32_t p) { return version==5&&(rb(p)&128)?2:1; }
static unsigned prop_length(uint32_t p) { if(version==3)return 1+(rb(p)>>5);if(rb(p)&128){unsigned n=rb(p+1)&63;return n?n:64;}return rb(p)&64?2:1; }
static uint32_t prop_next(uint32_t p) { return p+prop_header(p)+prop_length(p); }
static uint32_t prop_find(unsigned n,unsigned p) {
  uint32_t a=prop_start(n);while(rb(a)&&prop_number(a)>p)a=prop_next(a);
  return prop_number(a)==p?a:0;
}
static void reset_streams(void) {
  for(unsigned i=0;i<sizeof(streams);i++)((uint8_t*)&streams)[i]=0;
  streams.screen=1;
}
static void zout(int c) {
  if(!c)return; /* ZSCII null has no effect. */
  if(streams.depth) {
    unsigned i=streams.depth-1;
    uint32_t at=(uint32_t)streams.table[i]+2+streams.length[i];
    if(at>=dynamic_size)fatal("memory stream outside dynamic memory");
    wb(at,c=='\n'?13:c);streams.length[i]++;
  } else if(streams.screen){if(version==5)screen_put(c);else if(!output_window)console_story_put(c==13?'\n':c);}
}
static void output_stream(int16_t number,unsigned table,unsigned operands) {
  /* Flush at the selection boundary, before changing the screen route. */
  console_story_flush();if(version==5)screen_flush();
  switch(number) {
    case 1:streams.screen=1;break;
    case -1:streams.screen=0;break;
    case 3:
      if(operands<2)fatal("memory stream requires table");
      if(streams.depth==16)fatal("memory stream nesting exceeds 16");
      if((uint32_t)table+2>dynamic_size)fatal("memory stream outside dynamic memory");
      streams.table[streams.depth]=table;streams.length[streams.depth++]=0;break;
    case -3:
      if(streams.depth){unsigned i=--streams.depth;ww(streams.table[i],streams.length[i]);}
      break;
    case 2:case 4:
      say("\nTranscript/command file output is unavailable.\n");
      /* A failed transcript selection must not claim success in Flags 2. */
      wb(17,rb(17)&~1);break;
    case -2:wb(17,rb(17)&~1);break;
    case -4:break;
    default:fatal("invalid output stream");
  }
}
static uint32_t ztext(uint32_t a,unsigned depth) {
  if(depth>8)fatal("abbreviation recursion");
  int shift=0,abbrev=0,escape=0;unsigned high=0;
  for(;;) {
    unsigned w=rw(a);a+=2;
    for(int i=10;i>=0;i-=5) {
      unsigned z=(w>>i)&31;
      if(abbrev) { ztext(2U*rw(abbreviations+2*(32*(abbrev-1)+z)),depth+1);abbrev=0;shift=0;continue; }
      if(escape) { if(escape==1){high=z;escape=2;}else{zout((high<<5)|z);escape=0;shift=0;}continue; }
      if(z==0){zout(' ');shift=0;}
      else if(z<4)abbrev=z;
      else if(z<6)shift=z-3;
      else if(shift==2&&z==6)escape=1;
      else { zout(version==5&&rw(52)?rb(rw(52)+shift*26+z-6):alphabet[shift*26+z-6]);shift=0; }
    }
    if(w&0x8000)return a;
  }
}
static void number(int16_t n) {
  unsigned v=n<0 ? -(int)n : n;char b[6];unsigned len=0;
  if(n<0)zout('-');do{b[len++]='0'+v%10;v/=10;}while(v);while(len)zout(b[--len]);
}
static void encode_word(uint32_t a,unsigned len,uint8_t *encoded) {
  unsigned z[9],count=0,limit=version==5?9:6;
  for(unsigned i=0;i<len&&count<limit;i++) {
    int c=rb(a+i);unsigned index=78;
    for(unsigned j=0;j<78;j++)if((version==5&&rw(52)?rb(rw(52)+j):alphabet[j])==c){index=j;break;}
    if(index<26)z[count++]=index+6;
    else if(index<78){z[count++]=index<52?4:5;if(count<limit)z[count++]=index%26+6;}
    else {z[count++]=5;if(count<limit)z[count++]=6;if(count<limit)z[count++]=c>>5;if(count<limit)z[count++]=c&31;}
  }
  while(count<limit)z[count++]=5;
  for(unsigned i=0;i<limit;i+=3){unsigned w=(z[i]<<10)|(z[i+1]<<5)|z[i+2];if(i+3==limit)w|=0x8000;encoded[2*i/3]=w>>8;encoded[2*i/3+1]=w;}
}
static int separator(int c,unsigned dict) { for(unsigned i=0;i<rb(dict);i++)if(rb(dict+1+i)==c)return 1;return 0; }
static void tokenize(unsigned text,unsigned parse,unsigned dict,int skip_unknown) {
  if(!parse)return;
  unsigned offset=version==5?2:1,a=text+offset,count=0,limit=rb(parse),end=version==5?a+rb(text+1):0;
  unsigned d=dict+1+rb(dict),entrylen=rb(d),start=d+3;int entries=(int16_t)rw(d+1),sorted=entries>=0;if(entries<0)entries=-entries;
  unsigned keylen=version==5?6:4;
  while((version==5?a<end:rb(a)!=0)&&count<limit) {
    if(rb(a)==' '){a++;continue;}
    unsigned word=a;int sep=separator(rb(a++),dict);
    if(!sep)while((version==5?a<end:rb(a)!=0)&&rb(a)!=' '&&!separator(rb(a),dict))a++;
    unsigned len=a-word;uint8_t key[6];encode_word(word,len,key);
    int lo=0,hi=entries-1;unsigned found=0;
    while(lo<=hi){int mid=sorted?(lo+hi)/2:lo;unsigned at=start+mid*entrylen;int cmp=0;
      for(unsigned k=0;k<keylen;k++){cmp=(int)key[k]-rb(at+k);if(cmp)break;}
      if(!cmp){found=at;break;}if(!sorted||cmp>0)lo=mid+1;else hi=mid-1;
    }
    unsigned p=parse+2+4*count++;if(!skip_unknown||found){ww(p,found);wb(p+2,len);wb(p+3,word-text);}
  }
  wb(parse+1,count);
}
static void status(void) {
  console_story_flush();if(version==5)screen_flush();
  /* V3 status is separate from the scrolling transcript. */
  for(unsigned i=0;i<80;i++)status_put(i,' ');
  const char *s=storage_story_name();unsigned i=0;
  while(*s)status_put(i++,*s++);
  s=" - Tang Nano 20K";while(*s)status_put(i++,*s++);
  char right[32];unsigned length=0;
  if(rb(1)&2) {
    s="Time: ";while(*s)right[length++]=*s++;
    unsigned hour=rw(globals+2)%24,minute=rw(globals+4)%60;
    right[length++]='0'+hour/10;right[length++]='0'+hour%10;right[length++]=':';
    right[length++]='0'+minute/10;right[length++]='0'+minute%10;
  } else {
  s="Score: ";while(*s)right[length++]=*s++;
  for(unsigned g=0;g<2;g++) {
    int n=(int16_t)rw(globals+2+2*g);char b[8];unsigned k=0,v=n<0?-n:n;
    if(n<0)right[length++]='-';do{b[k++]='0'+v%10;v/=10;}while(v);
    while(k)right[length++]=b[--k];if(!g){s="   Moves: ";while(*s)right[length++]=*s++;}
  }
  }
  unsigned right_start=79-length;
  for(i=0;i<length;i++)status_put(right_start+i,right[i]);
  status_flush(right_start);
}
static char last_command[256];
static unsigned last_length;
static void input_echo(int c) { if(streams.screen&&!streams.depth){if(version==5)screen_put(c);else console_put(c);} }
static void erase_story_input(unsigned len) {
  while(len--){input_echo(8);input_echo(' ');input_echo(8);}
}
static void erase_input(unsigned len) {
  while(len--){ui_put(8);ui_put(' ');ui_put(8);}
}
static void read_line(unsigned text,unsigned parse) {
  console_input_begin();if(version==3)status();unsigned len=0,max=rb(text),escape=0,draft_length=0,recalled=0;
  unsigned offset=version==5?2:1;
  if(version==5){max++;len=rb(text+1);if(len>=max)fatal("input preload length");}
  char draft[256];
  if(version==3&&max>120)max=120;
  while(1) { int c=console_get();
    // Decode terminal CSI and SS3 keys, consuming unsupported sequences whole.
    if(escape==1){escape=(c=='['||c=='O')?2:0;continue;}
    if(escape==2){
      if(c>=0x40&&c<=0x7e){escape=0;if(c=='A')c=KEY_UP;else if(c=='B')c=KEY_DOWN;else continue;}
      else {if(c<0x20||c>0x3f)escape=0;continue;}
    }
    if(c==27){escape=1;continue;}
    if(c==KEY_UP||c==KEY_DOWN){
      if(c==KEY_UP){
        if(recalled||!last_length)continue;
        draft_length=len;for(unsigned i=0;i<len;i++)draft[i]=rb(text+offset+i);
      }else if(!recalled)continue;
      erase_story_input(len);
      const char *source=c==KEY_UP?last_command:draft;
      len=c==KEY_UP?last_length:draft_length;
      if(len>=max)len=max?max-1:0;
      for(unsigned i=0;i<len;i++){wb(text+offset+i,source[i]);input_echo(source[i]);}
      recalled=c==KEY_UP;continue;
    }
    if(c=='\r'||c=='\n')break;
    if(c==8||c==127){if(len){len--;erase_story_input(1);}continue;}
    if(c>=32&&c<127&&len+1<max){if(c>='A'&&c<='Z')c+=32;wb(text+offset+len++,c);input_echo(c);}
  }
  if(len){last_length=len;for(unsigned i=0;i<len;i++)last_command[i]=rb(text+offset+i);}
  input_echo('\n');if(version==5)wb(text+1,len);else wb(text+offset+len,0);tokenize(text,parse,dictionary,0);
}
static uint32_t hash_bytes(uint32_t hash,const uint8_t *p,unsigned n) { while(n--)hash=(hash^*p++)*16777619U;return hash; }
static uint32_t get32(const uint8_t *p) { return p[0]|(p[1]<<8)|(p[2]<<16)|((uint32_t)p[3]<<24); }
static void put32(uint8_t *p,uint32_t n) { for(unsigned i=0;i<4;i++)p[i]=n>>(8*i); }
static unsigned snapshot_base_size(void) { return sizeof(vm)+dynamic_size; }
static unsigned snapshot_size(void) { return snapshot_base_size()+(version==5?sizeof(streams)+sizeof(screen):((streams.depth||!streams.screen)?sizeof(streams):0)); }
static uint8_t snapshot_byte(unsigned off) {
  if(version==5&&off>=snapshot_base_size()+sizeof(streams))return ((const uint8_t*)&screen)[off-snapshot_base_size()-sizeof(streams)];
  if(off>=snapshot_base_size())return ((const uint8_t*)&streams)[off-snapshot_base_size()];
  return off<sizeof(vm)?((const uint8_t*)&vm)[off]:dynamic_memory[off-sizeof(vm)];
}
static void restore_byte(unsigned off,uint8_t value) {
  if(version==5&&off>=snapshot_base_size()+sizeof(streams)){((uint8_t*)&screen)[off-snapshot_base_size()-sizeof(streams)]=value;return;}
  if(off>=snapshot_base_size()){((uint8_t*)&streams)[off-snapshot_base_size()]=value;return;}
  if(off<sizeof(vm))((uint8_t*)&vm)[off]=value;else dynamic_memory[off-sizeof(vm)]=value;
}
static int save_header(unsigned bank,uint32_t *generation,uint32_t *hash) {
  if(!storage_read(STORAGE_SAVE_A+bank,0,sector_buf))return 0;
  unsigned size=get32(sector_buf+8);
  if(get32(sector_buf)!=SAVE_MAGIC||(version==5?size!=snapshot_base_size()+sizeof(streams)+sizeof(screen):(size!=snapshot_base_size()&&size!=snapshot_base_size()+sizeof(streams))))return 0;
  for(unsigned i=0;i<STORAGE_ID_BYTES;i++)if(sector_buf[16+i]!=storage_story_id()[i])return 0;
  *generation=get32(sector_buf+4);*hash=get32(sector_buf+12);return 1;
}
/* Slot menus live outside the VM/parser state and command history. */
static int menu_line(char *text,unsigned capacity) {
  unsigned len=0,escape=0,overflow=0;
  for(;;) {
    int c=console_get();
    if(escape){if(escape==1&&(c=='['||c=='O'))escape=2;else if(c>=0x40&&c<=0x7e)escape=0;continue;}
    if(c==27){escape=1;continue;}
    if(c=='\r'||c=='\n'){ui_put('\n');text[len]=0;return !overflow;}
    if(c==8||c==127){if(overflow)overflow--;else if(len){len--;erase_input(1);}continue;}
    if(c>=32&&c<127){if(len+1<capacity&&!overflow){text[len++]=(char)c;ui_put(c);}else overflow++;}
  }
}
static void menu_number(unsigned n) { if(n>=10)menu_number(n/10);ui_put('0'+n%10); }
static int choose_save_slot_inner(int saving) {
  unsigned count=storage_game_slots();if(!count)return 0;
  if(count==1)return storage_select_save(0); /* Existing cards keep their flow. */
  console_story_flush();if(version==5)screen_flush();say(saving?"\nSave slots for ":"\nRestore slots for ");say(storage_story_name());say(":\n");
  unsigned occupied=0;
  for(unsigned slot=0;slot<count;slot++) {
    if(!storage_select_save(slot))return 0;
    uint32_t generation,hash;int used=save_header(0,&generation,&hash)|save_header(1,&generation,&hash);
    if(used)occupied|=1U<<slot;
    menu_number(slot+1);say(used?". Saved\n":". Empty\n");
  }
  for(;;) {
    say("Slot number [Enter=1, 0=cancel]: ");char line[16];
    if(!menu_line(line,sizeof(line))){say("Invalid slot number.\n");continue;}
    if((line[0]=='0'||line[0]=='q'||line[0]=='Q')&&!line[1]){say("Cancelled.\n");return 0;}
    unsigned slot=0,valid=1;
    for(unsigned i=0;line[i];i++){if(line[i]<'0'||line[i]>'9'){valid=0;break;}slot=slot*10+line[i]-'0';if(slot>count){valid=0;break;}}
    if(!line[0])slot=1;
    if(!valid||!slot||slot>count){say("Invalid slot number.\n");continue;}
    slot--;
    if(!saving&&!(occupied&(1U<<slot))){say("Slot is empty. Choose a saved slot or cancel.\n");continue;}
    if(saving&&(occupied&(1U<<slot))) {
      say("Overwrite slot ");menu_number(slot+1);say("? [y/N]: ");
      int valid_line=menu_line(line,sizeof(line));
      if(!valid_line||!((line[0]=='y'||line[0]=='Y')&&!line[1])){say("Overwrite cancelled.\n");continue;}
    }
    return storage_select_save(slot);
  }
}
static int choose_save_slot(int saving) {
  if(version!=5||storage_game_slots()==1)return choose_save_slot_inner(saving);
  unsigned old_window=screen.window;screen_flush();screen.window=0;
  int result=choose_save_slot_inner(saving);screen_flush();screen.window=old_window;
  display_move(screen.row[old_window],screen.col[old_window]);return result;
}
static int save_game(void) {
  console_story_flush();if(version==5)screen_flush();
  if(!choose_save_slot(1))return 0;
  uint32_t gen[2]={0,0},h;int ok[2];for(unsigned i=0;i<2;i++)ok[i]=save_header(i,&gen[i],&h);
  unsigned newest=ok[1]&&(!ok[0]||(int32_t)(gen[1]-gen[0])>0);unsigned target=(ok[0]||ok[1])?newest^1:0;
  uint32_t hash=2166136261U;unsigned size=snapshot_size();
  for(unsigned offset=0;offset<size;offset+=512) {
    unsigned n=size-offset;if(n>512)n=512;
    for(unsigned j=0;j<512;j++)sector_buf[j]=j<n?snapshot_byte(offset+j):0;
    hash=hash_bytes(hash,sector_buf,n);
    if(!storage_write(target,1+offset/512,sector_buf))return 0;
  }
  for(unsigned i=0;i<512;i++)sector_buf[i]=0;
  put32(sector_buf,SAVE_MAGIC);put32(sector_buf+4,gen[newest]+1);put32(sector_buf+8,size);
  put32(sector_buf+12,hash);
  for(unsigned i=0;i<STORAGE_ID_BYTES;i++)sector_buf[16+i]=storage_story_id()[i];
  return storage_write(target,0,sector_buf);
}
static int restore_game(void) {
  console_story_flush();if(version==5)screen_flush();
  if(!choose_save_slot(0))return 0;
  uint32_t gen[2]={0,0},hash[2];int ok[2];for(unsigned i=0;i<2;i++)ok[i]=save_header(i,&gen[i],&hash[i]);
  unsigned newest=ok[1]&&(!ok[0]||(int32_t)(gen[1]-gen[0])>0);
  for(unsigned pass=0;pass<2;pass++) {
    unsigned bank=newest^pass;if(!ok[bank])continue;
    uint32_t sum=2166136261U;
    /* Check entire snapshot before changing the live VM. */
    if(!storage_read(STORAGE_SAVE_A+bank,0,sector_buf))continue;
    unsigned size=get32(sector_buf+8);
    int valid=1;for(unsigned off=0;off<size;off+=512){if(!storage_read(STORAGE_SAVE_A+bank,1+off/512,sector_buf)){valid=0;break;}
      unsigned n=size-off;if(n>512)n=512;sum=hash_bytes(sum,sector_buf,n);}
    if(!valid||sum!=hash[bank])continue;
    reset_streams();
    for(unsigned off=0;off<size;off+=512){if(!storage_read(STORAGE_SAVE_A+bank,1+off/512,sector_buf))fatal("restore SD read");
      for(unsigned j=0;j<512&&off+j<size;j++)restore_byte(off+j,sector_buf[j]);}
    if(streams.depth>16||streams.screen>1)fatal("invalid saved output streams");
    dynamic_memory[17]&=~1;
    undo_size=0;output_window=0;if(version==5){if(screen.window>1||screen.split>31||screen.row[0]>31||screen.row[1]>31||screen.col[0]>79||screen.col[1]>79)fatal("invalid saved screen");display_move(screen.row[screen.window],screen.col[screen.window]);}return 1;
  }
  return 0;
}
static void restart(void) {
  for(unsigned i=0;i<sizeof(vm);i++)((uint8_t*)&vm)[i]=0;
  dynamic_size=0;dynamic_size=(story(14)<<8)|story(15);
  version=story(0);if(dynamic_size<64||(version!=3&&version!=5))fatal("incompatible story memory");
  for(unsigned i=0;i<dynamic_size;i++)dynamic_memory[i]=story(i);
  objects=rw(10);globals=rw(12);dictionary=rw(8);abbreviations=rw(24);vm.pc=rw(6);vm.random=0x12345678;
  dynamic_memory[1]=version==5?0x10:(dynamic_memory[1]&~0x70); /* status available, split unavailable, variable pitch unavailable */
  dynamic_memory[17]&=~1; /* No transcript file backend. */
  reset_streams();
  if(version==5){wb(30,6);wb(31,'A');wb(32,32);wb(33,79);ww(34,79);ww(36,32);wb(38,1);wb(39,1);wb(44,2);wb(45,9);ww(50,0x0100);wb(17,(rb(17)&~0xe8)|16);}
  output_window=0;split_lines=0;stopped=0;undo_size=0;if(version==5){screen_reset();screen.pc_graphics=story(2)==0&&story(3)==57&&story(18)=='8'&&story(19)=='7'&&story(20)=='1'&&story(21)=='2'&&story(22)=='2'&&story(23)=='1'&&story(28)==0xc5&&story(29)==0xad;}
}
static uint16_t operand(unsigned type) { if(type==0)return fetchw();unsigned b=fetch();return type==2?variable(b,0):b; }
static void call(uint16_t *args,unsigned count,int discard) {
  unsigned dest=discard?0:fetch(),x=args[0];if(!x){if(!discard)setvar(dest,0,0);return;}
  if(vm.depth+1==FRAME_MAX)fatal("call depth");struct frame *f=&vm.frames[++vm.depth];
  f->pc=vm.pc;f->base=vm.sp;f->result=dest;f->pad=(discard?128:0)|(count-1);vm.pc=packed(x);
  unsigned locals=fetch();if(locals>15)fatal("local count");
  for(unsigned i=0;i<15;i++)f->locals[i]=i<locals&&version==3?fetchw():0;
  for(unsigned i=1;i<count&&i<=locals;i++)f->locals[i-1]=args[i];
}
static void execute(void) {
  uint16_t a[8]={0};unsigned n=0,op=fetch(),group;
  if(op==190&&version==5){group=4;op=fetch();unsigned types=fetch();for(int i=6;i>=0;i-=2){unsigned t=(types>>i)&3;if(t==3)break;a[n++]=operand(t);}}
  else if(op<128){group=2;a[n++]=operand(op&64?2:1);a[n++]=operand(op&32?2:1);op&=31;}
  else if(op<176){group=1;a[n++]=operand((op>>4)&3);op&=15;}
  else if(op<192){group=0;op&=15;}
  else {group=op<224?2:3;op&=31;unsigned types=fetch(),second=255;if(group==3&&(op==12||op==26))second=fetch();unsigned all=(types<<8)|second;for(int i=14;i>=0;i-=2){unsigned t=(all>>i)&3;if(t==3)break;a[n++]=operand(t);}}
  uint16_t x=a[0],y=a[1];int16_t sx=x,sy=y;uint32_t p;unsigned v;
  if(group==0)switch(op) {
    case 0:ret(1);break;case 1:ret(0);break;
    case 2:vm.pc=ztext(vm.pc,0);break;case 3:vm.pc=ztext(vm.pc,0);zout('\n');ret(1);break;
    case 4:break;case 5:branch(save_game());break;case 6:if(restore_game())branch(1);else branch(0);break;
    case 7:restart();break;case 8:ret(pop());break;case 9:if(version==5)store(vm.depth);else pop();break;case 10:stopped=1;break;
    case 11:zout('\n');break;case 12:if(version==3)status();break;
    case 13:{unsigned sum=0;for(unsigned i=64;i<(rw(26)?packed(rw(26)):storage_story_size());i++)sum+=story(i);branch((uint16_t)sum==rw(28));break;}
    case 15:branch(1);break;default:fatal("unknown 0OP");
  }
  else if(group==1)switch(op) {
    case 0:branch(!x);break;case 1:v=sibling(x);store(v);branch(v);break;case 2:v=child(x);store(v);branch(v);break;
    case 3:store(parent(x));break;case 4:store(!x?0:version==3?1+(rb(x-1)>>5):(rb(x-1)&128)?((rb(x-1)&63)?rb(x-1)&63:64):((rb(x-1)&64)?2:1));break;
    case 5:setvar(x,variable(x,1)+1,1);break;case 6:setvar(x,variable(x,1)-1,1);break;
    case 7:ztext(x,0);break;case 8:call(a,n,0);break;case 9:remove_obj(x);break;case 10:if(rb(prop_table(x)))ztext(prop_table(x)+1,0);break;
    case 11:ret(x);break;case 12:vm.pc+=sx-2;break;case 13:ztext(packed(x),0);break;
    case 14:store(variable(x,1));break;case 15:if(version==5)call(a,n,1);else store(~x);break;default:fatal("unknown 1OP");
  }
  else if(group==2)switch(op) {
    case 1:v=0;for(unsigned i=1;i<n;i++)v|=x==a[i];branch(v);break;
    case 2:branch(sx<sy);break;case 3:branch(sx>sy);break;
    case 4:v=variable(x,1)-1;setvar(x,v,1);branch((int16_t)v<sy);break;
    case 5:v=variable(x,1)+1;setvar(x,v,1);branch((int16_t)v>sy);break;
    case 6:branch(parent(x)==y);break;case 7:branch((x&y)==y);break;case 8:store(x|y);break;case 9:store(x&y);break;
    case 10:branch(rb(obj(x)+y/8)&(128>>(y&7)));break;
    case 11:p=obj(x)+y/8;wb(p,rb(p)|(128>>(y&7)));break;case 12:p=obj(x)+y/8;wb(p,rb(p)&~(128>>(y&7)));break;
    case 13:setvar(x,y,1);break;case 14:remove_obj(x);set_relation(x,0,y);set_relation(x,1,child(y));set_relation(y,2,x);break;
    case 15:store(rw(x+2U*y));break;case 16:store(rb(x+(uint32_t)y));break;
    case 17:p=prop_find(x,y);store(p?(prop_length(p)==1?rb(p+prop_header(p)):rw(p+prop_header(p))):rw(objects+2*(y-1)));break;
    case 18:p=prop_find(x,y);store(p?p+prop_header(p):0);break;
    case 19:p=y?prop_find(x,y):0;if(y&&!p)fatal("next property missing");p=y?prop_next(p):prop_start(x);store(prop_number(p));break;
    case 20:store(x+y);break;case 21:store(x-y);break;case 22:store(sx*sy);break;
    case 23:if(!y)fatal("division by zero");store(sx/sy);break;case 24:if(!y)fatal("division by zero");store(sx%sy);break;
    case 25:call(a,n,0);break;case 26:call(a,n,1);break;case 27:if(version==5)screen_flush();break;
    case 28:if(y>vm.depth)fatal("invalid catch frame");vm.depth=y;ret(x);break;
    default:fatal("unknown 2OP");
  }
  else if(group==3)switch(op) {
    case 0:case 12:call(a,n,0);break;
    case 1:ww(x+2U*y,a[2]);break;case 2:wb(x+(uint32_t)y,a[2]);break;
    case 3:p=prop_find(x,y);if(!p)fatal("put missing property");if(prop_length(p)==1)wb(p+prop_header(p),a[2]);else ww(p+prop_header(p),a[2]);break;
    case 4:read_line(x,y);if(version==5)store(13);break;case 5:zout(x);break;case 6:number(sx);break;
    case 7:if(sx<=0){vm.random=sx?-(int)sx:0x12345678;store(0);}else{vm.random^=vm.random<<13;vm.random^=vm.random>>17;vm.random^=vm.random<<5;store(vm.random%x+1);}break;
    case 8:push(x);break;case 9:setvar(x,pop(),1);break;
    case 10:console_story_flush();if(version==5)screen_flush();split_lines=x;if(version==5)screen_split(x);break;case 11:console_story_flush();if(version==5)screen_flush();output_window=x&&split_lines;if(version==5)screen_window(x);break;
    case 19:output_stream(sx,y,n);break;
    case 13:screen_erase(sx);break;case 14:if(x==1)screen_erase_line();break;case 15:screen_cursor(x,y);break;
    case 16:screen_flush();ww(x,screen.row[screen.window]+1);ww(x+2,screen.col[screen.window]+1);break;
    case 17:screen_style(x);break;case 18:screen_flush();screen.buffer=x!=0;break;case 20:case 21:break;
    case 22:
      v=console_get();if(v==27){unsigned c=console_get();if(c=='['||c=='O'){do{c=console_get();}while(c>=0x30&&c<0x40);v=c=='A'?129:c=='B'?130:c=='D'?131:c=='C'?132:27;}}
      store(v==10?13:v==KEY_UP?129:v==KEY_DOWN?130:v);break;
    case 23:{unsigned form=n>3?a[3]:0x82;v=0;for(unsigned i=0;i<a[2];i++){p=y+i*(form&127);if((form&128?rw(p):rb(p))==x){v=p;break;}}store(v);branch(v);break;}
    case 24:store(~x);break;case 25:case 26:call(a,n,1);break;
    case 27:tokenize(x,y,n>2&&a[2]?a[2]:dictionary,n>3?a[3]:0);break;
    case 28:{uint8_t key[6];encode_word(x+a[2],y,key);for(unsigned i=0;i<6;i++)wb(a[3]+i,key[i]);break;}
    case 29:{int size=(int16_t)a[2];unsigned len=size<0?-size:size;if(!y){for(unsigned i=0;i<len;i++)wb(x+i,0);}else if(size>=0&&y>x){while(len){len--;wb(y+len,rb(x+len));}}else for(unsigned i=0;i<len;i++)wb(y+i,rb(x+i));break;}
    case 30:{unsigned height=n>2?a[2]:1,skip=n>3?a[3]:0;screen_flush();unsigned start_col=screen.col[screen.window];for(unsigned r=0;r<height;r++){if(r){zout('\n');screen_flush();screen.col[screen.window]=start_col;}for(unsigned c=0;c<y;c++)zout(rb(x+r*(y+skip)+c));}break;}
    case 31:branch((vm.frames[vm.depth].pad&127)>=x);break;
    default:fatal("unknown VAR");
  }
  else switch(op) {
    case 0:if(n){store(0);break;}v=save_game();store(v);break;
    case 1:if(n){store(0);break;}if(restore_game())store(2);else store(0);break;
    case 2:store(sy>=0?(y<16?x<<y:0):(sy>-16?x>>-sy:0));break;
    case 3:store(sy>=0?(y<16?x<<y:0):(sy>-16?sx>>-sy:(sx<0?65535:0)));break;
    case 4:screen_flush();v=screen.font;if(x==1||x==4){screen.font=x;store(v);}else store(x?0:v);break;
    case 9:undo_size=snapshot_size();for(unsigned i=0;i<undo_size;i++)undo_image[i]=snapshot_byte(i);store(1);break;
    case 10:if(!undo_size){store(0);break;}for(unsigned i=0;i<undo_size;i++)restore_byte(i,undo_image[i]);undo_size=0;store(2);display_move(screen.row[screen.window],screen.col[screen.window]);break;
    case 11:zout(x>=32&&x<=126?x:'?');break;case 12:store(x>=32&&x<=126?3:0);break;
    default:fatal("unknown EXT");
  }
}
int main(void) {
  platform_init();say("SD story and persistent SAVE / RESTORE\n\n");
  if(!storage_init())fatal("requires FAT16/FAT32 and a compatible V3/V5 DAT in /ZORK");
  for(unsigned off=0;off<storage_story_size();off+=512) {
    if(!storage_read(STORAGE_STORY,off/512,sector_buf))fatal("SD story read");
    unsigned n=storage_story_size()-off;if(n>512)n=512;
    for(unsigned i=0;i<n;i++)story_image[off+i]=sector_buf[i];
  }
  restart();while(!stopped)execute();console_story_flush();if(version==5)screen_flush();say("\nGame stopped. Press reset to play again.\n");return 0;
}
