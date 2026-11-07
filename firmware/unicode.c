#include "unicode.h"
#include "unicode_text_data.h"
static int contains(const struct unicode_interval *ranges,unsigned count,unsigned c) {
  unsigned low=0;
  while(low<count) {
    unsigned mid=(low+count)/2;
    unsigned plane=(unsigned)ranges[mid].plane<<16;
    if(c<plane+ranges[mid].first)count=mid;
    else if(c>plane+ranges[mid].last)low=mid+1;
    else return 1;
  }
  return 0;
}
unsigned unicode_columns(unsigned c) {
  if(c<128)return 1;
  if(contains(unicode_zero_ranges,sizeof(unicode_zero_ranges)/sizeof(unicode_zero_ranges[0]),c))return 0;
  return contains(unicode_wide_ranges,sizeof(unicode_wide_ranges)/sizeof(unicode_wide_ranges[0]),c)?2:1;
}
unsigned unicode_lower(unsigned c) {
  unsigned low=0,high=sizeof(unicode_lower_ranges)/sizeof(unicode_lower_ranges[0]);
  while(low<high) {
    unsigned mid=(low+high)/2;const struct unicode_lower_range *r=&unicode_lower_ranges[mid];
    unsigned first=((unsigned)r->plane<<16)|r->first;
    if(c<first)high=mid;
    else if(c-first>r->span)low=mid+1;
    else return (c-first)%r->stride?c:((unsigned)r->plane<<16)+r->lower+(c-first);
  }
  return c;
}
