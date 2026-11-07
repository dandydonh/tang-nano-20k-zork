#!/usr/bin/env python3
"""Shared pools are unrelated files; sidecars retain indexed snapshot recovery."""
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from fat_helpers import FatImage
from indexed_pool_helpers import sparse_card, pool_lba, pool_read
from sd_image_fixture import make_image, project_files, POOL_SIZE
from save_pool_fixture import pool_header, checksum
from v3_fixture import make_story

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='zork-ignore-pool-') as directory:
    work=Path(directory);image=work/'card.img';reads=work/'reads.log';writes=work/'writes.log'

    def run(commands):
        reads.unlink(missing_ok=True);writes.unlink(missing_ok=True)
        env=dict(os.environ,ZORK_SD_IMAGE=str(image),ZORK_READ_LOG=str(reads),ZORK_WRITE_LOG=str(writes))
        result=subprocess.run([ROOT/'impl/zork-host'],input=commands,text=True,capture_output=True,env=env,timeout=30,check=True)
        assert 'CORE ERROR' not in result.stdout,result.stdout
        return result.stdout,list(map(int,reads.read_text().splitlines())),list(map(int,writes.read_text().splitlines())) if writes.exists() else []

    alpha=make_story()
    for fat in (16,32):
        header,size=pool_header(3,5)
        for contents in (bytes(POOL_SIZE),header+header+bytes(size-1024),b'bad index'+bytes(65536-9)):
            # Compare identical allocation/layout; only mark the old entry deleted.
            baseline=make_image([('ALPHA.Z3',alpha),('SAVES.BIN',contents)],fat,16 if fat==16 else 64,False)
            layout=FatImage(baseline);entry=layout.file_entry('SAVES.BIN')
            layout.data[entry]=0xe5;image.write_bytes(layout.data)
            _,without,changed=run('q\n');assert not changed
            image.write_bytes(baseline)
            _,with_pool,changed=run('q\n');assert with_pool==without and not changed
            pool_sectors=set(FatImage(baseline).sectors('SAVES.BIN'))
            assert not pool_sectors.intersection(with_pool)
            for commands in ('s\n0\nq\n','r\n0\nq\n','r\n1\n0\nq\n'):
                _,_,changed=run(commands);assert not changed and image.read_bytes()==baseline
            out,_,changed=run('n\ns\n5\nq\n');assert 'saved\n' in out
            after=FatImage(image.read_bytes());assert after.file_bytes('SAVES.BIN')==contents
            assert not pool_sectors.intersection(changed)
            old_entry=FatImage(baseline).data[entry:entry+32]
            assert after.data[entry:entry+32]==old_entry
            # Allocated chain links are preserved too, including both FAT copies.
            old=FatImage(baseline)
            for cluster in old.chain(old.entry_cluster(entry)):
                for copy in range(old.fats):
                    at=old.fat_offset(cluster,copy)
                    assert after.data[at:at+old.width]==old.data[at:at+old.width]
            saved=image.read_bytes()
            out,_,changed=run('r\n5\nl\nq\n')
            assert 'alpha moved' in out and not changed and image.read_bytes()==saved
            # Existing sidecar selection has identical reads with/without pool.
            _,present,_=run('q\n');after.data[entry]=0xe5;image.write_bytes(after.data)
            _,absent,_=run('q\n');assert present==absent
        print(f'PASS FAT{fat}: legacy/indexed/malformed pools ignored, identical startup reads, no pool data/FAT/entry writes, lazy creation, cancellation and existing-sidecar restore')

    # A cyclic allocated legacy chain must not affect play or automatic saves.
    layout=FatImage(baseline);chain=layout.chain(layout.entry_cluster(layout.file_entry('SAVES.BIN')))
    layout.set_next(chain[-1],chain[0]);image.write_bytes(layout.data)
    out,_,changed=run('s\n5\nq\n');assert 'saved\n' in out
    after=FatImage(image.read_bytes())
    for cluster in chain:
        assert after.next(cluster)==layout.next(cluster)
        at=layout.cluster_offset(cluster);assert after.data[at:at+512]==layout.data[at:at+512]
    print('PASS cyclic old pool chain ignored and preserved during automatic SAVE')

    # Duplicate or nonsensical old entries must not disable story discovery.
    for kind in ('duplicate','read-only','invalid cluster/size'):
        layout=FatImage(baseline);entry=layout.file_entry('SAVES.BIN')
        if kind=='duplicate':layout.data[entry+32:entry+64]=layout.data[entry:entry+32]
        elif kind=='read-only':layout.data[entry+11]|=1
        else:
            layout.set_entry_cluster(entry,0xffffffff)
            struct.pack_into('<I',layout.data,entry+28,0xffffffff)
        image.write_bytes(layout.data);before=image.read_bytes()
        out,trace,changed=run('s\n0\nr\n0\nq\n')
        assert 'Starting ALPHA.Z3' in out and 'Saves disabled' not in out
        assert not changed and image.read_bytes()==before
    print('PASS duplicate, read-only and invalid-geometry SAVES.BIN entries ignored during play/cancellation')

    # Sparse 1.22 GiB pool: compare exact boot read trace, without reading the
    # card into memory. Any old chain/index traversal would change that trace.
    layout=sparse_card(image,alpha,fragmented=True)
    entry=layout['directory_lba']*512+96
    with image.open('r+b') as stream:
        stream.seek(entry);original=stream.read(1);stream.seek(entry);stream.write(b'\xe5')
    _,without,changed=run('q\n');assert not changed
    with image.open('r+b') as stream:stream.seek(entry);stream.write(original)
    metadata=pool_read(image,layout,0,128)
    _,present,changed=run('q\n')
    assert without==present and len(present)<100 and not changed
    pool_data={pool_lba(layout,i) for i in range(128)}
    assert not pool_data.intersection(present)
    assert pool_read(image,layout,0,128)==metadata
    print(f'PASS fragmented 1.22 GiB SAVES.BIN: exact same {len(present)} boot reads as absent entry; no old index access or writes')

    # Indexed sidecar metadata must still reject unsupported ownership geometry.
    for kind in ('owners','positions','owner identity'):
        layout=FatImage(make_image(project_files(alpha,'ALPHA.Z3'),16,8,False))
        sectors=layout.sectors('ALPHA.SAV')
        if kind in ('owners','positions'):
            for sector in sectors[:2]:
                off=sector*512;header=bytearray(layout.data[off:off+512])
                struct.pack_into('<I',header,12 if kind=='owners' else 16,2 if kind=='owners' else 4)
                struct.pack_into('<I',header,508,checksum(header[:508]));layout.data[off:off+512]=header
        else:
            for sector in sectors[2:4]:
                off=sector*512;layout.data[off+8]^=1
                struct.pack_into('<I',layout.data,off+28,checksum(layout.data[off:off+28]))
        image.write_bytes(layout.data);before=image.read_bytes()
        out,_,changed=run('s\nq\n')
        assert 'Saves disabled' in out and not changed and image.read_bytes()==before,kind
    print('PASS indexed sidecars refuse foreign owners and invalid owner/position geometry')

    # Recover one damaged owner replica on confirmed SAVE. Read-only RESTORE
    # must not repair metadata, and any interrupted repair retains position 1.
    image.write_bytes(make_image(project_files(alpha,'ALPHA.Z3'),16,8,False))
    assert 'saved' in run('s\n1\nq\n')[0]
    layout=FatImage(image.read_bytes());sectors=layout.sectors('ALPHA.SAV')
    layout.data[sectors[2]*512+28]^=128
    image.write_bytes(layout.data);damaged=image.read_bytes()
    out,_,changed=run('r\n1\nl\nq\n')
    assert 'alpha home' in out and not changed and image.read_bytes()==damaged
    out,_,changed=run('n\ns\n5\nq\n')
    assert 'saved' in out and len(changed)==23
    assert set(changed)<=set(sectors[2:4]+sectors[4+4*512:4+5*512])
    repaired=FatImage(image.read_bytes()).file_bytes('ALPHA.SAV')
    assert repaired[1024:1056]==repaired[1536:1568]
    for cut in range(len(changed)):
        image.write_bytes(damaged)
        result=subprocess.run([ROOT/'impl/zork-host'],input='n\ns\n5\n',text=True,capture_output=True,
                              env=dict(os.environ,ZORK_SD_IMAGE=str(image),ZORK_CUT_AFTER_WRITES=str(cut)),timeout=30)
        assert result.returncode==99,(cut,result.stdout,result.stderr)
        out,_,changed=run('r\n1\nl\nq\n')
        assert 'alpha home' in out and not changed,(cut,out)
    print('PASS read-only owner recovery, scoped metadata repair and all 23 interrupted repair/snapshot writes')
