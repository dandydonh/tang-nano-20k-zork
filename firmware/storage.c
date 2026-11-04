/* Bounded FAT16/FAT32 reader with writes confined to two existing save files.
 * File chains are resolved once at boot, including fragmented allocations.
 * The card must remain inserted and exclusively owned until reset/power off.
 */
#include "platform.h"
#include "storage.h"

#define STORY_SECTORS 180U
#define SAVE_SECTORS 64U
#define MAP_SECTORS (STORY_SECTORS + 2 * SAVE_SECTORS)
#define DIR_SECTOR_LIMIT 256U
static uint32_t sector_map[MAP_SECTORS];
static uint8_t buf[512];
static uint8_t fat_buf[512];
static uint32_t fat_cached_sector;
static uint32_t fat_start, data_start, cluster_count, root_start, root_sectors;
static unsigned sectors_per_cluster, fat32, ready;
struct entry { uint32_t cluster, size; unsigned attr; };
static const char names[4][12] = {"ZORK       ", "ZORK1   DAT", "SAVEA   BIN", "SAVEB   BIN"};

static uint32_t u16(const uint8_t *p) { return p[0] | ((uint32_t)p[1] << 8); }
static uint32_t u32(const uint8_t *p) { return u16(p) | (u16(p+2) << 16); }
static int cluster_valid(uint32_t c) {
  return c >= 2 && c - 2 < cluster_count && c < (fat32 ? 0x0ffffff0U : 0xfff0U);
}
static int chain_end(uint32_t c) { return c >= (fat32 ? 0x0ffffff8U : 0xfff8U); }
static uint32_t cluster_sector(uint32_t c) { return data_start + (c-2)*sectors_per_cluster; }
static int next_cluster(uint32_t c, uint32_t *next) {
  unsigned width = fat32 ? 4 : 2;
  uint32_t offset = c * width;
  uint32_t sector = fat_start + offset/512;
  if (!cluster_valid(c)) return 0;
  if (fat_cached_sector != sector) {
    if (!sd_read_sector(sector, fat_buf)) return 0;
    fat_cached_sector = sector;
  }
  *next = fat32 ? u32(fat_buf + offset%512) & 0x0fffffffU : u16(fat_buf + offset%512);
  return cluster_valid(*next) || chain_end(*next);
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

/* Three fixed 8.3 names; VFAT entries and unrelated files are ignored.
 * Bound directory walks so damaged/cyclic media cannot hang startup. */
static int directory(uint32_t start, int fixed_root, unsigned first, unsigned count,
                     struct entry *entries) {
  unsigned found = 0, walked = 0;
  uint32_t c = start;
  do {
    if (!fixed_root && !cluster_valid(c)) return 0;
    unsigned n = fixed_root ? root_sectors : sectors_per_cluster;
    uint32_t lba = fixed_root ? c : cluster_sector(c);
    for (unsigned s=0; s<n; s++) {
      if (++walked > DIR_SECTOR_LIMIT) return 0;
      if (!sd_read_sector(lba+s, buf)) return 0;
      for (unsigned offset=0; offset<512; offset+=32) {
        const uint8_t *p = buf+offset;
        if (!p[0]) return found == (1U<<count)-1;
        if (p[0] == 0xe5 || (p[11]&8)) continue; /* Deleted, volume label or LFN. */
        for (unsigned i=0; i<count; i++) {
          unsigned j=0; while (j<11 && p[j] == (uint8_t)names[first+i][j]) j++;
          if (j != 11) continue;
          if (found & (1U<<i)) return 0; /* Ambiguous duplicate. */
          found |= 1U<<i;
          entries[i].cluster = u16(p+26) | (fat32 ? u16(p+20)<<16 : 0);
          entries[i].size = u32(p+28); entries[i].attr = p[11];
        }
      }
    }
    if (fixed_root) break;
    if (!next_cluster(c, &c)) return 0;
  } while (!chain_end(c));
  return found == (1U<<count)-1;
}

/* Include allocated directory clusters beyond the first end-of-entries marker.
 * Check the whole chain even if the names were found in its first sector. */
static int protect_directory(uint32_t start, int fixed_root) {
  uint32_t c=start;
  unsigned walked=0;
  do {
    if (!fixed_root && !cluster_valid(c)) return 0;
    unsigned n=fixed_root ? root_sectors : sectors_per_cluster;
    if (n > DIR_SECTOR_LIMIT-walked) return 0;
    walked+=n;
    uint32_t lba=fixed_root ? c : cluster_sector(c);
    for (unsigned i=0; i<MAP_SECTORS; i++)
      if (sector_map[i]>=lba && sector_map[i]-lba<n) return 0;
    if (fixed_root) return 1;
    if (!next_cluster(c, &c)) return 0;
  } while (!chain_end(c));
  return 1;
}

static int map_file(struct entry *e, unsigned offset, unsigned size) {
  if ((e->attr & 0x18) || (offset >= STORY_SECTORS && (e->attr & 1)) || e->size != size*512U) return 0;
  uint32_t c = e->cluster;
  for (unsigned i=0; i<size;) {
    if (!cluster_valid(c)) return 0;
    uint32_t lba = cluster_sector(c);
    /* Compare allocated clusters, including unused tail sectors. */
    for (unsigned j=0; j<offset+i; j++)
      if ((sector_map[j]-data_start)/sectors_per_cluster == c-2) return 0;
    for (unsigned s=0; s<sectors_per_cluster && i<size; s++) sector_map[offset+i++] = lba+s;
    if (!next_cluster(c, &c)) return 0;
    if (i<size && chain_end(c)) return 0;
  }
  return chain_end(c); /* Reject overallocated/cyclic chains as well as short ones. */
}

int storage_init(void) {
  ready = 0;
  fat_cached_sector = UINT32_MAX;
  if (!sd_read_sector(0, buf)) return 0;
  /* A boot jump identifies a superfloppy. Otherwise select the first primary
   * FAT16/FAT32 MBR partition. GPT/extended partition traversal is unsupported.
   */
  uint32_t base=0, size=UINT32_MAX;
  if (!((buf[0] == 0xeb && buf[2] == 0x90) || buf[0] == 0xe9) || u16(buf+11) != 512) {
    if (u16(buf+510) != 0xaa55) return 0;
    unsigned i;
    for (i=0; i<4; i++) {
      const uint8_t *p = buf+446+16*i;
      unsigned type=p[4];
      if (type==4 || type==6 || type==14 || type==11 || type==12) {
        base=u32(p+8); size=u32(p+12);
        if (!base || !size || base > UINT32_MAX-size || (p[0] != 0 && p[0] != 0x80)) return 0;
        break;
      }
    }
    if (i==4) return 0;
  }
  if (!mount_volume(base, size)) return 0;
  struct entry dir, files[3];
  if (!directory(root_start, !fat32, 0, 1, &dir) ||
      !(dir.attr & 0x10) || !cluster_valid(dir.cluster)) return 0;
  uint32_t zork_dir=dir.cluster;
  if (!directory(zork_dir, 0, 1, 3, files)) return 0;
  if (!map_file(&files[0], 0, STORY_SECTORS) ||
      !map_file(&files[1], STORY_SECTORS, SAVE_SECTORS) ||
      !map_file(&files[2], STORY_SECTORS+SAVE_SECTORS, SAVE_SECTORS)) return 0;
  if (!protect_directory(root_start, !fat32) || !protect_directory(zork_dir, 0)) return 0;
  if (!sd_read_sector(sector_map[0], buf) || buf[0]!=3 || u16(buf+2)!=0x5800) return 0;
  const char *serial="840726";
  for (unsigned i=0; i<6; i++) if (buf[18+i] != (uint8_t)serial[i]) return 0;
  ready = 1;
  return 1;
}

int storage_read(unsigned file, unsigned sector, uint8_t *data) {
  if (!ready || file>STORAGE_SAVE_B || sector >= (file ? SAVE_SECTORS : STORY_SECTORS)) return 0;
  unsigned offset = file ? STORY_SECTORS+(file-1)*SAVE_SECTORS : 0;
  return sd_read_sector(sector_map[offset+sector], data);
}
int storage_writable(uint32_t sector) {
  if (!ready) return 0;
  for (unsigned i=STORY_SECTORS; i<MAP_SECTORS; i++) if (sector_map[i]==sector) return 1;
  return 0;
}
int storage_write(unsigned bank, unsigned sector, const uint8_t *data) {
  if (!ready || bank>1 || sector>=SAVE_SECTORS) return 0;
  return sd_write_sector(sector_map[STORY_SECTORS+bank*SAVE_SECTORS+sector], data);
}
