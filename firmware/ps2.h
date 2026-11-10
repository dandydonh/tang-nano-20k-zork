#ifndef PS2_H
#define PS2_H
/* Feed raw set-2 bytes. Zero means no completed input event. */
/* Source 0: physical PS/2; source 1: Companion USB. State is independent. */
void ps2_reset_source(unsigned source);
int ps2_key_source(unsigned source,unsigned scan);
/* Legacy single-source interface; reset clears both sources. */
void ps2_reset(void);
int ps2_key(unsigned scan);
#endif
