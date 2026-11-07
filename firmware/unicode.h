#ifndef UNICODE_H
#define UNICODE_H
#include <stdint.h>

/* VFAT lengths are UTF-16 code units; internal display strings use UTF-8. */
static inline unsigned unicode_utf16(const uint16_t *s,unsigned length,unsigned *at) {
  unsigned c=s[(*at)++];
  if(c>=0xd800&&c<=0xdbff) {
    if(*at==length||s[*at]<0xdc00||s[*at]>0xdfff)return UINT32_MAX;
    c=0x10000+((c-0xd800)<<10)+(s[(*at)++]-0xdc00);
  }else if(c>=0xdc00&&c<=0xdfff)return UINT32_MAX;
  return c;
}
/* Reject malformed bytes without reading beyond the string terminator. */
static inline unsigned unicode_utf8(const char **text) {
  const uint8_t *p=(const uint8_t *)*text;unsigned lead=*p++,c=lead,n=0;
  *text=(const char *)p;
  if(lead<128)return c;
  if(lead>=0xf0&&lead<=0xf4){c&=7;n=3;}
  else if(lead>=0xe0&&lead<=0xef){c&=15;n=2;}
  else if(lead>=0xc2&&lead<=0xdf){c&=31;n=1;}
  else return 0xfffd;
  unsigned remaining=n;
  while(remaining--){if((*p&0xc0)!=0x80)return 0xfffd;c=(c<<6)|(*p++&63);}
  if((n==1&&c<0x80)||(n==2&&c<0x800)||(n==3&&c<0x10000)||
      c>0x10ffff||(c>=0xd800&&c<=0xdfff))return 0xfffd;
  *text=(const char *)p;return c;
}
static inline unsigned unicode_encode(unsigned c,uint8_t *p) {
  if(c<0x80){p[0]=c;return 1;}
  if(c<0x800){p[0]=0xc0|(c>>6);p[1]=0x80|(c&63);return 2;}
  if(c<0x10000){p[0]=0xe0|(c>>12);p[1]=0x80|((c>>6)&63);p[2]=0x80|(c&63);return 3;}
  p[0]=0xf0|(c>>18);p[1]=0x80|((c>>12)&63);p[2]=0x80|((c>>6)&63);p[3]=0x80|(c&63);return 4;
}
/* Unicode 15.1 cell widths: combining/format zero, wide/fullwidth two,
 * other scalars one. Ambiguous-width characters use the common narrow mode. */
unsigned unicode_columns(unsigned c);
unsigned unicode_lower(unsigned c);
static inline int unicode_printable(unsigned c) {
  return c>=32&&c<=0x10ffff&&!(c>=127&&c<=159)&&
    !(c>=0xd800&&c<=0xdfff)&&(c&0xffff)<0xfffe;
}
#endif
