"""Replace a verified unsigned IPA's executable without reopening loose resources.

Verify all existing resource hashes during the copy, then verify the complete
new archive. This is for host-only fixes that keep shader/profile inputs intact.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import zipfile


def without_zip64(extra):
    """Discard source offsets/sizes; ZipFile regenerates needed ZIP64 fields."""
    output = bytearray()
    position = 0
    while position < len(extra):
        if position + 4 > len(extra):
            raise ValueError('Truncated ZIP extra field')
        kind, length = struct.unpack_from('<HH', extra, position)
        end = position + 4 + length
        if end > len(extra):
            raise ValueError('Truncated ZIP extra field data')
        if kind != 1:
            output.extend(extra[position:end])
        position = end
    return bytes(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--host', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--resources-manifest', type=Path,
                        help='JSON mapping bundle archive paths to replacement or added files')
    args = parser.parse_args()
    if args.source.resolve() == args.out.resolve():
        parser.error('Source and output must be different files')
    report = json.loads(args.source.with_suffix('.verification.json').read_text())
    link = json.loads((args.host / 'link_report.json').read_text())
    executable = (args.host / 'DmIOS').read_bytes()
    executable_hash = hashlib.sha256(executable).hexdigest()
    if link['signed'] or link['ios_platform'] != 2 or link['sha256'] != executable_hash:
        raise ValueError('Expected a verified unsigned iOS executable')
    target = 'Payload/DmIOS.app/DmIOS'
    expected = report['file_sha256']
    hashes = dict(expected)
    hashes[target] = executable_hash
    resources = json.loads(args.resources_manifest.read_text(encoding='utf-8')) if args.resources_manifest else {}
    for name, path in resources.items():
        if not name.startswith('Payload/DmIOS.app/') or '..' in Path(name).parts or name == target:
            raise ValueError('Invalid replacement bundle path: ' + name)
        if not Path(path).is_file():
            raise ValueError('Replacement resource does not exist: ' + path)
    temporary = args.out.with_suffix('.ipa.partial')
    with zipfile.ZipFile(args.source) as source, zipfile.ZipFile(temporary, 'w', allowZip64=True) as output:
        infos = source.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or set(names) != set(expected) or target not in expected:
            raise ValueError('Source archive inventory differs from its verification report')
        additions = set(resources) - set(names)
        for name in sorted(additions):
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED if name.endswith('.metallib') else zipfile.ZIP_DEFLATED
            info.file_size = Path(resources[name]).stat().st_size
            infos.append(info)
        # Keep small graphics resources below the 4 GiB boundary, and avoid
        # unnecessary ZIP64 local headers in sideloaders that parse those files.
        infos.sort(key=lambda info: (info.file_size >= 64 * 1024 * 1024, info.file_size if info.file_size >= 64 * 1024 * 1024 else 0))
        for index, info in enumerate(infos, 1):
            destination = copy.copy(info)
            destination.extra = without_zip64(info.extra)
            destination.extract_version = destination.create_version = 20
            digest = hashlib.sha256()
            replacement = resources.get(info.filename)
            if info.filename == target or replacement:
                if info.filename in expected:
                    with source.open(info) as reader:
                        while block := reader.read(4 * 1024 * 1024):
                            digest.update(block)
                    if digest.hexdigest() != expected[info.filename]:
                        raise ValueError('Source content hash mismatch: ' + info.filename)
                replacement_bytes = executable if info.filename == target else Path(replacement).read_bytes()
                destination.file_size = len(replacement_bytes)
                hashes[info.filename] = hashlib.sha256(replacement_bytes).hexdigest()
                with output.open(destination, 'w', force_zip64=destination.file_size >= zipfile.ZIP64_LIMIT) as writer:
                    writer.write(replacement_bytes)
            else:
                with source.open(info) as reader, output.open(destination, 'w', force_zip64=info.file_size >= zipfile.ZIP64_LIMIT) as writer:
                    while block := reader.read(4 * 1024 * 1024):
                        digest.update(block)
                        writer.write(block)
                if digest.hexdigest() != expected[info.filename]:
                    raise ValueError('Source content hash mismatch: ' + info.filename)
            if index % 10000 == 0:
                print(f'Repacked {index}/{len(infos)} verified files', flush=True)
    print('Verifying every new archive entry', flush=True)
    with zipfile.ZipFile(temporary) as output:
        for info in output.infolist():
            digest = hashlib.sha256()
            with output.open(info) as reader:
                while block := reader.read(4 * 1024 * 1024):
                    digest.update(block)
            if digest.hexdigest() != hashes[info.filename]:
                raise ValueError('Output content hash mismatch: ' + info.filename)
    temporary.replace(args.out)
    report.update(ipa=str(args.out.resolve()), bytes=args.out.stat().st_size,
                  file_sha256=hashes, runtime_tested=False, signed=False,
                  files=len(hashes),
                  source_ipa=str(args.source.resolve()), executable_sha256=executable_hash,
                  archive_source_hashes_verified=True)
    if args.resources_manifest:
        report['resources_manifest'] = str(args.resources_manifest.resolve())
        map_path = resources.get('Payload/DmIOS.app/dm/shader_map.tsv')
        if map_path:
            report['shader_keys'] = len({line.split('\t')[3] for line in Path(map_path).read_text(encoding='utf-8').splitlines()
                                        if line and not line.startswith(('#', 'package\t'))})
    args.out.with_suffix('.verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('ipa', 'bytes', 'files', 'shader_keys', 'signed', 'runtime_tested')}), flush=True)


if __name__ == '__main__':
    main()
