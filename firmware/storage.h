#ifndef STORAGE_H
#define STORAGE_H
#include <stdint.h>
#define V3_DYNAMIC_MAX 65535U
#define V3_STORY_MAX 131072U
/* Bound physical allocation traversal, including trailing legacy padding. */
#define V3_FILE_MAX 1048576U
#define STORAGE_SAVE_MAGIC 0x35564d5aU
#define STORAGE_ID_BYTES 16U
#define STORAGE_STORY_LIMIT 20U
#define STORAGE_SAVE_SLOTS 20U
#define STORAGE_LEGACY_SLOTS 8U
/* Player positions per story; each plane retains twenty story identities. */
#define STORAGE_GAME_SLOTS 20U
#define STORAGE_BANK_BYTES 131072U
#define STORAGE_BANK_SECTORS (STORAGE_BANK_BYTES/512U)
#define STORAGE_PLANE_BYTES (STORAGE_SAVE_SLOTS * 2U * STORAGE_BANK_BYTES)
#define STORAGE_POOL_BYTES (STORAGE_GAME_SLOTS * STORAGE_PLANE_BYTES)
enum { STORAGE_STORY, STORAGE_SAVE_A, STORAGE_SAVE_B };
int storage_init(void);
int storage_read(unsigned file, unsigned sector, uint8_t *data);
int storage_write(unsigned bank, unsigned sector, const uint8_t *data);
int storage_writable(uint32_t sector);
uint32_t storage_story_size(void);
const char *storage_story_name(void);
const uint8_t *storage_story_id(void);
int storage_saves_available(void);
unsigned storage_game_slots(void);
int storage_select_save(unsigned slot);
#endif
