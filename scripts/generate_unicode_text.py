#!/usr/bin/env python3
"""Generate Unicode 15.1 lowercase and terminal-width tables.

Usage: python3 scripts/generate_unicode_text.py /path/to/ucd
Inputs: UnicodeData.txt and EastAsianWidth.txt from Unicode 15.1.
Normal builds use the checked-in header. Terms: third_party/unicode/LICENSE.
"""
from pathlib import Path
import sys

ucd = Path(sys.argv[1])
pairs, zero, wide = [], set(), set()
for line in (ucd / 'UnicodeData.txt').read_text().splitlines():
    f = line.split(';')
    c = int(f[0], 16)
    if f[13]:
        pairs.append((c, int(f[13], 16)))
    if f[2] in ('Mn', 'Me', 'Cf'):
        zero.add(c)
for line in (ucd / 'EastAsianWidth.txt').read_text().splitlines():
    record = line.split('#')[0].strip()
    if not record:
        continue
    field, width = map(str.strip, record.split(';'))
    if width in ('W', 'F'):
        ends = field.split('..')
        first, last = int(ends[0], 16), int(ends[-1], 16)
        wide.update(range(first, last + 1))


def intervals(values):
    result = []
    for c in sorted(values):
        if result and result[-1][1] == c - 1:
            result[-1][1] = c
        else:
            result.append([c, c])
    return result


out = '''/* Generated Unicode 15.1 data, modified into compact firmware tables.
 * Copyright (c) 1991-2023 Unicode, Inc. All rights reserved.
 * Terms: third_party/unicode/LICENSE, https://www.unicode.org/license.txt */
#ifndef UNICODE_TEXT_DATA_H
#define UNICODE_TEXT_DATA_H
static const struct unicode_lower_range {
  uint16_t first,lower,span;
  uint8_t stride,plane;
} unicode_lower_ranges[] = {
'''
i = 0
while i < len(pairs):
    first, lower = pairs[i]
    delta = lower - first
    j = i + 1
    stride = pairs[j][0] - first if j < len(pairs) and pairs[j][1] - pairs[j][0] == delta else 1
    if stride > 2:
        stride = 1
    while j < len(pairs) and pairs[j][0] - pairs[j - 1][0] == stride and pairs[j][1] - pairs[j][0] == delta:
        j += 1
    assert first >> 16 == lower >> 16 and pairs[j - 1][0] - first < 65536
    out += f'  {{0x{first & 65535:x}, 0x{lower & 65535:x}, {pairs[j-1][0]-first}, {stride}, {first >> 16}}},\n'
    i = j
out += '};\n'
for name, values in (('zero', zero), ('wide', wide - zero)):
    out += f'static const struct unicode_interval {{ uint16_t first,last; uint8_t plane; }} unicode_{name}_ranges[] = {{\n' if name == 'zero' else f'static const struct unicode_interval unicode_{name}_ranges[] = {{\n'
    for first, last in intervals(values):
        while first <= last:
            end = min(last, first | 65535)
            out += f'  {{0x{first & 65535:x}, 0x{end & 65535:x}, {first >> 16}}},\n'
            first = end + 1
    out += '};\n'
out += '#endif\n'
target = Path(__file__).resolve().parents[1] / 'firmware/unicode_text_data.h'
target.write_text(out)
print(f'Generated {target}')
