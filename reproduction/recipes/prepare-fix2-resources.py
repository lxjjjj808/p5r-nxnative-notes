"""Validate completed shader outputs and prepare the fix2 bundle update."""
import json
from pathlib import Path
import plistlib
import zipfile

# Historical incremental recipe. Set all four environment inputs explicitly.
import os
root = Path(os.environ['P5R_BUILD'])
work = Path(os.environ['P5R_WORK'])
profile = Path(os.environ['P5R_PROFILE'])
source_ipa = Path(os.environ['P5R_SOURCE_IPA'])
version = 'b-bcd8a8e27f1b'
ios = root / 'metal-sample/ios' / version
mac = root / 'metal-sample/mac' / version
results = json.loads((mac / '_b_build.json').read_text(encoding='utf-8'))
assert len(results) == 30646 and all(row['st'] == 'ok' for row in results), 'Shader build incomplete'
stamp = dict(line.split('\t', 1) for line in (ios / 'inputs.tsv').read_text().splitlines() if line and not line.startswith('#'))
assert stamp['game'] == '01004B10157F2000'
table_header = '# chain ' + version + ' inputs ' + stamp['inputs'] + ' '
for name in ('c1_full.tsv', 'cb_extent.tsv'):
    assert (profile / name).read_text(encoding='utf-8').splitlines()[0].startswith(table_header), name
changes = json.loads((work / 'gsc-shaders/embedded-additions.json').read_text(encoding='utf-8'))
keys = set(changes['added']) | set(changes['affected_vertex_keys'])
prefix = 'Payload/DmIOS.app/'
resources = {}
for key in sorted(keys):
    library = ios / (key + '_b.metallib')
    with library.open('rb') as stream:
        assert stream.read(4) == b'MTLB', key
    reflection = json.loads((ios / (key + '_b.json')).read_text(encoding='utf-8'))
    assert reflection['chain'] == version[2:] and reflection['dm_ctl'] == key
    assert 'air64-apple-ios' in reflection['chain_metal']
    for suffix in ('_b.json', '_b.metallib', '_bf.json', '_bf.metallib', '_bv.json', '_bv.metallib'):
        path = ios / (key + suffix)
        if path.is_file():
            resources[prefix + 'msl/' + version + '/' + path.name] = str(path)
for name in ('shader_map.tsv', 'c1_full.tsv', 'cb_extent.tsv'):
    resources[prefix + 'dm/' + name] = str(profile / name)
resources[prefix + 'msl/' + version + '/inputs.tsv'] = str(ios / 'inputs.tsv')
with zipfile.ZipFile(source_ipa) as archive:
    info = plistlib.loads(archive.read(prefix + 'Info.plist'))
info['DMBuildLabel'] = 'P5R-M1-fix2'
info['DMShaderCount'] = 30646
plist = root / 'fix2-Info.plist'
plist.write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_BINARY))
resources[prefix + 'Info.plist'] = str(plist)
diagnostics = root / 'fix2-env.txt'
diagnostics.write_text('DM_NVN_SHDUMP=temp\n', encoding='ascii', newline='\n')
resources[prefix + 'dm/env.txt'] = str(diagnostics)
manifest = root / 'fix2-resources.json'
manifest.write_text(json.dumps(resources, indent=2), encoding='utf-8')
print(json.dumps(dict(shader_keys=len(results), refreshed_keys=len(keys), replacement_files=len(resources), inputs=stamp['inputs'], manifest=str(manifest))))
