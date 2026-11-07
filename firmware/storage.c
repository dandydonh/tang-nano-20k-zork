/* FAT16/FAT32 discovery and lazy per-story save allocation. No hot swapping. */
#include "platform.h"
#include "storage.h"
#define STORY_SECTORS (V3_FILE_MAX/512U)
#define SAVE_SECTORS STORAGE_BANK_SECTORS
#define MAP_SECTORS (STORY_SECTORS+2*SAVE_SECTORS)
#define DIR_SECTOR_LIMIT 2048U
#define DIR_EXTENTS 4096U
#define STORY_LIMIT STORAGE_STORY_LIMIT
#define STORY_NAME_MAX 255U
#ifdef HOST
static uint32_t sector_map[MAP_SECTORS];
static uint32_t save_headers[STORAGE_SAVE_SLOTS*2*STORAGE_GAME_SLOTS];
static uint8_t owner_flags[STORAGE_INDEX_GAMES];
#else
/* After the 0x30060000..0x3007ffff undo bank; populated before use. */
#define save_headers ((volatile uint32_t *)0x30080000U)
#define sector_map ((uint32_t *)0x30084000U)
#define owner_flags ((uint8_t *)0x30094000U)
#endif
struct pool_extent { uint32_t file_sector,first,count; };
#ifdef HOST
static struct pool_extent pool_extents[STORAGE_INDEX_EXTENTS];
#else
#define pool_extents ((struct pool_extent *)0x300a0000U)
#endif
static unsigned indexed_pool,index_claimed,index_games,index_sectors,index_data,extent_count,index_write_active;
static uint32_t index_write_sector;
static uint8_t buf[512], fat_buf[512], story_id[STORAGE_ID_BYTES];
static uint32_t fat_cached_sector, fat_start, data_start, cluster_count, root_start, root_sectors;
static uint32_t story_bytes;
static uint32_t story_first_sector,story_last_sector;
static unsigned sectors_per_cluster, fat32, ready, saves_ready, story_sectors, story_count, story_omitted, chosen, save_slots;
static unsigned game_slots, save_owner, mapped_game_slot;
struct entry { uint32_t cluster, size; unsigned attr; };
struct candidate { struct entry file; char name[STORY_NAME_MAX+1], alias[13]; uint8_t version; };
#ifdef HOST
static struct candidate stories[STORY_LIMIT];
static uint16_t story_order[STORY_LIMIT],menu_pages[STORY_LIMIT+1];
#else
/* Disjoint from VM, save index, sector map and extent caches. */
#define stories ((struct candidate *)0x30100000U)
#define story_order ((uint16_t *)0x300c1000U)
#define menu_pages ((uint16_t *)0x300c0000U)
#endif
struct long_name { uint16_t units[260]; unsigned count, expected, checksum; };
static struct entry pool;
struct directory_extent { uint32_t start,size; };
#ifdef HOST
static struct directory_extent directories[DIR_EXTENTS];
#else
#define directories ((struct directory_extent *)0x300d0000U)
#endif
static unsigned directory_count;
static struct entry game_directory;
static uint32_t volume_base,volume_total,fat_size_sectors,fat_copies,fat_primary;
static uint32_t fsinfo_sector,backup_fsinfo;
static unsigned fat_mirrored;
static unsigned sidecar_pending,metadata_active;
static uint32_t metadata_sector;
static uint16_t save_name[260];
static unsigned save_name_length;
static uint8_t save_alias[11];
static uint32_t u16(const uint8_t *p) { return p[0]|((uint32_t)p[1]<<8); }
static uint32_t u32(const uint8_t *p) { return u16(p)|(u16(p+2)<<16); }
static unsigned be16(const uint8_t *p) { return ((unsigned)p[0]<<8)|p[1]; }
static void put32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=v>>(8*i);}
static uint32_t index_hash(const uint8_t *p,unsigned n) {
  uint32_t h=2166136261U;while(n--)h=(h^*p++)*16777619U;return h;
}
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
  volume_base=base;volume_total=total;fat_size_sectors=fat_size;fat_copies=fats;
  fat_primary=base+reserved;fat_mirrored=!fat32||!(u16(buf+40)&0x80);
  fsinfo_sector=backup_fsinfo=0;
  if(fat32) {
    unsigned info=u16(buf+48),backup=u16(buf+50);
    if(info&&info<reserved) {
      fsinfo_sector=base+info;
      if(backup&&backup<reserved&&info<reserved-backup)backup_fsinfo=base+backup+info;
    }
  }
  return 1;
}


