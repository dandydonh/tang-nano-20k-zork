/* FAT16/FAT32 V3/V5 story discovery. Only the selected save-slot data is writable.
 * No filesystem metadata writes, allocation or hot swapping. */
#include "platform.h"
#include "storage.h"
#define STORY_SECTORS (V3_FILE_MAX/512U)
#define SAVE_SECTORS STORAGE_BANK_SECTORS
#define MAP_SECTORS (STORY_SECTORS+2*SAVE_SECTORS)
#define DIR_SECTOR_LIMIT 256U
#define DIR_EXTENTS 32U
#define STORY_LIMIT STORAGE_STORY_LIMIT
static uint32_t sector_map[MAP_SECTORS];
#ifdef HOST
static uint32_t save_headers[STORAGE_SAVE_SLOTS*2*STORAGE_GAME_SLOTS];
#else
/* After the 0x30060000..0x3007ffff undo bank; populated before use. */
#define save_headers ((volatile uint32_t *)0x30080000U)
#endif
static uint8_t buf[512], fat_buf[512], story_id[STORAGE_ID_BYTES];
static uint32_t fat_cached_sector, fat_start, data_start, cluster_count, root_start, root_sectors;
static uint32_t story_bytes;
static uint32_t story_first_sector,story_last_sector;
static unsigned sectors_per_cluster, fat32, ready, saves_ready, story_sectors, story_count, chosen, save_slots;
static unsigned game_slots, save_owner, mapped_game_slot;
struct entry { uint32_t cluster, size; unsigned attr; };
struct candidate { struct entry file; char name[13]; uint8_t version; const char *error; };
static struct candidate stories[STORY_LIMIT];
static struct entry pool;
static struct { uint32_t start, size; } directories[DIR_EXTENTS];
static unsigned directory_count;
static uint32_t u16(const uint8_t *p) { return p[0]|((uint32_t)p[1]<<8); }
static uint32_t u32(const uint8_t *p) { return u16(p)|(u16(p+2)<<16); }
static unsigned be16(const uint8_t *p) { return ((unsigned)p[0]<<8)|p[1]; }
static void say(const char *p) { while(*p)console_put(*p++); }
static int equal(const uint8_t *a,const uint8_t *b,unsigned n) {
  while(n--)if(*a++!=*b++)return 0;return 1;
}
static int cluster_valid(uint32_t c) {
  return c>=2&&c-2<cluster_count&&c<(fat32?0x0ffffff0U:0xfff0U);
}
static int chain_end(uint32_t c) { return c>=(fat32?0x0ffffff8U:0xfff8U); }
static uint32_t cluster_sector(uint32_t c) { return data_start+(c-2)*sectors_per_cluster; }
static int next_cluster(uint32_t c,uint32_t *next) {
  unsigned width=fat32?4:2;uint32_t offset=c*width,sector=fat_start+offset/512;
  if(!cluster_valid(c))return 0;
  if(fat_cached_sector!=sector){if(!sd_read_sector(sector,fat_buf))return 0;fat_cached_sector=sector;}
  *next=fat32?u32(fat_buf+offset%512)&0x0fffffffU:u16(fat_buf+offset%512);
  return cluster_valid(*next)||chain_end(*next);
}

