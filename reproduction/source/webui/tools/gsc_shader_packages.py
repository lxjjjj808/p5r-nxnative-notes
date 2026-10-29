"""Convert extracted GFS0/GSC0 Switch shader resources into shader packages.

Uses nxnative's existing control/code validators. This prepares translation
inputs; it does not establish that the game or any target device is playable.
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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('--profile', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[2]
    os.environ['DM_GAME'] = str(args.profile.resolve())
    sys.path.insert(0, str(repo / 'dm/gfx/tools'))
    import shader_split as split
    keys = {}
    for path in sorted(args.source.glob('*.GSC')):
        data = path.read_bytes()
        if data[:4] != b'GFS0' or b'GSC0' not in data[:32] or b'HNSHV002' not in data:
            raise ValueError('Unsupported shader resource: ' + str(path))
        for match in re.finditer(split.CTL_MAGIC, data):
            start = match.start()
            if start + 0x760 > len(data):
                raise ValueError('Truncated control: ' + str(path))
            ctl_size = struct.unpack_from('<I', data, start + 0x20)[0]
            code_size = struct.unpack_from('<I', data, start + 0x704)[0]
            if not 0x760 <= ctl_size < 0x880 or start + ctl_size + code_size > len(data):
                raise ValueError('Invalid shader bounds: ' + str(path))
            ctl = data[start:start + ctl_size]
            code = data[start + ctl_size:start + ctl_size + code_size]
            stage = split.glslc_stage(ctl, code)
            where = f'/CPK/{path.name}#RAW@{start:#x}'
            if not stage or split.check(where, stage, ctl, code):
                raise ValueError('Invalid control/code pair: ' + where)
            key = split.skey(ctl, code)
            if key in keys and not split.same_shader((ctl, code), keys[key][2:]):
                raise ValueError('Shader key collision: ' + key)
            keys.setdefault(key, (where, stage, ctl, code))
    if not keys:
        raise ValueError('No validated shaders; refusing to emit empty packages')
    packages = args.out / 'packages'
    tables = args.out / 'tables'
    packages.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    rows, counts, streams = [], collections.Counter(), {}
    try:
        for key, (where, stage, ctl, code) in sorted(keys.items()):
            filename = f'{stage}_gsc.bin'
            if filename not in streams:
                streams[filename] = (packages / filename).open('wb')
            record = bytearray(b'BTCDBTCD' + bytes(0x30))
            struct.pack_into('<II', record, 0x28, len(ctl), len(code))
            record += code + ctl
            if record.count(b'BTCDBTCD') != 1 or record.find(split.CTL_MAGIC) != 0x38 + len(code):
                raise ValueError('Ambiguous package delimiters: ' + key)
            streams[filename].write(record)
            rows.append(f'{filename}\t{counts[stage]}\t{split.STAGE_NAME[stage]}\t{key}\t{where}\n')
            counts[stage] += 1
    finally:
        for stream in streams.values():
            stream.close()
    (tables / 'shader_map.tsv').write_text('# Validated GFS0/GSC0 control/code pairs; generated, not runtime-tested.\npackage\tindex\tstage\tdm_ctl_sha16\tsource\n' + ''.join(rows), encoding='utf-8')
    (tables / 'shader_map.tsv.conflicts.tsv').write_text('# No PC shader mappings: all keys come from the supplied Switch resources.\n', encoding='utf-8')
    facts = {}
    for key, (_, stage, ctl, _) in keys.items():
        if stage == 'cs':
            x, y, z, shared = struct.unpack_from('<4I', ctl, 0x748)
            if not x * y * z:
                raise ValueError('Empty compute group: ' + key)
            facts[key] = dict(local=[x, y, z], shared=(shared + 15) // 16 * 16)
    (tables / 'shader_facts.tsv').write_text('# Generated compute shader facts.\n' + ''.join(k + '\t' + json.dumps(v) + '\n' for k, v in sorted(facts.items())), encoding='utf-8')
    pairs, _ = split.separable_pairs(keys)
    (tables / 'shader_pairs.tsv').write_text('# Conservative varying coverage for separately bound stages.\n' + ''.join(a + '\t' + b + '\n' for a, b in sorted(pairs)), encoding='utf-8')
    print(json.dumps(dict(shaders=len(keys), stages=dict(counts), pairs=len(pairs), sample_keys=list(sorted(keys))[:2])))


if __name__ == '__main__':
    main()