static struct entry entry_at(const uint8_t *p) {
  struct entry e={u16(p+26)|(fat32?u16(p+20)<<16:0),u32(p+28),p[11]};return e;
}
static int story_extension(const uint8_t *extension) {
  uint8_t a=extension[0],b=extension[1],c=extension[2];
  if(a>='a'&&a<='z')a-='a'-'A';
  if(b>='a'&&b<='z')b-='a'-'A';
  if(c>='a'&&c<='z')c-='a'-'A';
  return (a=='D'&&b=='A'&&c=='T')||(a=='Z'&&(b=='3'||b=='5')&&c==' ');
}
static void long_name_piece(struct long_name *name,const uint8_t *p) {
  unsigned ordinal=p[0]&31;
  if(p[0]&0x40){name->count=ordinal;name->expected=ordinal;name->checksum=p[13];}
  if(!ordinal||ordinal>20||(p[0]!=ordinal&&p[0]!=(ordinal|0x40))||
      !name->count||name->expected!=ordinal||p[12]||u16(p+26)||p[13]!=name->checksum) {
    name->count=name->expected=0;return;
  }
  static const uint8_t offsets[13]={1,3,5,7,9,14,16,18,20,22,24,28,30};
  for(unsigned i=0;i<13;i++)name->units[(ordinal-1)*13+i]=u16(p+offsets[i]);
  name->expected--;
}
static int long_name_text(const struct long_name *name,const uint8_t *p,char *text) {
  if(!name->count||name->expected)return 0;
  uint8_t checksum=0;
  for(unsigned i=0;i<11;i++)checksum=((checksum&1)?128:0)+(checksum>>1)+p[i];
  if(checksum!=name->checksum)return 0;
  unsigned length=0,ended=0;
  for(unsigned i=0;i<name->count*13;i++) {
    unsigned c=name->units[i];
    if(ended){if(c!=0xffff)return 0;continue;}
    if(!c){ended=1;continue;}
    if(c==0xffff||length==STORY_NAME_MAX||c<32||c==127||c=='"'||c=='*'||c=='/'||
        c==':'||c=='<'||c=='>'||c=='?'||c=='\\'||c=='|')return 0;
    text[length++]=c<=126?c:'?';
  }
  if(!length||length<=(name->count-1)*13)return 0;
  text[length]=0;return 1;
}
static void collect_story(const uint8_t *p,const struct long_name *name);
/* mode 0 finds ZORK, mode 1 collects stories and the optional save pool.
 * Header validation uses buf; keep directory entries separate while scanning. */
