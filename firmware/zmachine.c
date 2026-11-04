/* Dedicated version 3 Z-machine interpreter. All story addresses are byte addresses. */
#include "platform.h"
#include "storage.h"
#define STACK_MAX 2048
#define FRAME_MAX 96
#define SAVE_MAGIC STORAGE_SAVE_MAGIC
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
typedef char snapshot_fits_bank[(sizeof(struct machine)+sizeof(streams)+V3_DYNAMIC_MAX+511)/512+1<=STORAGE_BANK_SECTORS?1:-1];
#ifdef HOST
static uint8_t story_image[V3_STORY_MAX], dynamic_memory[65536];
#else
/* Pristine image retained for restart/verify; mutable image in a separate region. */
#define story_image ((volatile uint8_t *)0x30000000U)
#define dynamic_memory ((volatile uint8_t *)0x30020000U)
#endif
static uint8_t sector_buf[512];
static uint16_t dynamic_size, objects, globals, dictionary, abbreviations;
static int stopped, output_window, split_lines;
static const char alphabet[] = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ \n0123456789.,!?_#'\"/\\-:()";
static void say(const char *s) { while (*s) console_put(*s++); }
void fatal(const char *s) { console_story_flush();say("\nCORE ERROR: "); say(s); say("\n"); stopped=1;
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
  vm.sp=f->base;vm.pc=f->pc;unsigned dest=f->result;vm.depth--;setvar(dest,v,0);
}
static void branch(int condition) {
  unsigned b=fetch();int offset=b&63;
  if(!(b&64)) {offset=(offset<<8)|fetch();if(offset&8192)offset-=16384;}
  if(!!condition == !!(b&128)) { if(offset<2 && offset>=0)ret(offset);else vm.pc+=offset-2; }
}
static uint32_t obj(unsigned n) { if(!n||n>255)fatal("object number");return objects+62+9*(n-1); }
static unsigned parent(unsigned n) { return n?rb(obj(n)+4):0; }
static unsigned sibling(unsigned n) { return n?rb(obj(n)+5):0; }
static unsigned child(unsigned n) { return n?rb(obj(n)+6):0; }
static void remove_obj(unsigned n) {
  unsigned p=parent(n);if(!p)return;
  unsigned c=child(p);
  if(c==n)wb(obj(p)+6,sibling(n));
  else { while(c&&sibling(c)!=n)c=sibling(c);if(!c)fatal("broken object tree");wb(obj(c)+5,sibling(n)); }
  wb(obj(n)+4,0);wb(obj(n)+5,0);
}
static uint32_t prop_start(unsigned n) { uint32_t a=rw(obj(n)+7);return a+1+2*rb(a); }
static uint32_t prop_find(unsigned n,unsigned p) {
  uint32_t a=prop_start(n);while(rb(a) && (rb(a)&31)>p)a+=2+(rb(a)>>5);
  return (rb(a)&31)==p ? a : 0;
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
  } else if(streams.screen&&!output_window)console_story_put(c==13?'\n':c);
}
static void output_stream(int16_t number,unsigned table,unsigned operands) {
  /* Flush at the selection boundary, before changing the screen route. */
  console_story_flush();
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
      else { zout(alphabet[shift*26+z-6]);shift=0; }
    }
    if(w&0x8000)return a;
  }
}
static void number(int16_t n) {
  unsigned v=n<0 ? -(int)n : n;char b[6];unsigned len=0;
  if(n<0)zout('-');do{b[len++]='0'+v%10;v/=10;}while(v);while(len)zout(b[--len]);
}
static void encode_word(uint32_t a,unsigned len,uint8_t *encoded) {
  unsigned z[6],count=0;
  for(unsigned i=0;i<len&&count<6;i++) {
    int c=rb(a+i);unsigned index=78;
    for(unsigned j=0;j<78;j++)if(alphabet[j]==c){index=j;break;}
    if(index<26)z[count++]=index+6;
    else if(index<78){z[count++]=index<52?4:5;if(count<6)z[count++]=index%26+6;}
    else {z[count++]=5;if(count<6)z[count++]=6;if(count<6)z[count++]=c>>5;if(count<6)z[count++]=c&31;}
  }
  while(count<6)z[count++]=5;
  unsigned w=(z[0]<<10)|(z[1]<<5)|z[2];encoded[0]=w>>8;encoded[1]=w;
  w=0x8000|(z[3]<<10)|(z[4]<<5)|z[5];encoded[2]=w>>8;encoded[3]=w;
}
static int separator(int c) { for(unsigned i=0;i<rb(dictionary);i++)if(rb(dictionary+1+i)==c)return 1;return 0; }
static void tokenize(unsigned text,unsigned parse) {
  unsigned a=text+1,count=0,limit=rb(parse);unsigned d=dictionary+1+rb(dictionary);
  unsigned entrylen=rb(d),entries=rw(d+1),start=d+3;
  while(rb(a)&&count<limit) {
    if(rb(a)==' '){a++;continue;}
    unsigned word=a;int sep=separator(rb(a++));
    if(!sep)while(rb(a)&&rb(a)!=' '&&!separator(rb(a)))a++;
    unsigned len=a-word;uint8_t key[4];encode_word(word,len,key);
    int lo=0,hi=entries-1;unsigned found=0;
    while(lo<=hi){int mid=(lo+hi)/2;unsigned at=start+mid*entrylen;int cmp=0;
      for(unsigned k=0;k<4;k++){cmp=(int)key[k]-rb(at+k);if(cmp)break;}
      if(!cmp){found=at;break;}if(cmp<0)hi=mid-1;else lo=mid+1;
    }
    unsigned p=parse+2+4*count++;ww(p,found);wb(p+2,len);wb(p+3,word-text);
  }
  wb(parse+1,count);
}
static void status(void) {
  console_story_flush();
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
static char last_command[120];
static unsigned last_length;
static void input_echo(int c) { if(streams.screen&&!streams.depth)console_put(c); }
static void erase_story_input(unsigned len) {
  while(len--){input_echo(8);input_echo(' ');input_echo(8);}
}
static void erase_input(unsigned len) {
  while(len--){console_put(8);console_put(' ');console_put(8);}
}
static void read_line(unsigned text,unsigned parse) {
  status();unsigned len=0,max=rb(text),escape=0,draft_length=0,recalled=0;
  char draft[120];
  if(max>120)max=120;
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
        draft_length=len;for(unsigned i=0;i<len;i++)draft[i]=rb(text+1+i);
      }else if(!recalled)continue;
      erase_story_input(len);
      const char *source=c==KEY_UP?last_command:draft;
      len=c==KEY_UP?last_length:draft_length;
      if(len>=max)len=max?max-1:0;
      for(unsigned i=0;i<len;i++){wb(text+1+i,source[i]);input_echo(source[i]);}
      recalled=c==KEY_UP;continue;
    }
    if(c=='\r'||c=='\n')break;
    if(c==8||c==127){if(len){len--;erase_story_input(1);}continue;}
    if(c>=32&&c<127&&len+1<max){if(c>='A'&&c<='Z')c+=32;wb(text+1+len++,c);input_echo(c);}
  }
  if(len){last_length=len;for(unsigned i=0;i<len;i++)last_command[i]=rb(text+1+i);}
  input_echo('\n');wb(text+1+len,0);tokenize(text,parse);
}
static uint32_t hash_bytes(uint32_t hash,const uint8_t *p,unsigned n) { while(n--)hash=(hash^*p++)*16777619U;return hash; }
static uint32_t get32(const uint8_t *p) { return p[0]|(p[1]<<8)|(p[2]<<16)|((uint32_t)p[3]<<24); }
static void put32(uint8_t *p,uint32_t n) { for(unsigned i=0;i<4;i++)p[i]=n>>(8*i); }
static unsigned snapshot_base_size(void) { return sizeof(vm)+dynamic_size; }
static unsigned snapshot_size(void) { return snapshot_base_size()+((streams.depth||!streams.screen)?sizeof(streams):0); }
static uint8_t snapshot_byte(unsigned off) {
  if(off>=snapshot_base_size())return ((const uint8_t*)&streams)[off-snapshot_base_size()];
  return off<sizeof(vm)?((const uint8_t*)&vm)[off]:dynamic_memory[off-sizeof(vm)];
}
static void restore_byte(unsigned off,uint8_t value) {
  if(off>=snapshot_base_size()){((uint8_t*)&streams)[off-snapshot_base_size()]=value;return;}
  if(off<sizeof(vm))((uint8_t*)&vm)[off]=value;else dynamic_memory[off-sizeof(vm)]=value;
}
static int save_header(unsigned bank,uint32_t *generation,uint32_t *hash) {
  if(!storage_read(STORAGE_SAVE_A+bank,0,sector_buf))return 0;
  unsigned size=get32(sector_buf+8);
  if(get32(sector_buf)!=SAVE_MAGIC||(size!=snapshot_base_size()&&size!=snapshot_base_size()+sizeof(streams)))return 0;
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
    if(c=='\r'||c=='\n'){console_put('\n');text[len]=0;return !overflow;}
    if(c==8||c==127){if(overflow)overflow--;else if(len){len--;erase_input(1);}continue;}
    if(c>=32&&c<127){if(len+1<capacity&&!overflow){text[len++]=(char)c;console_put(c);}else overflow++;}
  }
}
static void menu_number(unsigned n) { if(n>=10)menu_number(n/10);console_put('0'+n%10); }
static int choose_save_slot(int saving) {
  unsigned count=storage_game_slots();if(!count)return 0;
  if(count==1)return storage_select_save(0); /* Existing cards keep their flow. */
  console_story_flush();say(saving?"\nSave slots for ":"\nRestore slots for ");say(storage_story_name());say(":\n");
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
static int save_game(void) {
  console_story_flush();
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
  console_story_flush();
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
    output_window=0;return 1;
  }
  return 0;
}
static void restart(void) {
  for(unsigned i=0;i<sizeof(vm);i++)((uint8_t*)&vm)[i]=0;
  dynamic_size=0;dynamic_size=(story(14)<<8)|story(15);
  if(dynamic_size<64||story(0)!=3)fatal("incompatible V3 story memory");
  for(unsigned i=0;i<dynamic_size;i++)dynamic_memory[i]=story(i);
  objects=rw(10);globals=rw(12);dictionary=rw(8);abbreviations=rw(24);vm.pc=rw(6);vm.random=0x12345678;
  dynamic_memory[1]=(dynamic_memory[1]&~0x70); /* status available, split unavailable, variable pitch unavailable */
  dynamic_memory[17]&=~1; /* No transcript file backend. */
  reset_streams();
  output_window=0;split_lines=0;stopped=0;
}
static uint16_t operand(unsigned type) { if(type==0)return fetchw();unsigned b=fetch();return type==2?variable(b,0):b; }
static void execute(void) {
  uint16_t a[4]={0,0,0,0};unsigned n=0,op=fetch(),group;
  if(op<128){group=2;a[n++]=operand(op&64?2:1);a[n++]=operand(op&32?2:1);op&=31;}
  else if(op<176){group=1;a[n++]=operand((op>>4)&3);op&=15;}
  else if(op<192){group=0;op&=15;}
  else {group=op<224?2:3;op&=31;unsigned types=fetch();for(int i=6;i>=0;i-=2){unsigned t=(types>>i)&3;if(t==3)break;a[n++]=operand(t);}}
  uint16_t x=a[0],y=a[1];int16_t sx=x,sy=y;uint32_t p;unsigned v;
  if(group==0)switch(op) {
    case 0:ret(1);break;case 1:ret(0);break;
    case 2:vm.pc=ztext(vm.pc,0);break;case 3:vm.pc=ztext(vm.pc,0);zout('\n');ret(1);break;
    case 4:break;case 5:branch(save_game());break;case 6:if(restore_game())branch(1);else branch(0);break;
    case 7:restart();break;case 8:ret(pop());break;case 9:pop();break;case 10:stopped=1;break;
    case 11:zout('\n');break;case 12:status();break;
    case 13:{unsigned sum=0;for(unsigned i=64;i<(rw(26)?2U*rw(26):storage_story_size());i++)sum+=story(i);branch((uint16_t)sum==rw(28));break;}
    default:fatal("unknown 0OP");
  }
  else if(group==1)switch(op) {
    case 0:branch(!x);break;case 1:v=sibling(x);store(v);branch(v);break;case 2:v=child(x);store(v);branch(v);break;
    case 3:store(parent(x));break;case 4:store(x?1+(rb(x-1)>>5):0);break;
    case 5:setvar(x,variable(x,1)+1,1);break;case 6:setvar(x,variable(x,1)-1,1);break;
    case 7:ztext(x,0);break;case 9:remove_obj(x);break;case 10:ztext(rw(obj(x)+7)+1,0);break;
    case 11:ret(x);break;case 12:vm.pc+=sx-2;break;case 13:ztext(2U*x,0);break;
    case 14:store(variable(x,1));break;case 15:store(~x);break;default:fatal("unknown 1OP");
  }
  else if(group==2)switch(op) {
    case 1:v=0;for(unsigned i=1;i<n;i++)v|=x==a[i];branch(v);break;
    case 2:branch(sx<sy);break;case 3:branch(sx>sy);break;
    case 4:v=variable(x,1)-1;setvar(x,v,1);branch((int16_t)v<sy);break;
    case 5:v=variable(x,1)+1;setvar(x,v,1);branch((int16_t)v>sy);break;
    case 6:branch(parent(x)==y);break;case 7:branch((x&y)==y);break;case 8:store(x|y);break;case 9:store(x&y);break;
    case 10:branch(rb(obj(x)+y/8)&(128>>(y&7)));break;
    case 11:p=obj(x)+y/8;wb(p,rb(p)|(128>>(y&7)));break;case 12:p=obj(x)+y/8;wb(p,rb(p)&~(128>>(y&7)));break;
    case 13:setvar(x,y,1);break;case 14:remove_obj(x);wb(obj(x)+4,y);wb(obj(x)+5,child(y));wb(obj(y)+6,x);break;
    case 15:store(rw(x+2U*y));break;case 16:store(rb(x+(uint32_t)y));break;
    case 17:p=prop_find(x,y);store(p?(rb(p)<32?rb(p+1):rw(p+1)):rw(objects+2*(y-1)));break;
    case 18:p=prop_find(x,y);store(p?p+1:0);break;
    case 19:p=y?prop_find(x,y):0;if(y&&!p)fatal("next property missing");p=y?p+2+(rb(p)>>5):prop_start(x);store(rb(p)&31);break;
    case 20:store(x+y);break;case 21:store(x-y);break;case 22:store(sx*sy);break;
    case 23:if(!y)fatal("division by zero");store(sx/sy);break;case 24:if(!y)fatal("division by zero");store(sx%sy);break;
    default:fatal("unknown 2OP");
  }
  else switch(op) {
    case 0: {
      unsigned dest=fetch();if(!x){setvar(dest,0,0);break;}
      if(vm.depth+1==FRAME_MAX)fatal("call depth");struct frame *f=&vm.frames[++vm.depth];
      f->pc=vm.pc;f->base=vm.sp;f->result=dest;vm.pc=2U*x;unsigned locals=fetch();if(locals>15)fatal("local count");
      for(unsigned i=0;i<locals;i++)f->locals[i]=fetchw();for(unsigned i=1;i<n&&i<=locals;i++)f->locals[i-1]=a[i];break;
    }
    case 1:ww(x+2U*y,a[2]);break;case 2:wb(x+(uint32_t)y,a[2]);break;
    case 3:p=prop_find(x,y);if(!p)fatal("put missing property");if(rb(p)<32)wb(p+1,a[2]);else ww(p+1,a[2]);break;
    case 4:read_line(x,y);break;case 5:zout(x);break;case 6:number(sx);break;
    case 7:if(sx<=0){vm.random=sx?-(int)sx:0x12345678;store(0);}else{vm.random^=vm.random<<13;vm.random^=vm.random>>17;vm.random^=vm.random<<5;store(vm.random%x+1);}break;
    case 8:push(x);break;case 9:setvar(x,pop(),1);break;
    case 10:console_story_flush();split_lines=x;break;case 11:console_story_flush();output_window=x&&split_lines;break;
    case 19:output_stream(sx,y,n);break;
    case 20:break;case 21:break;default:fatal("unknown VAR");
  }
}
int main(void) {
  platform_init();say("SD story and persistent SAVE / RESTORE\n\n");
  if(!storage_init())fatal("requires FAT16/FAT32 and a compatible V3 DAT in /ZORK");
  for(unsigned off=0;off<storage_story_size();off+=512) {
    if(!storage_read(STORAGE_STORY,off/512,sector_buf))fatal("SD story read");
    unsigned n=storage_story_size()-off;if(n>512)n=512;
    for(unsigned i=0;i<n;i++)story_image[off+i]=sector_buf[i];
  }
  restart();while(!stopped)execute();console_story_flush();say("\nGame stopped. Press reset to play again.\n");return 0;
}
