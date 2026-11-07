# Included stories

These two third-party stories are supplied for inclusion in the project as
redistributable examples. The original binaries are kept unchanged.
They are excluded from the project's Apache 2.0 license and retain their own
copyright and distribution terms, including the notices inside each game.

| Story | Included file | Version | Release / serial | SD card filename |
| --- | --- | --- | --- | --- |
| Madman | [madman.z3](madman.z3) | V3 | 1 / 260719 | `madman.z3` |
| Mars, 2049 AD | [mars2049ad.z5](mars2049ad.z5) | V5 | 8 / 250121 | `mars2049ad.z5` |

## Copy to a card

With the board powered off, run these commands from the project root, replacing
`/path/to/mounted/card` with the root of your FAT16/FAT32 microSD card:

```bash
mkdir -p /path/to/mounted/card/ZORK
cp -i story/madman.z3 story/mars2049ad.z5 /path/to/mounted/card/ZORK/
```

Keep the original filenames and extensions: no renaming or story conversion is
needed. The updated firmware supports `.dat`, `.z3` and `.z5`, regardless of
extension case, and was flashed and readback-verified on 2026-11-06.
The long-filename firmware displays `mars2049ad.z5` directly in the menu and
passed flash programming/readback on 2026-11-06. Older firmware shows the FAT
short alias, such as `MARS20~1.Z5`. Missing or damaged long-name records also
fall back to the alias. No card-file renaming is needed.

Safely eject the card, insert it, and reset the board. Select a story from the
alphabetically sorted menu. With the new 1,000-entry menu, enter N/P followed
by Enter to change pages, or enter a story's number directly from any page.
Mars uses the V5 display: use a serial terminal at
least 80 columns by 32 rows. Its opening waits for a key; press Space before
entering commands.

The first confirmed SAVE creates
`madman.sav` or `mars2049ad.sav` beside the story, with five positions per game.
No PC save preparation is needed. See [automatic per-story saves](../README.md#automatic-per-story-saves)
for naming limits and power-loss behavior. The automatic-save firmware passed
persistent flash programming/readback on 2026-11-07; physical save/restore and
power-cycle behavior for this exact build remain to be observed.

Keep each `.sav` alongside its story. Back it up with the board powered off;
no save-file download, generation or expansion step is needed.

## Credits and distribution notices

Madman's `ABOUT` command credits Ove Friman with the original VIC-20 BASIC game
and Fredrik Ramsberg with the Inform 6 + NAIL port. It identifies the upstream
project as <https://github.com/fredrikr/madman>. The supplied file is included
on the project owner's statement that it is redistributable; no Apache license
is granted to it. Preserve its embedded credits and any accompanying upstream
terms when redistributing.

Mars, 2049 AD provides credits and a License section in its `HELP` menu. The
distribution notice embedded in this supplied release states:

> This game can be distributed freely in unaltered form, as long as no profit is
> involved. The game file can be used to build disk images or binaries that
> include a Z-code interpreter. The homepage of the game, where the sourcecode
> can also be found, is https://fredrikr.itch.io/mars2049ad

## Validation

Both supplied files pass the project's V3/V5 memory-layout validation and their
Z-machine checksums. Native host-interpreter smoke checks reach both openings,
exercise Madman's `LOOK`, `INVENTORY` and `ABOUT`, and open Mars's `HELP` and
License menus. This does not establish complete-game compatibility, physical
HDMI/keyboard behavior, or save/restore behavior for these two games.

SHA-256 checksums of the original files:

```text
91a2fd7014af18f722dae224b7f53309dd5a71db608b052f7b82a56b5bf42cb1  madman.z3
43b525723ce8721bc58d5c2f160d60d6e277833770fa354a652f7faef9e1658d  mars2049ad.z5
```
