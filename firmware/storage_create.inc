/* Included after the read-only FAT/index helpers. Metadata authority is scoped
 * to one synchronous sector write and revoked even on a failed SD operation. */
#define SIDECAR_SECTORS (4U+5U*2U*SAVE_SECTORS)
#define CREATE_CLUSTERS (SIDECAR_SECTORS+2U)
#ifdef HOST
static uint32_t create_clusters[CREATE_CLUSTERS];
#else
#define create_clusters ((uint32_t *)0x300e0000U)
#endif
static int metadata_write(uint32_t lba,const uint8_t *data) {
  if(lba<volume_base||lba-volume_base>=volume_total)return 0;
  metadata_sector=lba;metadata_active=1;
  int ok=sd_write_sector(lba,data);metadata_active=0;fat_cached_sector=UINT32_MAX;
  return ok;
}
static unsigned short_units(const uint8_t *p,uint16_t *out) {
  unsigned n=0;for(unsigned i=0;i<8&&p[i]!=' ';i++)out[n++]=oem_char(p[i]);
  if(p[8]!=' '){out[n++]='.';for(unsigned i=8;i<11&&p[i]!=' ';i++)out[n++]=oem_char(p[i]);}
  return n;
}
static int units_match(const uint16_t *a,unsigned n) {
  if(n!=save_name_length)return 0;
  unsigned i=0,j=0;
  while(i<n&&j<save_name_length)
    if(folded(unicode_utf16(a,n,&i))!=folded(unicode_utf16(save_name,save_name_length,&j)))return 0;
  if(i!=n||j!=save_name_length)return 0;
  return 1;
}
/* Walk the validated directory using complete LFN units or the short name.
 * Local entries avoid clobbering the shared sector buffer during validation. */
