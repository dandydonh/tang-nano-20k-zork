#ifndef PS2_H
#define PS2_H
/* Feed raw set-2 bytes. Zero means no completed input event. */
void ps2_reset(void);
int ps2_key(unsigned scan);
#endif
