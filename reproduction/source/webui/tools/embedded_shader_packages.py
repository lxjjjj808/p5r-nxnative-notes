"""Append validated, adjacent embedded shader records to an external profile.

The full control/code bytes are validated and retain their Switch content keys.
Existing package indices remain unchanged, preserving their shader cache keys.
"""
import argparse
import collections
import json
import os
from pathlib import Path
import re
import struct
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--packages', type=Path, required=True)
    args = parser.parse_args()
    os.environ['DM_GAME'] = str(args.profile.resolve())
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dm/gfx/tools'))
    import shader_split as split
    table = args.profile / 'shader_map.tsv'
    original = table.read_text(encoding='utf-8')
    mapping = {}
    for line in original.splitlines():
        if not line or line.startswith(('#', 'package\t')):
            continue
        package, index, stage, key, source = line.split('\t', 4)
        mapping[package, int(index)] = (key, source)
    keys = {}
    for package in sorted({p for p, _ in mapping}):
        data = (args.packages / package).read_bytes()
        position = index = 0
        while position < len(data):
            if data[position:position + 8] != b'BTCDBTCD':
                raise ValueError('Invalid existing package boundary')
            nctl, ncode = struct.unpack_from('<II', data, position + 0x28)
            code = data[position + 0x38:position + 0x38 + ncode]
            ctl = data[position + 0x38 + ncode:position + 0x38 + ncode + nctl]
            key, source = mapping[package, index]
            if split.skey(ctl, code) != key:
                raise ValueError('Existing package key mismatch: ' + key)
            keys[key] = (source, split.glslc_stage(ctl, code), ctl, code)
            position += 0x38 + ncode + nctl
            index += 1
    old = set(keys)
    data = args.image.read_bytes()
    for match in re.finditer(re.escape(split.CTL_MAGIC), data):
        offset = match.start()
        if offset % 4 or offset + 0x760 > len(data):
            continue
        nctl = struct.unpack_from('<I', data, offset + 0x20)[0]
        ncode = struct.unpack_from('<I', data, offset + 0x704)[0]
        if not 0x760 <= nctl <= 0x880 or not 0 < ncode < 0x100000 or offset + nctl + ncode > len(data):
            continue
        ctl = data[offset:offset + nctl]
        code = data[offset + nctl:offset + nctl + ncode]
        stage = split.glslc_stage(ctl, code)
        if not stage or split.check('embedded image', stage, ctl, code):
            continue
        key = split.skey(ctl, code)
        if key in keys and not split.same_shader((ctl, code), keys[key][2:]):
            raise ValueError('Embedded shader key collision')
        keys.setdefault(key, (f'/ExeFS/main#RAW@{offset:#x}', stage, ctl, code))
    added = sorted(set(keys) - old)
    if not added:
        # Preserve the original update manifest when preparation is repeated.
        print(json.dumps(dict(added=0, unchanged=True)))
        return
    counts = collections.Counter()
    streams, rows, facts = {}, [], []
    try:
        for key in added:
            where, stage, ctl, code = keys[key]
            package = stage + '_embedded.bin'
            if package not in streams:
                if (args.packages / package).exists():
                    raise ValueError('Refusing to overwrite an existing embedded package')
                streams[package] = (args.packages / package).open('wb')
            record = bytearray(b'BTCDBTCD' + bytes(0x30))
            struct.pack_into('<II', record, 0x28, len(ctl), len(code))
            streams[package].write(record + code + ctl)
            rows.append(f'{package}\t{counts[stage]}\t{split.STAGE_NAME[stage]}\t{key}\t{where}\n')
            counts[stage] += 1
            if stage == 'cs':
                x, y, z, shared = struct.unpack_from('<4I', ctl, 0x748)
                if not x * y * z:
                    raise ValueError('Empty embedded compute group')
                facts.append(key + '\t' + json.dumps(dict(local=[x, y, z], shared=(shared + 15) // 16 * 16)) + '\n')
    finally:
        for stream in streams.values():
            stream.close()
    table.write_text(original + ''.join(rows), encoding='utf-8', newline='\n')
    fact_path = args.profile / 'shader_facts.tsv'
    fact_path.write_text(fact_path.read_text(encoding='utf-8') + ''.join(facts), encoding='utf-8', newline='\n')
    pairs, cover = split.separable_pairs(keys)
    pair_path = args.profile / 'shader_pairs.tsv'
    previous = {tuple(line.split('\t')) for line in pair_path.read_text().splitlines() if line and not line.startswith('#')}
    pair_path.write_text('# Conservative varying coverage for separately bound stages.\n' + ''.join(a + '\t' + b + '\n' for a, b in sorted(pairs)), encoding='utf-8', newline='\n')
    affected = sorted({a for a, _ in pairs ^ previous})
    result = dict(added=added, stages=dict(counts), affected_vertex_keys=affected, pixel_cover=cover)
    (args.packages.parent / 'embedded-additions.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(added=len(added), stages=dict(counts), affected_vertices=len(affected), pixel_cover=cover)))


if __name__ == '__main__':
    main()