static int sidecar_scan(unsigned mode,unsigned *alias_exists) {
  uint32_t c=game_directory.cluster;unsigned walked=0,found=0;
  struct long_name name={0};uint8_t entries[512];
  do {
    if(!cluster_valid(c))return -1;
    for(unsigned s=0;s<sectors_per_cluster;s++) {
      if(++walked>DIR_SECTOR_LIMIT||!sd_read_sector(cluster_sector(c)+s,entries))return -1;
      for(unsigned off=0;off<512;off+=32) {
        const uint8_t *p=entries+off;
        if(!p[0])return found;
        if(p[0]==0xe5){name.count=name.expected=0;continue;}
        if(p[11]==15){long_name_piece(&name,p);continue;}
        uint16_t units[260];char text[STORY_NAME_MAX+1];unsigned n=short_units(p,units);
        if(long_name_text(&name,p,text)) {
          n=0;while(n<name.count*13&&name.units[n]&&name.units[n]!=0xffff){units[n]=name.units[n];n++;}
        }
        if(mode==0) {
          /* Re-find selected story by its unique short alias and allocation. */
          char alias[13];unsigned an=short_alias(p,alias),i=0;
          while(i<an&&stories[chosen].alias[i]&&(unsigned char)stories[chosen].alias[i]==(unsigned char)alias[i])i++;
          if(i==an&&!stories[chosen].alias[i]&&entry_at(p).cluster==stories[chosen].file.cluster) {
            if(found++)return -1;
            unsigned dot=n;while(dot&&units[dot-1]!='.')dot--;
            if(!dot||dot+3>255)return -1;
            save_name_length=dot+3;
            for(unsigned j=0;j<dot;j++)save_name[j]=units[j];
            save_name[dot]='s';save_name[dot+1]='a';save_name[dot+2]='v';
          }
        }else {
          if(equal(p,save_alias,11))*alias_exists=1;
          uint16_t proposed[13];unsigned pn=short_units(save_alias,proposed),same=pn==n;
          for(unsigned j=0;j<n&&same;j++)if(folded(proposed[j])!=folded(units[j]))same=0;
          if(same)*alias_exists=1;
          uint16_t alias[13];unsigned an=short_units(p,alias);
          if(units_match(units,n)||units_match(alias,an)) {
            if(found++)return -1;
            sidecar_file=entry_at(p);
          }
        }
        name.count=name.expected=0;
      }
    }
    if(!next_cluster(c,&c))return -1;
  }while(!chain_end(c));
  return found;
}
/* -1 refuses ambiguous/invalid names; 0 missing; 1 valid sidecar. */
static int select_sidecar(void) {
  unsigned exists=0;
  if(sidecar_scan(0,&exists)!=1)return -1;
  unsigned stem=save_name_length-4,plain=stem>0&&stem<=8;
  for(unsigned i=0;i<11;i++)save_alias[i]=' ';
  for(unsigned i=0;i<stem&&plain;i++) {
    unsigned c=folded(save_name[i]);
    if(!((c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-'))plain=0;
    else save_alias[i]=c;
  }
  for(unsigned trial=0;trial<10000;trial++) {
    if(!plain||trial) {
      for(unsigned i=0;i<8;i++)save_alias[i]='0';save_alias[0]='Z';save_alias[1]='S';
      unsigned v=trial;for(unsigned i=0;i<6;i++){save_alias[7-i]='0'+v%10;v/=10;}
    }
    save_alias[8]='S';save_alias[9]='A';save_alias[10]='V';exists=0;
    int found=sidecar_scan(1,&exists);
    if(found<0)return -1;
    if(found) {
      if(sidecar_file.size!=SIDECAR_SECTORS*512U||!select_indexed_saves()||index_games!=1||game_slots!=5||owner_flags[0]!=1)return -1;
      return 1;
    }
    if(!exists)return 0;
  }
  return -1;
}
/* FAT copies must agree before allocation; active FAT mode updates only the
 * selected FAT. Preserve the FAT32 reserved upper nibble on every write. */
static uint32_t allocation_cached_sector;
static int fat_value(uint32_t c,uint32_t *value) {
  unsigned width=fat32?4:2;uint32_t off=c*width,sector=fat_start+off/512;
  if(allocation_cached_sector!=sector) {
    if(!sd_read_sector(sector,fat_buf))return 0;
    if(fat_mirrored)for(unsigned copy=1;copy<fat_copies;copy++) {
      if(!sd_read_sector(fat_primary+copy*fat_size_sectors+off/512,buf)||!equal(buf,fat_buf,512))return 0;
    }
    allocation_cached_sector=sector;fat_cached_sector=sector;
  }
  *value=(fat32?u32(fat_buf+off%512):u16(fat_buf+off%512))&(fat32?0xfffffffU:0xffffU);
  return 1;
}
static int fat_set(uint32_t c,uint32_t value) {
  unsigned width=fat32?4:2;uint32_t off=c*width;
  for(unsigned copy=0;copy<(fat_mirrored?fat_copies:1);copy++) {
    uint32_t sector=(fat_mirrored?fat_primary+copy*fat_size_sectors:fat_start)+off/512;
    if(!sd_read_sector(sector,fat_buf))return 0;
    if(fat32)put32(fat_buf+off%512,(u32(fat_buf+off%512)&0xf0000000U)|value);
    else {fat_buf[off%512]=value;fat_buf[off%512+1]=value>>8;}
    if(!metadata_write(sector,fat_buf))return 0;
  }
  return 1;
}
/* The allocation list is ascending, so update each FAT sector once per copy.
 * This also avoids thousands of repeated SPI writes on one-sector clusters. */
static int set_allocations(unsigned count,unsigned file_clusters,unsigned allocate) {
  unsigned width=fat32?4:2;uint32_t eoc=fat32?0xfffffffU:0xffffU;
  for(unsigned copy=0;copy<(fat_mirrored?fat_copies:1);copy++) {
    for(unsigned first=0;first<count;) {
      uint32_t part=create_clusters[first]*width/512;
      uint32_t lba=(fat_mirrored?fat_primary+copy*fat_size_sectors:fat_start)+part;
      if(!sd_read_sector(lba,fat_buf))return 0;
      unsigned end=first;
      while(end<count&&create_clusters[end]*width/512==part) {
        unsigned off=create_clusters[end]*width%512;
        uint32_t next=allocate?((end+1==file_clusters||end+1==count)?eoc:create_clusters[end+1]):0;
        if(fat32)put32(fat_buf+off,(u32(fat_buf+off)&0xf0000000U)|next);
        else {fat_buf[off]=next;fat_buf[off+1]=next>>8;}
        end++;
      }
      if(!metadata_write(lba,fat_buf))return 0;first=end;
    }
  }
  return 1;
}
static int invalidate_hints(void) {
  uint32_t sectors[2]={fsinfo_sector,backup_fsinfo};
  for(unsigned i=0;i<2;i++)if(sectors[i]) {
    if(!sd_read_sector(sectors[i],buf))return 0;
    if(u32(buf)!=0x41615252U||u32(buf+484)!=0x61417272U||u32(buf+508)!=0xaa550000U)return 0;
    put32(buf+488,UINT32_MAX);put32(buf+492,UINT32_MAX);
    if(!metadata_write(sectors[i],buf))return 0;
  }
  return 1;
}
static void sidecar_header(uint8_t *data) {
  for(unsigned i=0;i<512;i++)data[i]=0;
  for(unsigned i=0;i<8;i++)data[i]="ZSP1000\0"[i];
  put32(data+8,1);put32(data+12,1);put32(data+16,5);put32(data+20,STORAGE_BANK_BYTES);
  put32(data+24,1);put32(data+28,4);put32(data+32,SIDECAR_SECTORS*512U);
  put32(data+36,32);put32(data+508,index_hash(data,508));
}
/* End-marker append avoids reusing orphan LFN fragments or deleted aliases.
 * The short entry publishes the initialized file after its LFN records. */
#ifdef HOST
static uint32_t create_directory[DIR_SECTOR_LIMIT];
#else
#define create_directory ((uint32_t *)0x300e4000U)
#endif
static int directory_entry_write(unsigned index,const uint8_t *entry) {
  uint32_t lba=create_directory[index/16];
  if(!sd_read_sector(lba,buf))return 0;
  for(unsigned i=0;i<32;i++)buf[index%16*32+i]=entry[i];
  return metadata_write(lba,buf);
}
static int create_sidecar(void) {
  unsigned selected=mapped_game_slot,lfns=(save_name_length+12)/13,entries=lfns+1;
  unsigned dir_count=0,start=UINT32_MAX;uint32_t c=game_directory.cluster,tail=0,old_end=0;
  do {
    if(!cluster_valid(c)||dir_count>DIR_SECTOR_LIMIT-sectors_per_cluster)return 0;
    for(unsigned s=0;s<sectors_per_cluster;s++) {
      uint32_t lba=cluster_sector(c)+s;create_directory[dir_count]=lba;
      if(start==UINT32_MAX) {
        if(!sd_read_sector(lba,buf))return 0;
        for(unsigned off=0;off<512;off+=32)if(!buf[off]){start=dir_count*16+off/32;break;}
      }
      dir_count++;
    }
    tail=c;if(!next_cluster(c,&c))return 0;
  }while(!chain_end(c));
  old_end=c;if(start==UINT32_MAX)start=dir_count*16;
  unsigned need_sectors=(start+entries+1+15)/16;
  unsigned extra=need_sectors>dir_count?(need_sectors-dir_count+sectors_per_cluster-1)/sectors_per_cluster:0;
  if(extra*sectors_per_cluster>DIR_SECTOR_LIMIT-dir_count)return 0;
  unsigned file_clusters=(SIDECAR_SECTORS+sectors_per_cluster-1)/sectors_per_cluster;
  unsigned wanted=file_clusters+extra,allocated=0;
  if(wanted>CREATE_CLUSTERS)return 0;
  allocation_cached_sector=UINT32_MAX;
  for(uint32_t at=2;at-2<cluster_count&&allocated<wanted;at++) {
    uint32_t value;if(!fat_value(at,&value))return 0;
    if(value)continue;
    uint32_t lba=cluster_sector(at);
    if(directory_overlap(lba,sectors_per_cluster))return 0;
    for(unsigned j=0;j<story_sectors;j++)if(sector_map[j]>=lba&&sector_map[j]-lba<sectors_per_cluster)return 0;
    create_clusters[allocated++]=at;
  }
  if(allocated!=wanted){say("SD card full; save file was not created.\n");return 0;}
  /* Invalidate both free-space hints before any allocation. Unknown is valid
   * after interruption; no guessed counts or next-free pointers are committed. */
  if(!invalidate_hints())return 0;
  unsigned linked=0,staged=0;
  if(!set_allocations(wanted,file_clusters,1))goto rollback;
  /* Only commit headers make snapshots visible. Clear every bank header and
   * initialize the index before publication, including headers on recycled
   * clusters containing valid old snapshots of this exact story. Payload is
   * unreachable until a complete snapshot is written and its header commits.
   * Directory extension clusters must still be fully zeroed. */
  for(unsigned i=0;i<wanted;i++)for(unsigned s=0;s<sectors_per_cluster;s++) {
    unsigned sector=i*sectors_per_cluster+s;
    if(i<file_clusters&&(sector>=SIDECAR_SECTORS||
        (sector>=4&&(sector-4)%SAVE_SECTORS)))continue;
    for(unsigned j=0;j<512;j++)buf[j]=0;
    if(sector<2)sidecar_header(buf);
    else if(sector<4) {
      for(unsigned j=0;j<4;j++)buf[j]="ZOWN"[j];put32(buf+4,1);
      for(unsigned j=0;j<16;j++)buf[8+j]=story_id[j];
      put32(buf+24,0);put32(buf+28,index_hash(buf,28));
    }
    if(!metadata_write(cluster_sector(create_clusters[i])+s,buf))goto rollback;
  }
  if(extra) {
    /* Extending an empty-initialized directory is itself filesystem-consistent. */
    linked=1;if(!fat_set(tail,create_clusters[file_clusters]))goto rollback;
    for(unsigned i=file_clusters;i<wanted;i++)for(unsigned s=0;s<sectors_per_cluster;s++)
      create_directory[dir_count++]=cluster_sector(create_clusters[i])+s;
  }
  uint8_t checksum=0,entry[32]={0};
  for(unsigned i=0;i<11;i++)checksum=((checksum&1)?128:0)+(checksum>>1)+save_alias[i];
  /* Write a new end marker, then LFNs, then publish the short entry last. */
  staged=1;
  if(!directory_entry_write(start+entries,entry))goto rollback;
  for(unsigned at=0;at<entries;at++) {
    for(unsigned j=0;j<32;j++)entry[j]=0;
    if(at==lfns) {
      for(unsigned j=0;j<11;j++)entry[j]=save_alias[j];entry[11]=0x20;
      c=create_clusters[0];entry[26]=c;entry[27]=c>>8;
      if(fat32){entry[20]=c>>16;entry[21]=c>>24;}
      put32(entry+28,SIDECAR_SECTORS*512U);
      /* FAT date 1980-01-01: no RTC is available. */
      entry[16]=entry[18]=entry[24]=0x21;
    }else {
      unsigned ordinal=lfns-at;entry[0]=ordinal|(at==0?0x40:0);entry[11]=15;entry[13]=checksum;
      static const uint8_t offsets[13]={1,3,5,7,9,14,16,18,20,22,24,28,30};
      for(unsigned j=0;j<13;j++) {
        unsigned n=(ordinal-1)*13+j;
        unsigned value=n<save_name_length?save_name[n]:n==save_name_length?0:0xffff;
        entry[offsets[j]]=value;entry[offsets[j]+1]=value>>8;
      }
    }
    if(at==lfns) {
      /* A failed/torn publication may have made the file reachable. Never free
       * its clusters after this point; fsck may be needed after an SD fault. */
      if(!directory_entry_write(start+at,entry))return 0;
    }else if(!directory_entry_write(start+at,entry))goto rollback;
  }
  sidecar_file.cluster=create_clusters[0];sidecar_file.size=SIDECAR_SECTORS*512U;sidecar_file.attr=0x20;
  directory_count=0;
  if(!protect_directory(root_start,!fat32)||!protect_directory(game_directory.cluster,0)||!select_indexed_saves())return 0;
  sidecar_pending=0;
  return index_map_pair(selected);
rollback:
  /* Best effort for reported I/O failures. Abrupt power loss bypasses this and
   * can leave lost chains or disagreeing FAT mirrors; never claim journaling. */
  if(staged) {
    uint8_t empty[32]={0};
    for(unsigned at=0;at<=entries;at++)if(!directory_entry_write(start+at,empty))return 0;
  }
  if(linked&&!fat_set(tail,old_end))return 0;
  if(!set_allocations(wanted,file_clusters,0))return 0;
  return 0;
}
