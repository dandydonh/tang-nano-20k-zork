#!/usr/bin/env python3
"""Board-created sidecars checked with independent FAT tools and fault injection."""
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from fat_helpers import FatImage
from v3_fixture import make_story
from v5_fixture import make_story as make_v5_story
ROOT = Path(__file__).resolve().parents[1]
from sd_image_fixture import make_image


def command(*args):
    result = subprocess.run(list(map(str,args)), capture_output=True)
    assert result.returncode == 0, (args, result.stdout, result.stderr)
    return result.stdout


with tempfile.TemporaryDirectory(prefix='zork-auto-save-') as directory:
    work = Path(directory)
    image = work/'card.img'
    trace = work/'writes.log'

    def play(commands, cut=None, **extra):
        env = dict(os.environ, ZORK_SD_IMAGE=str(image), **{k:str(v) for k,v in extra.items()})
        if cut is not None: env['ZORK_CUT_AFTER_WRITES'] = str(cut)
        result = subprocess.run([ROOT/'impl/zork-host'],input=commands,text=True,capture_output=True,env=env,timeout=45)
        assert result.returncode == (99 if cut is not None else 0), (result.stdout,result.stderr)
        assert 'CORE ERROR' not in result.stdout and 'testfailed' not in result.stdout, result.stdout
        return result.stdout

    def clean():
        layout=FatImage(image.read_bytes())
        volume=work/'volume.img';volume.write_bytes(layout.data[layout.base*512:])
        command('fsck.fat','-n',volume)

    def read(name):
        layout=FatImage(image.read_bytes())
        return command('mtype','-i',f'{image}@@{layout.base*512}',f'::/ZORK/{name}')

    command('gcc','-std=c99','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
            '-DHOST','-Ifirmware','firmware/storage.c','firmware/unicode.c','tests/auto_storage_tb.c','-o','impl/auto-storage-test')
    image.write_bytes(make_image([('ALPHA.Z3',make_story())],16,8,False))
    print(command(ROOT/'impl/auto-storage-test',image).decode().strip())
    clean()

    alpha,beta=make_story(),make_story(name='beta',release=2)
    for fat,partitioned in ((16,False),(16,True),(32,False),(32,True)):
        original=make_image([('ALPHA.Z3',alpha),('BETA.Z3',beta)],fat,8 if fat==16 else 64,partitioned)
        image.write_bytes(original)
        for action in ('1\nq\n','1\nr\n0\nq\n','1\ns\n0\nq\n','1\nr\n1\nq\n'):
            play(action);assert image.read_bytes()==original
        assert 'saved\n' in play('1\nn\ns\n5\nq\n')
        assert len(read('ALPHA.sav'))==1312768
        assert 'alpha moved' in play('1\nr\n5\nl\nq\n')
        assert 'saved\n' in play('2\ns\n1\nq\n')
        alpha_save=read('ALPHA.sav');beta_save=read('BETA.sav')
        assert 'saved\n' in play('1\ns\n1\nq\n')
        assert read('BETA.sav')==beta_save
        assert read('ALPHA.Z3')==alpha and read('BETA.Z3')==beta
        # Read-only sidecar and foreign same-stem release never get overwritten.
        layout=FatImage(image.read_bytes());entry=layout.file_entry('ALPHA.SAV')
        layout.data[entry+11]|=1;image.write_bytes(layout.data);before=image.read_bytes()
        assert 'Saves disabled' in play('1\ns\nq\n') and image.read_bytes()==before
        layout.data[entry+11]&=~1
        story=layout.sectors('ALPHA.Z3')[0]*512;layout.data[story+3]^=1
        image.write_bytes(layout.data);before=image.read_bytes()
        assert 'Saves disabled' in play('1\ns\nq\n') and image.read_bytes()==before
        clean()
    print('PASS FAT16/FAT32 superfloppy/MBR: lazy allocation, cancellation, absent restore, five positions, reset, isolation, read-only and foreign identity refusal')

    image.write_bytes(make_image([('ALPHA.Z3',alpha)],16,8,False))
    assert 'saved' in play('n\ns\n5\nq\n')
    previous=image.read_bytes()
    assert 'saved' in play('s\n5\ny\nq\n')
    completed_pair=image.read_bytes()
    layout=FatImage(completed_pair);sectors=layout.sectors('ALPHA.SAV')
    # Newest bank B payload corruption restores bank A for the same position.
    layout.data[sectors[4+4*512+256+1]*512+100]^=128
    image.write_bytes(layout.data)
    assert 'alpha moved' in play('r\n5\nl\nq\n')
    for label in ('header A','header B','both headers','owner A','both owners','short chain','cycle','directory overlap'):
        layout=FatImage(previous);sectors=layout.sectors('ALPHA.SAV');entry=layout.file_entry('ALPHA.SAV')
        if label in ('header A','header B','both headers'):
            for n in ([0,1] if label=='both headers' else [0 if label=='header A' else 1]):layout.data[sectors[n]*512+100]^=128
        elif label in ('owner A','both owners'):
            for n in ([2,3] if label=='both owners' else [2]):layout.data[sectors[n]*512+28]^=128
        elif label=='short chain':layout.set_next(layout.entry_cluster(entry),layout.eoc)
        elif label=='cycle':layout.set_next(layout.chain(layout.entry_cluster(entry))[-1],layout.entry_cluster(entry))
        else:layout.set_entry_cluster(entry,layout.entry_cluster(layout.entry('ZORK')))
        image.write_bytes(layout.data);before=image.read_bytes()
        if label in ('header A','header B','owner A'):
            assert 'alpha moved' in play('r\n5\nl\nq\n')
        else:
            assert 'Saves disabled' in play('s\nq\n') and image.read_bytes()==before,label
    print('PASS sidecar snapshot fallback, redundant metadata recovery, malformed/cyclic/protected chains and damaged-owner refusal')

    # Recycle a file that contains valid headers/payloads for this SAME story
    # in both banks of all positions. Lazy payload initialization must invalidate
    # every old commit header before publishing the replacement file.
    image.write_bytes(make_image([('ALPHA.Z3',alpha)],16,8,False))
    commands='n\n'+''.join(f's\n{slot}\n' for slot in range(1,6))
    commands+=''.join(f's\n{slot}\ny\n' for slot in range(1,6))+'q\n'
    assert play(commands).count('saved\n')==10
    old=FatImage(image.read_bytes());old_sectors=old.sectors('ALPHA.SAV')
    recycled=old.file_bytes('ALPHA.SAV')
    assert all(recycled[(4+bank*256)*512:(4+bank*256)*512+4]!=bytes(4) for bank in range(10))
    command('mdel','-i',image,'::/ZORK/ALPHA.sav')
    trace.unlink(missing_ok=True)
    assert 'saved' in play('s\n5\nq\n',ZORK_WRITE_LOG=trace)
    writes=list(map(int,trace.read_text().splitlines()))
    fresh=FatImage(image.read_bytes());sectors=fresh.sectors('ALPHA.SAV')
    assert sectors==old_sectors and len(writes)<100
    for bank in range(10):
        header=fresh.data[sectors[4+bank*256]*512:sectors[4+bank*256]*512+512]
        if bank!=8:assert header==bytes(512),(bank,header[:32])
    # Unwritten payload is deliberately preserved, demonstrating why clearing
    # the bank commits, rather than relying on fresh-looking data, matters.
    assert fresh.data[sectors[5]*512:sectors[6]*512]==old.data[old_sectors[5]*512:old_sectors[6]*512]
    output=play('r\n0\nq\n')
    assert '1. Empty\n2. Empty\n3. Empty\n4. Empty\n5. Saved' in output,output
    # Damage the only committed new snapshot: recycled bank B must not offer
    # its old state as an apparently valid recovery fallback.
    fresh.data[sectors[4+4*512+1]*512+100]^=128
    image.write_bytes(fresh.data)
    assert 'restorefailed' in play('r\n5\nq\n')
    clean()
    print(f'PASS recycled same-story snapshots: ten bank headers invalidated, stale payload ignored, no old-bank recovery; first SAVE {len(writes)} sector writes')

    # Independently formatted cards, multi-sector clusters, VFAT and directory
    # growth. A collision on the generated short alias must choose another one.
    for fat,spc,size in ((16,4,16),(32,2,128)):
        with image.open('wb') as f:f.truncate(size*1024*1024)
        command('mkfs.fat','-F',fat,'-s',spc,image);command('mmd','-i',image,'::/ZORK')
        names=['A very long adventure title.z3','VFive adventure.z5','x'*251+'.dat']
        for name,data in zip(names,[alpha,make_v5_story(),alpha]):
            source=work/name;source.write_bytes(data);command('mcopy','-i',image,source,'::/ZORK/')
        source=work/'note';source.write_bytes(b'keep me')
        command('mcopy','-i',image,source,'::/ZORK/ZS000000.SAV')
        # Fill directory to within one slot of cluster boundary, forcing an LFN
        # append to grow the existing directory into a freshly allocated cluster.
        layout=FatImage(image.read_bytes());first=layout.entry_cluster(layout.entry('ZORK'))
        chain=layout.chain(first);offsets=[layout.cluster_offset(c)+i for c in chain for i in range(0,spc*512,32)]
        end=next(i for i,off in enumerate(offsets) if not layout.data[off])
        template=bytearray(32);template[11]=0x20;template[16]=template[18]=template[24]=0x21
        for i in range(end,len(offsets)-1):
            template[:11]=(f'P{i:07}TXT').encode();layout.data[offsets[i]:offsets[i]+32]=template
        image.write_bytes(layout.data)
        assert 'saved\n' in play('1\nn\ns\n5\nq\n')
        assert len(read('A very long adventure title.sav'))==1312768
        assert read('ZS000000.SAV')==b'keep me'
        assert 'alpha moved' in play('1\nr\n5\nl\nq\n')
        assert 'saved' in play('2\ns\n3\nn\nr\n3\nq\n')
        assert 'restored' in play('2\nr\n3\nq\n')
        assert 'saved' in play('3\ns\n2\nq\n')
        assert len(read('x'*251+'.sav'))==1312768
        clean()
    print('PASS independent mkfs/mtools FAT16/FAT32: V3/V5, long names through 255 units, alias collision, directory growth and fsck')

    # Bad-cluster markers are valid FAT allocations and force isolated free
    # clusters across the volume, with no contiguous run large enough to use.
    image.write_bytes(make_image([('ALPHA.Z3',alpha)],16,8,False))
    layout=FatImage(image.read_bytes())
    for cluster in range(2,layout.clusters+2):
        if cluster%2 and not layout.next(cluster):layout.set_next(cluster,0xfff7)
    image.write_bytes(layout.data)
    assert 'saved' in play('s\n5\nq\n');clean()
    after=FatImage(image.read_bytes());chain=after.chain(after.entry_cluster(after.file_entry('ALPHA.SAV')))
    assert len(chain)==2564 and all(b-a==2 for a,b in zip(chain,chain[1:]))
    assert 'alpha home' in play('r\n5\nl\nq\n')
    print('PASS fragmented save creation across 2564 isolated free clusters')

    original=make_image([('ALPHA.Z3',alpha)],16,8,False)
    for kind in ('directory read only','full','fat mismatch','too long','active fat'):
        layout=FatImage(original)
        if kind=='directory read only':layout.data[layout.entry('ZORK')+11]|=1
        elif kind=='full':
            for c in range(2,layout.clusters+2):
                if layout.next(c)==0:layout.set_next(c,0xfff7)
        elif kind=='fat mismatch':layout.data[layout.fat_offset(20,1)]=1
        elif kind=='too long':
            image.write_bytes(original)
            target='a'*252+'.z3'
            source=work/target;source.write_bytes(alpha)
            command('mdel','-i',image,'::/ZORK/ALPHA.Z3')
            command('mcopy','-i',image,source,'::/ZORK/')
            layout=FatImage(image.read_bytes())
        else:
            layout=FatImage(make_image([('ALPHA.Z3',alpha)],32,64,False))
            struct.pack_into('<H',layout.data,40,0x81)
            at=layout.reserved*512;layout.data[at:at+layout.fat_size*512]=bytes(layout.fat_size*512)
        image.write_bytes(layout.data);before=image.read_bytes()
        result=play('s\n1\nq\n')
        if kind=='active fat':
            assert 'saved' in result;assert image.read_bytes()[at:at+layout.fat_size*512]==before[at:at+layout.fat_size*512]
        else:
            assert 'savefailed' in result and image.read_bytes()==before, (kind,result)
    image.write_bytes(original);assert 'savefailed' in play('s\n1\nq\n',ZORK_READ_ONLY=1);assert image.read_bytes()==original
    print('PASS full/read-only media, FAT mirror disagreement, unrepresentable names and active-FAT write isolation')

    image.write_bytes(original);trace.unlink(missing_ok=True)
    assert 'saved' in play('n\ns\n5\nq\n',ZORK_WRITE_LOG=trace)
    writes=list(map(int,trace.read_text().splitlines()));completed=image.read_bytes()
    layout=FatImage(original);after=FatImage(completed)
    # All writes are FAT sectors, existing directory sectors, or the new file.
    dirs={layout.cluster_lba(c)+s for c in layout.chain(layout.entry_cluster(layout.entry('ZORK'))) for s in range(layout.spc)}
    fats=set(range(layout.reserved,layout.reserved+layout.fats*layout.fat_size))
    allowed=dirs|fats|set(after.sectors('ALPHA.SAV'))
    assert set(writes)<=allowed
    for sector in range(len(original)//512):
        if sector not in allowed:assert original[sector*512:(sector+1)*512]==completed[sector*512:(sector+1)*512]
    # Representative cuts cover FAT replica separation, initialization, staging,
    # publication and every snapshot write. Whole-sector cuts can leave lost
    # allocations; they must preserve pre-existing files and never expose junk.
    fat_end=next(i for i,lba in enumerate(writes) if lba not in fats)
    publish=max(i for i,lba in enumerate(writes) if lba in dirs)
    cuts=sorted({0,1,2,fat_end-1,fat_end,fat_end+1,publish-2,publish-1,publish,*range(publish+1,len(writes))})
    for cut in cuts:
        image.write_bytes(original);play('n\ns\n5\n',cut=cut)
        broken=FatImage(image.read_bytes());assert broken.file_bytes('ALPHA.Z3')==alpha
        if cut>publish:
            clean();assert 'saved' in play('s\n5\nq\n')
        else:
            # fsck independently diagnoses lost clusters/FAT mirror differences;
            # this is documented, and no automatic repair is attempted.
            result=subprocess.run(['fsck.fat','-n',image],capture_output=True)
            assert result.returncode in (0,1),result.stdout
    # Reported errors before publication roll allocations back. Torn writes of
    # allocation/data are safe to roll back; a torn publication retains clusters.
    for failed in (0,1,fat_end,fat_end+1,publish-1,publish):
        for torn in (0,17,257):
            image.write_bytes(original)
            out=play('s\n5\nq\n',ZORK_FAIL_WRITE=failed,ZORK_TORN_BYTES=torn)
            assert 'savefailed' in out
            assert FatImage(image.read_bytes()).file_bytes('ALPHA.Z3')==alpha
            if failed<publish:clean()
    print(f'PASS write bounds, {len(cuts)} interruption boundaries and 18 failed/torn metadata/data writes; pre-existing story preserved')

    # FAT32 failure cases include both FSInfo copies and both directory-tail
    # FAT replicas, crossing the old/new directory-cluster boundary.
    layout=FatImage(make_image([('ALPHA.Z3',alpha)],32,64,False))
    directory_cluster=layout.entry_cluster(layout.entry('ZORK'))
    directory_lba=layout.cluster_lba(directory_cluster)
    for row in range(3,15):
        entry=bytearray(32);entry[:11]=f'P{row:07}TXT'.encode();entry[11]=32
        entry[16]=entry[18]=entry[24]=0x21
        layout.data[directory_lba*512+row*32:directory_lba*512+(row+1)*32]=entry
    original=bytes(layout.data);image.write_bytes(original);trace.unlink(missing_ok=True)
    assert 'saved' in play('n\ns\n5\nq\n',ZORK_WRITE_LOG=trace);clean()
    writes=list(map(int,trace.read_text().splitlines()));after=FatImage(image.read_bytes())
    dirs={after.cluster_lba(c) for c in after.chain(directory_cluster)}
    fats=set(range(layout.reserved,layout.reserved+layout.fats*layout.fat_size))
    allowed=dirs|fats|{1,7}|set(after.sectors('ALPHA.SAV'))
    assert set(writes)<=allowed
    first_data=next(i for i,lba in enumerate(writes) if lba not in fats|{1,7})
    tail_updates=[i for i,lba in enumerate(writes) if lba in fats and i>first_data]
    assert len(tail_updates)==2
    publish=max(i for i,lba in enumerate(writes) if lba in dirs)
    for failed in sorted({0,1,2,first_data,*tail_updates,publish-1,publish}):
        image.write_bytes(original)
        assert 'savefailed' in play('s\n5\nq\n',ZORK_FAIL_WRITE=failed,ZORK_TORN_BYTES=257)
        assert FatImage(image.read_bytes()).file_bytes('ALPHA.Z3')==alpha
        if failed<publish:clean()
    for cut in (0,1,2,*tail_updates,publish-1,publish,publish+1):
        image.write_bytes(original);play('s\n5\n',cut=cut)
        assert FatImage(image.read_bytes()).file_bytes('ALPHA.Z3')==alpha
        if cut>publish:clean()
        else:
            result=subprocess.run(['fsck.fat','-n',image],capture_output=True)
            assert result.returncode in (0,1),result.stdout
    print('PASS FAT32 FSInfo/backup and directory-growth tail-link failures, torn writes and interruption boundaries')

print('PASS automatic per-story .sav creation')