static int directory(uint32_t start,int fixed_root,unsigned mode,struct entry *game_dir) {
  uint8_t entries[512];
  struct long_name name;name.count=name.expected=name.checksum=0;
  unsigned walked=0,found=0;uint32_t c=start;
  do {
    if(!fixed_root&&!cluster_valid(c))return 0;
    unsigned n=fixed_root?root_sectors:sectors_per_cluster;
    uint32_t lba=fixed_root?c:cluster_sector(c);
    for(unsigned s=0;s<n;s++) {
      if(++walked>DIR_SECTOR_LIMIT||!sd_read_sector(lba+s,entries))return 0;
      for(unsigned off=0;off<512;off+=32) {
        const uint8_t *p=entries+off;
        if(!p[0])return mode||found;
        if(p[0]==0xe5){name.count=name.expected=0;continue;}
        if(p[11]==0x0f){long_name_piece(&name,p);continue;}
        if(p[11]&8){name.count=name.expected=0;continue;}
        if(!mode) {
          if(equal(p,(const uint8_t*)"ZORK       ",11)) {
            if(found++)return 0;*game_dir=entry_at(p);
          }
        } else if(equal(p,(const uint8_t*)"SAVES   BIN",11)) {
          if(found++)return 0;pool=entry_at(p);
        } else if(!(p[11]&0x10)&&story_extension(p+8)) {
          collect_story(p,&name);
        }
        name.count=name.expected=0;
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
static int candidate_after(const struct candidate *a,const struct candidate *b) {
  return name_after(a->name,b->name)||(!name_after(b->name,a->name)&&name_after(a->alias,b->alias));
}
static void sift_story(unsigned at,unsigned count) {
  for(;;) {
    unsigned child=at*2+1;if(child>=count)return;
    if(child+1<count&&candidate_after(&stories[story_order[child+1]],&stories[story_order[child]]))child++;
    if(!candidate_after(&stories[story_order[child]],&stories[story_order[at]]))return;
    uint16_t swap=story_order[at];story_order[at]=story_order[child];story_order[child]=swap;at=child;
  }
}
static void collect_story(const uint8_t *p,const struct long_name *name) {
  struct candidate item;item.file=entry_at(p);
  unsigned j=0;for(unsigned i=0;i<8&&p[i]!=' ';i++)item.alias[j++]=p[i];
  item.alias[j++]='.';for(unsigned i=8;i<11&&p[i]!=' ';i++)item.alias[j++]=p[i];item.alias[j]=0;
  if(!long_name_text(name,p,item.name))for(unsigned i=0;i<=j;i++)item.name[i]=item.alias[i];
  const char *error=validate_story(&item.file);
  if(error){say("Skipping ");say(item.name);say(": ");say(error);say("\n");return;}
  item.version=buf[0];
  /* A max heap retains the first 1000 names without moving full-name records
   * on every insertion. Overflow still scans through a later SAVES.BIN. */
  if(story_count==STORY_LIMIT) {
    story_omitted++;
    if(!candidate_after(&stories[story_order[0]],&item))return;
    stories[story_order[0]]=item;sift_story(0,story_count);return;
  }
  unsigned at=story_count;stories[at]=item;story_order[at]=at;story_count++;
  while(at) {
    unsigned parent=(at-1)/2;
    if(!candidate_after(&stories[story_order[at]],&stories[story_order[parent]]))break;
    uint16_t swap=story_order[at];story_order[at]=story_order[parent];story_order[parent]=swap;at=parent;
  }
}
static void say_number(unsigned n) {
  if(n>=10)say_number(n/10);console_put('0'+n%10);
}
static int select_story(void) {
  if(!story_count){say("No compatible V3/V5 stories (.DAT/.Z3/.Z5) in /ZORK.\n");return 0;}
  for(unsigned count=story_count;count>1;count--) {
    uint16_t swap=story_order[0];story_order[0]=story_order[count-1];story_order[count-1]=swap;
    sift_story(0,count-1);
  }
  if(story_omitted){
    say("Story menu limited to 1000 compatible files; ");say_number(story_omitted);say(" more omitted.\n");
  }
  if(story_count==1)chosen=0;
  else {
    unsigned has_v5=0;for(unsigned j=0;j<story_count;j++)if(stories[j].version==5)has_v5=1;
    unsigned pages=0,rows=console_menu_rows(),width=console_menu_columns();
    unsigned budget=rows>7?rows-6:1;
    for(unsigned start=0;start<story_count;) {
      menu_pages[pages++]=start;unsigned used=0,end=start;
      while(end<story_count&&end-start<20) {
        unsigned length=0,n=end+1;do{length++;n/=10;}while(n);length+=2;
        for(const char *p=stories[story_order[end]].name;*p;p++)length++;
        unsigned lines=(length+width-1)/width;
        if(end>start&&used+lines>budget)break;
        used+=lines;end++;
      }
      start=end;
    }
    menu_pages[pages]=story_count;
    unsigned page=0,redraw=1;
    for(;;) {
      if(redraw) {
        if(pages>1){console_menu_reset();console_clear();}
        if(story_omitted&&pages>1){say_number(story_omitted);say(" additional compatible stories omitted.\n");}
        say(has_v5?"V3/V5 stories:\n":"V3 stories:\n");
        if(pages>1){say("Page ");say_number(page+1);say("/");say_number(pages);say(" (stories ");say_number(menu_pages[page]+1);say("-");say_number(menu_pages[page+1]);say(" of ");say_number(story_count);say(")\n");}
        console_page_reset();
        for(unsigned i=menu_pages[page];i<menu_pages[page+1];i++) {
          say_number(i+1);say(". ");say(stories[story_order[i]].name);say("\n");
        }
        if(pages>1)say("N = next page, P = previous; enter any story number.\n");
        redraw=0;
      }
      console_page_reset();
      say("Select story number: ");unsigned choice=0,escape=0,length=0,overflow=0;
      char input[5];
      for(;;) {
        int c=console_get();
        if(escape){if(escape==1&&(c=='['||c=='O'))escape=2;else if(c>=0x40&&c<=0x7e)escape=0;continue;}
        if(c==27){escape=1;continue;}if(c==KEY_UP||c==KEY_DOWN)continue;
        if(c=='\r'||c=='\n'){say("\n");break;}
        if(c==8||c==127){if(overflow)overflow--;else if(length){console_put(8);console_put(' ');console_put(8);length--;}continue;}
        if(c>=32&&c<127){if(length<4&&!overflow){input[length++]=c;console_put(c);}else overflow++;}
      }
      input[length]=0;
      if(!overflow&&length==1&&(input[0]=='n'||input[0]=='N'||input[0]=='p'||input[0]=='P')) {
        if(input[0]=='n'||input[0]=='N') {
          if(page+1<pages){page++;redraw=1;}else say("Already on last page.\n");
        }else if(page){page--;redraw=1;}else say("Already on first page.\n");
        continue;
      }
      unsigned invalid=overflow||!length;
      for(unsigned i=0;i<length;i++) {
        if(input[i]<'0'||input[i]>'9'){invalid=1;break;}
        choice=choice*10+input[i]-'0';
      }
      if(!invalid&&choice&&choice<=story_count){chosen=choice-1;break;}
      say("Choose a compatible story number.\n");
    }
  }
  chosen=story_order[chosen];
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
/* Validate the complete allocation once, retaining contiguous runs rather than
 * one entry per sector. Large, normally allocated pools need only a few runs. */
static int index_map_pool(void) {
  if((pool.attr&0x19)||!pool.size||pool.size%512)return 0;
  uint32_t c=pool.cluster,total=pool.size/512;
  extent_count=0;
  for(uint32_t at=0;at<total;) {
    if(!cluster_valid(c))return 0;
    uint32_t lba=cluster_sector(c),n=sectors_per_cluster;
    if(directory_overlap(lba,n))return 0;
    if(lba<=story_last_sector&&lba+n>story_first_sector)for(unsigned j=0;j<story_sectors;j++)
      if(sector_map[j]>=lba&&sector_map[j]-lba<n)return 0;
    if(n>total-at)n=total-at;
    if(extent_count&&pool_extents[extent_count-1].first+pool_extents[extent_count-1].count==lba)
      pool_extents[extent_count-1].count+=n;
    else {
      if(extent_count==STORAGE_INDEX_EXTENTS)return 0;
      pool_extents[extent_count].file_sector=at;pool_extents[extent_count].first=lba;
      pool_extents[extent_count++].count=n;
    }
    at+=n;if(!next_cluster(c,&c))return 0;
    if(at<total&&chain_end(c))return 0;
  }
  return chain_end(c);
}
static int index_lba(uint32_t sector,uint32_t *lba) {
  unsigned lo=0,hi=extent_count;
  while(lo<hi) {
    unsigned mid=(lo+hi)/2;struct pool_extent *e=&pool_extents[mid];
    if(sector<e->file_sector)hi=mid;
    else if(sector-e->file_sector>=e->count)lo=mid+1;
    else{*lba=e->first+sector-e->file_sector;return 1;}
  }
  return 0;
}
static int index_read(uint32_t sector,uint8_t *data) {
  uint32_t lba;return index_lba(sector,&lba)&&sd_read_sector(lba,data);
}
static int index_header(const uint8_t *p) {
  if(!equal(p,(const uint8_t*)"ZSP1000\0",8)||u32(p+8)!=1||
      index_hash(p,508)!=u32(p+508)||u32(p+20)!=STORAGE_BANK_BYTES||
      u32(p+36)!=STORAGE_INDEX_RECORD_BYTES)return 0;
  unsigned owners=u32(p+12),positions=u32(p+16),sectors=(owners+15)/16;
  if(!owners||owners>STORAGE_INDEX_GAMES||!positions||positions>STORAGE_GAME_SLOTS||
      u32(p+24)!=sectors||u32(p+28)!=2+2*sectors)return 0;
  uint32_t metadata=(2+2*sectors)*512U;
  if(owners*positions>(UINT32_MAX-metadata)/(2U*STORAGE_BANK_BYTES))return 0;
  uint32_t bytes=metadata+owners*positions*2U*STORAGE_BANK_BYTES;
  return u32(p+32)==bytes&&pool.size==bytes;
}
/* 0 = empty, 1 = committed owner, 2 = damaged record (never reallocated). */
static unsigned index_record(const uint8_t *p,unsigned owner) {
  unsigned zero=1;for(unsigned i=0;i<32;i++)if(p[i])zero=0;
  if(zero)return 0;
  return equal(p,(const uint8_t*)"ZOWN",4)&&u32(p+4)==1&&u32(p+24)==owner&&
    index_hash(p,28)==u32(p+28)?1:2;
}
static int index_map_pair(unsigned position) {
  uint32_t start=index_data+(save_owner*game_slots+position)*2U*SAVE_SECTORS;
  for(unsigned i=0;i<2*SAVE_SECTORS;i++)
    if(!index_lba(start+i,&sector_map[STORY_SECTORS+i]))return 0;
  mapped_game_slot=position;return 1;
}
static int select_indexed_saves(void) {
  uint8_t copy[512];
  if(!index_map_pool()||!index_read(0,copy)||!index_read(1,buf))return 0;
  int first=index_header(copy),second=index_header(buf);
  if(!first&&!second)return 0;
  if(first&&second&&!equal(copy,buf,512))return 0;
  const uint8_t *header=first?copy:buf;
  index_games=u32(header+12);game_slots=u32(header+16);
  index_sectors=u32(header+24);index_data=u32(header+28);
  int match=-1,empty=-1;unsigned matched_redundant=0;
  for(unsigned sector=0;sector<index_sectors;sector++) {
    if(!index_read(2+sector,copy)||!index_read(2+index_sectors+sector,buf))return 0;
    for(unsigned slot=0;slot<16&&sector*16+slot<index_games;slot++) {
      unsigned owner=sector*16+slot;const uint8_t *a=copy+slot*32,*b=buf+slot*32;
      unsigned va=index_record(a,owner),vb=index_record(b,owner);
      owner_flags[owner]=(!va&&!vb)?0:2;
      const uint8_t *record=va==1?a:vb==1?b:0;
      if(record&&!(va==1&&vb==1&&!equal(a,b,32))) {
        owner_flags[owner]=1;
        if(equal(record+8,story_id,STORAGE_ID_BYTES)) {
          if(match>=0)return 0;match=owner;matched_redundant=va==1&&vb==1;
        }
      }
      /* A damaged record might have owned this story. Refuse a new assignment
       * if no intact record identifies it, rather than silently losing saves. */
      if(!owner_flags[owner]&&empty<0)empty=owner;
    }
  }
  if(match<0)for(unsigned owner=0;owner<index_games;owner++)if(owner_flags[owner]==2) {
    say("Save index damaged; new story allocation disabled.\n");return 0;
  }
  int owner=match>=0?match:empty;
  if(owner<0){say("Save pool full; no slot for this story.\n");return 0;}
  save_owner=(unsigned)owner;index_claimed=matched_redundant;indexed_pool=1;
  return index_map_pair(0);
}
/* Claim an identity before writing any snapshot data. Each copy is a separate
 * sector write, preserving neighboring records and leaving a recoverable copy. */
static int index_claim(void) {
  uint8_t record[32]={0};
  for(unsigned i=0;i<4;i++)record[i]="ZOWN"[i];put32(record+4,1);
  for(unsigned i=0;i<STORAGE_ID_BYTES;i++)record[8+i]=story_id[i];
  put32(record+24,save_owner);put32(record+28,index_hash(record,28));
  for(unsigned bank=0;bank<2;bank++) {
    uint32_t lba;
    if(!index_lba(2+bank*index_sectors+save_owner/16,&lba)||!sd_read_sector(lba,buf))return 0;
    for(unsigned i=0;i<32;i++)buf[(save_owner%16)*32+i]=record[i];
    index_write_sector=lba;index_write_active=1;
    int ok=sd_write_sector(lba,buf);index_write_active=0;if(!ok)return 0;
  }
  owner_flags[save_owner]=1;
  index_claimed=1;return 1;
}
static int select_saves(void) {
  game_slots=1;
  if(pool.size==STORAGE_LEGACY_SLOTS*2U*STORAGE_BANK_BYTES)save_slots=STORAGE_LEGACY_SLOTS;
  else if(pool.size&&pool.size%STORAGE_PLANE_BYTES==0&&pool.size<=STORAGE_POOL_BYTES) {
    save_slots=STORAGE_SAVE_SLOTS;game_slots=pool.size/STORAGE_PLANE_BYTES;
  }
  else return select_indexed_saves();
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
#include "storage_create.inc"

int storage_init(void) {
  sidecar_pending=metadata_active=0;
  indexed_pool=index_claimed=index_write_active=extent_count=0;
  ready=saves_ready=story_count=story_omitted=directory_count=story_sectors=save_slots=game_slots=0;pool.size=0;fat_cached_sector=UINT32_MAX;
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
  game_directory=dir;
  int sidecar=select_sidecar();
  saves_ready=sidecar>0;
  /* Existing shared pools remain usable; fresh cards need only stories. */
  if(sidecar==0&&pool.size)saves_ready=select_saves();
  else if(sidecar==0) {
    sidecar_pending=1;saves_ready=!(game_directory.attr&1);game_slots=5;mapped_game_slot=0;
  }
  if(!saves_ready)say("Saves disabled: invalid, conflicting or read-only save file/directory.\n");
  ready=1;return 1;
}
uint32_t storage_story_size(void){return story_bytes;}
const char *storage_story_name(void){return stories[chosen].name;}
const uint8_t *storage_story_id(void){return story_id;}
int storage_saves_available(void){return ready&&saves_ready;}
unsigned storage_game_slots(void){return storage_saves_available()?game_slots:0;}
int storage_select_save(unsigned slot) {
  if(!storage_saves_available()||slot>=game_slots)return 0;
  if(sidecar_pending){mapped_game_slot=slot;return 1;}
  if(slot==mapped_game_slot)return 1;
  if(indexed_pool){if(index_map_pair(slot))return 1;saves_ready=0;return 0;}
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
  if(file&&sidecar_pending){for(unsigned i=0;i<512;i++)data[i]=0;return 1;}
  unsigned offset=file?STORY_SECTORS+(file-1)*SAVE_SECTORS:0;
  return sd_read_sector(sector_map[offset+sector],data);
}
int storage_writable(uint32_t sector) {
  if(!ready||!saves_ready)return 0;
  if(metadata_active)return sector==metadata_sector;
  if(sidecar_pending)return 0;
  if(indexed_pool&&index_write_active&&sector==index_write_sector)return 1;
  for(unsigned i=STORY_SECTORS;i<MAP_SECTORS;i++)if(sector_map[i]==sector)return 1;return 0;
}
int storage_write(unsigned bank,unsigned sector,const uint8_t *data) {
  if(!ready||!saves_ready||bank>1||sector>=SAVE_SECTORS)return 0;
  if(sidecar_pending&&!create_sidecar()){saves_ready=0;return 0;}
  if(indexed_pool&&!index_claimed&&!index_claim()){saves_ready=0;return 0;}
  return sd_write_sector(sector_map[STORY_SECTORS+bank*SAVE_SECTORS+sector],data);
}