/* BPB geometry is checked before any derived address can be used. */
static int mount_volume(uint32_t base, uint32_t partition_size) {
  if (!sd_read_sector(base, buf) || u16(buf+510) != 0xaa55 ||
      !((buf[0] == 0xeb && buf[2] == 0x90) || buf[0] == 0xe9) || u16(buf+11) != 512) return 0;
  sectors_per_cluster = buf[13];
  uint32_t reserved = u16(buf+14), fats = buf[16], roots = u16(buf+17);
  uint32_t total = u16(buf+19), fat_size = u16(buf+22);
  if (!total) total = u32(buf+32);
  if (!fat_size) fat_size = u32(buf+36);
  if (!sectors_per_cluster || sectors_per_cluster > 128 ||
      (sectors_per_cluster & (sectors_per_cluster-1)) || !reserved ||
      (fats != 1 && fats != 2) || !fat_size || !total || total > partition_size ||
      base > UINT32_MAX - total || reserved >= total || fat_size > (total-reserved)/fats) return 0;
  root_sectors = (roots*32+511)/512;
  uint32_t overhead = reserved + fats*fat_size;
  if (root_sectors >= total-overhead) return 0;
  overhead += root_sectors;
  cluster_count = (total-overhead)/sectors_per_cluster;
  if (cluster_count < 4085 || cluster_count > 0x0fffffeeU) return 0; /* FAT12/exFAT unsupported. */
  fat32 = cluster_count >= 65525;
  if (fat_size < (cluster_count+2+(fat32?127:255))/(fat32?128:256)) return 0;
  fat_start = base + reserved;
  data_start = base + overhead;
  if (fat32) {
    if (roots || u16(buf+22) || u16(buf+42)) return 0;
    unsigned flags = u16(buf+40);
    if (flags & 0x80) {
      if ((flags & 15) >= fats) return 0;
      fat_start += (flags & 15)*fat_size;
    }
    root_start = u32(buf+44) & 0x0fffffffU;
    if (!cluster_valid(root_start)) return 0;
  } else {
    if (!roots || roots%16 || !u16(buf+22)) return 0;
    root_start = base + reserved + fats*fat_size;
  }
  return 1;
}


static struct entry entry_at(const uint8_t *p) {
  struct entry e={u16(p+26)|(fat32?u16(p+20)<<16:0),u32(p+28),p[11]};return e;
}
/* mode 0 finds ZORK, mode 1 collects DATs and the optional save pool. */
static int directory(uint32_t start,int fixed_root,unsigned mode,struct entry *game_dir) {
  unsigned walked=0,found=0;uint32_t c=start;
  do {
    if(!fixed_root&&!cluster_valid(c))return 0;
    unsigned n=fixed_root?root_sectors:sectors_per_cluster;
    uint32_t lba=fixed_root?c:cluster_sector(c);
    for(unsigned s=0;s<n;s++) {
      if(++walked>DIR_SECTOR_LIMIT||!sd_read_sector(lba+s,buf))return 0;
      for(unsigned off=0;off<512;off+=32) {
        const uint8_t *p=buf+off;
        if(!p[0])return mode||found;
        if(p[0]==0xe5||(p[11]&8))continue;
        if(!mode) {
          if(equal(p,(const uint8_t*)"ZORK       ",11)) {
            if(found++)return 0;*game_dir=entry_at(p);
          }
        } else if(equal(p,(const uint8_t*)"SAVES   BIN",11)) {
          if(found++)return 0;pool=entry_at(p);
        } else if(!(p[11]&0x10)&&equal(p+8,(const uint8_t*)"DAT",3)) {
          if(story_count==STORY_LIMIT){say("Too many DAT files (maximum 20).\n");return 0;}
          struct candidate *item=&stories[story_count++];item->file=entry_at(p);
          unsigned j=0;for(unsigned i=0;i<8&&p[i]!=' ';i++)item->name[j++]=p[i];
          item->name[j++]='.';for(unsigned i=8;i<11;i++)item->name[j++]=p[i];item->name[j]=0;
        }
      }
    }
    if(fixed_root)break;if(!next_cluster(c,&c))return 0;
  }while(!chain_end(c));
  return mode||found;
}
/* Protect all allocated directory clusters, even beyond the entry end marker.
 * Coalescing contiguous allocations bounds RAM without mapping every sector. */
static int protect_directory(uint32_t start,int fixed_root) {
  uint32_t c=start;unsigned walked=0;
  do {
    if(!fixed_root&&!cluster_valid(c))return 0;
    unsigned n=fixed_root?root_sectors:sectors_per_cluster;
    if(n>DIR_SECTOR_LIMIT-walked)return 0;walked+=n;
    uint32_t lba=fixed_root?c:cluster_sector(c);
    for(unsigned i=0;i<directory_count;i++)
      if(lba<directories[i].start+directories[i].size&&directories[i].start<lba+n)return 0;
    if(directory_count&&directories[directory_count-1].start+directories[directory_count-1].size==lba)
      directories[directory_count-1].size+=n;
    else {
      if(directory_count==DIR_EXTENTS)return 0;
      directories[directory_count].start=lba;directories[directory_count++].size=n;
    }
    if(fixed_root)return 1;if(!next_cluster(c,&c))return 0;
  }while(!chain_end(c));return 1;
}
static int directory_overlap(uint32_t lba,unsigned n) {
  for(unsigned i=0;i<directory_count;i++)
    if(lba<directories[i].start+directories[i].size&&directories[i].start<lba+n)return 1;
  return 0;
}
/* Exact finite chain lengths reject cycles/short/overallocated files. Pool
 * traversal protects every slot, but only maps the currently selected pair. */
static int map_file(struct entry *e,int is_pool,unsigned skip) {
  if((e->attr&0x18)||(is_pool&&(e->attr&1))||!e->size)return 0;
  unsigned size=(e->size+511)/512;uint32_t c=e->cluster;
  unsigned bound=is_pool?STORAGE_POOL_BYTES/512:STORY_SECTORS;
  if(size>bound)return 0;
  for(unsigned i=0;i<size;) {
    if(!cluster_valid(c))return 0;
    uint32_t lba=cluster_sector(c);
    if(directory_overlap(lba,sectors_per_cluster))return 0;
    if(is_pool&&lba<=story_last_sector&&lba+sectors_per_cluster>story_first_sector)for(unsigned j=0;j<story_sectors;j++)
      if(sector_map[j]>=lba&&sector_map[j]-lba<sectors_per_cluster)return 0;
    for(unsigned s=0;s<sectors_per_cluster&&i<size;s++,i++) {
      if(!is_pool) {
        sector_map[i]=lba+s;
        if(lba+s<story_first_sector)story_first_sector=lba+s;
        if(lba+s>story_last_sector)story_last_sector=lba+s;
      }
      else {
        if(i%SAVE_SECTORS==0)save_headers[i/SAVE_SECTORS]=lba+s;
        if(i>=skip&&i-skip<2*SAVE_SECTORS)sector_map[STORY_SECTORS+i-skip]=lba+s;
      }
    }
    if(!next_cluster(c,&c))return 0;
    if(i<size&&chain_end(c))return 0;
  }
  return chain_end(c);
}
static const char *validate_story(struct entry *e) {
  if(e->size<64)return "size must be at least 64 bytes";
  if(e->size>V3_FILE_MAX)return "padded file exceeds 1 MiB";
  if(!cluster_valid(e->cluster)||!sd_read_sector(cluster_sector(e->cluster),buf))return "story read failed";
  if(buf[0]!=3&&buf[0]!=5)return "requires Z-machine V3 or V5";
  unsigned scale=buf[0]==5?4:2;
  unsigned dynamic=be16(buf+14);uint32_t length=scale*be16(buf+26);if(!length)length=e->size;
  if(length<64||length>e->size||length>(buf[0]==5?Z_STORY_MAX:V3_STORY_MAX))return buf[0]==5?"invalid declared length (maximum 256 KiB)":"invalid declared length (maximum 128 KiB)";
  if(dynamic<64||dynamic>length||be16(buf+4)<dynamic||be16(buf+4)>=length||
      be16(buf+6)<64||be16(buf+6)>=length||be16(buf+10)<64||be16(buf+10)+(buf[0]==5?126U:62U)>dynamic||
      be16(buf+12)<64||be16(buf+12)+480U>dynamic||be16(buf+8)<64||be16(buf+8)+4U>length||
      be16(buf+24)<64||be16(buf+24)+192U>length)return "invalid story memory layout";
  return 0;
}
static int name_after(const char *a,const char *b) {
  for(;;) {
    unsigned x=(uint8_t)*a++,y=(uint8_t)*b++;
    if(x>='a'&&x<='z')x-=32;if(y>='a'&&y<='z')y-=32;
    if(x!=y)return x>y;if(!x)return 0;
  }
}
static void say_number(unsigned n) {
  if(n>=10)say_number(n/10);console_put('0'+n%10);
}
static int select_story(void) {
  // Sort complete candidates so selection retains the filename's allocation.
  for(unsigned i=1;i<story_count;i++) {
    struct candidate item=stories[i];unsigned j=i;
    while(j&&name_after(stories[j-1].name,item.name)){stories[j]=stories[j-1];j--;}
    stories[j]=item;
  }
  unsigned good=0,last=0;
  for(unsigned i=0;i<story_count;i++) {
    stories[i].error=validate_story(&stories[i].file);stories[i].version=buf[0];
    if(!stories[i].error){good++;last=i;}
    else{say("Skipping ");say(stories[i].name);say(": ");say(stories[i].error);say("\n");}
  }
  if(!good){say("No compatible V3/V5 DAT stories in /ZORK.\n");return 0;}
  if(good==1)chosen=last;
  else {
    unsigned has_v5=0;for(unsigned j=0;j<story_count;j++)if(!stories[j].error&&stories[j].version==5)has_v5=1;
    say(has_v5?"V3/V5 stories:\n":"V3 stories:\n");
    for(unsigned i=0;i<story_count;i++)if(!stories[i].error){say_number(i+1);say(". ");say(stories[i].name);say("\n");}
    for(;;) {
      say("Select story number: ");unsigned choice=0,escape=0,length=0,invalid=0;
      for(;;) {
        int c=console_get();
        if(escape){if(escape==1&&(c=='['||c=='O'))escape=2;else if(c>=0x40&&c<=0x7e)escape=0;continue;}
        if(c==27){escape=1;continue;}if(c==KEY_UP||c==KEY_DOWN)continue;
        if(c=='\r'||c=='\n'){say("\n");break;}
        if(c==8||c==127){if(length){console_put(8);console_put(' ');console_put(8);choice/=10;length--;}continue;}
        if(c>='0'&&c<='9'&&length<2){choice=choice*10+c-'0';length++;console_put(c);}
        else if(c>=32&&c<127)invalid=1;
      }
      if(!invalid&&choice&&choice<=story_count&&!stories[choice-1].error){chosen=choice-1;break;}
      say("Choose a compatible story number.\n");
    }
  }
  struct entry *e=&stories[chosen].file;
  story_sectors=(e->size+511)/512;
  if(!map_file(e,0,0)){say("Invalid story allocation chain.\n");return 0;}
  if(!sd_read_sector(sector_map[0],buf))return 0;
  story_bytes=(buf[0]==5?4U:2U)*be16(buf+26);if(!story_bytes)story_bytes=e->size;
  /* Standard release/serial/checksum identity, plus logical and dynamic sizes.
   * Renaming a story preserves its saves; a different release gets a new slot. */
  for(unsigned i=0;i<2;i++)story_id[i]=buf[2+i];
  for(unsigned i=0;i<6;i++)story_id[2+i]=buf[18+i];
  story_id[8]=buf[28];story_id[9]=buf[29];
  for(unsigned i=0;i<4;i++)story_id[10+i]=story_bytes>>(8*i);
  if(buf[0]==5)story_id[13]=5; /* Version domain in unused high size byte. */
  story_id[14]=buf[14];story_id[15]=buf[15];
  say("Starting ");say(stories[chosen].name);say("\n");return 1;
}
static int select_saves(void) {
  game_slots=1;
  if(pool.size==STORAGE_LEGACY_SLOTS*2U*STORAGE_BANK_BYTES)save_slots=STORAGE_LEGACY_SLOTS;
  else if(pool.size&&pool.size%STORAGE_PLANE_BYTES==0&&pool.size<=STORAGE_POOL_BYTES) {
    save_slots=STORAGE_SAVE_SLOTS;game_slots=pool.size/STORAGE_PLANE_BYTES;
  }
  else return 0;
  if(!map_file(&pool,1,0))return 0;
  int match=-1,empty=-1;
  for(unsigned slot=0;slot<save_slots;slot++) {
    unsigned owned=0,blank=0,foreign=0;
    for(unsigned position=0;position<game_slots;position++)for(unsigned bank=0;bank<2;bank++) {
      if(!sd_read_sector(save_headers[(position*save_slots+slot)*2+bank],buf))return 0;
      unsigned zero=1;for(unsigned i=0;i<512;i++)if(buf[i])zero=0;
      if(zero)blank++;else if(equal(buf+16,story_id,STORAGE_ID_BYTES))owned++;else foreign++;
    }
    if(owned) {if(foreign||match>=0)return 0;match=slot;}
    if(blank==2*game_slots&&empty<0)empty=slot;
  }
  int slot=match>=0?match:empty;
  if(slot<0){say("Save pool full; no slot for this story.\n");return 0;}
  save_owner=(unsigned)slot;mapped_game_slot=0;
  return !save_owner||map_file(&pool,1,save_owner*2*SAVE_SECTORS);
}
int storage_init(void) {
  ready=saves_ready=story_count=directory_count=story_sectors=save_slots=game_slots=0;pool.size=0;fat_cached_sector=UINT32_MAX;
  story_first_sector=UINT32_MAX;story_last_sector=0;
  if(!sd_read_sector(0,buf))return 0;
  uint32_t base=0,size=UINT32_MAX;
  if(!((buf[0]==0xeb&&buf[2]==0x90)||buf[0]==0xe9)||u16(buf+11)!=512) {
    if(u16(buf+510)!=0xaa55)return 0;unsigned i;
    for(i=0;i<4;i++) {
      const uint8_t *p=buf+446+16*i;unsigned type=p[4];
      if(type==4||type==6||type==14||type==11||type==12) {
        base=u32(p+8);size=u32(p+12);
        if(!base||!size||base>UINT32_MAX-size||(p[0]!=0&&p[0]!=0x80))return 0;break;
      }
    }if(i==4)return 0;
  }
  if(!mount_volume(base,size))return 0;
  struct entry dir;
  if(!directory(root_start,!fat32,0,&dir)||!(dir.attr&0x10)||!cluster_valid(dir.cluster)||
      !protect_directory(root_start,!fat32)||!protect_directory(dir.cluster,0)||
      !directory(dir.cluster,0,1,&dir)||!select_story())return 0;
  saves_ready=select_saves();
  if(!saves_ready)say("Saves disabled: prepare /ZORK/SAVES.BIN.\n");
  ready=1;return 1;
}
uint32_t storage_story_size(void){return story_bytes;}
const char *storage_story_name(void){return stories[chosen].name;}
const uint8_t *storage_story_id(void){return story_id;}
int storage_saves_available(void){return ready&&saves_ready;}
unsigned storage_game_slots(void){return storage_saves_available()?game_slots:0;}
int storage_select_save(unsigned slot) {
  if(!storage_saves_available()||slot>=game_slots)return 0;
  if(slot==mapped_game_slot)return 1;
  /* Allocation was fully validated at mount. Remap just this pair, following
   * the chain without repeating the expensive overlap scan for every menu row.
   * Card changes during play are unsupported. Revoke writes on any read error. */
  unsigned skip=(slot*save_slots+save_owner)*2*SAVE_SECTORS;
  uint32_t c=pool.cluster;
  while(skip>=sectors_per_cluster) {
    if(!next_cluster(c,&c)||!cluster_valid(c)){saves_ready=0;return 0;}
    skip-=sectors_per_cluster;
  }
  for(unsigned i=0;i<2*SAVE_SECTORS;) {
    uint32_t lba=cluster_sector(c);
    while(skip<sectors_per_cluster&&i<2*SAVE_SECTORS)
      sector_map[STORY_SECTORS+i++]=lba+skip++;
    if(i<2*SAVE_SECTORS) {
      if(!next_cluster(c,&c)||!cluster_valid(c)){saves_ready=0;return 0;}
      skip=0;
    }
  }
  mapped_game_slot=slot;return 1;
}
int storage_read(unsigned file,unsigned sector,uint8_t *data) {
  if(!ready||file>STORAGE_SAVE_B||sector>=(file?SAVE_SECTORS:(story_bytes+511)/512)||
      (file&&!saves_ready))return 0;
  unsigned offset=file?STORY_SECTORS+(file-1)*SAVE_SECTORS:0;
  return sd_read_sector(sector_map[offset+sector],data);
}
int storage_writable(uint32_t sector) {
  if(!ready||!saves_ready)return 0;
  for(unsigned i=STORY_SECTORS;i<MAP_SECTORS;i++)if(sector_map[i]==sector)return 1;return 0;
}
int storage_write(unsigned bank,unsigned sector,const uint8_t *data) {
  if(!ready||!saves_ready||bank>1||sector>=SAVE_SECTORS)return 0;
  return sd_write_sector(sector_map[STORY_SECTORS+bank*SAVE_SECTORS+sector],data);
}
