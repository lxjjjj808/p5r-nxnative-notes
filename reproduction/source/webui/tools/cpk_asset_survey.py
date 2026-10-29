"""Survey CPK resources without changing the archive or loading it all into RAM.

Requires the optional cricodecs package. Signature hits are candidates, not
validated shaders. Outputs contain metadata only, never game payloads or keys.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct


def survey(path, limit_mb=256):
    from cricodecs import cpk
    archive = cpk.load(str(path))
    entries = archive.file_infos()
    formats, extensions = Counter(), Counter()
    hits, skipped, errors = [], [], []
    texture_bytes = expanded_bytes = 0
    signatures = {
        'GLSLC': bytes.fromhex('91688619'),
        'control': bytes.fromhex('34127698'),
        'BNSH': b'BNSH\0\0\0\0',
    }
    for index, entry in enumerate(entries):
        ext = Path(entry.filename).suffix.upper()
        extensions[ext] += 1
        if ext in ('.AWB', '.ACB', '.USM'):
            continue
        if entry.extract_size > limit_mb * 1024**2:
            skipped.append(dict(index=index, path=entry.full_path,
                                bytes=entry.extract_size, reason='size limit'))
            continue
        try:
            data = archive.file_bytes(index)
        except RuntimeError as error:
            errors.append(dict(index=index, path=entry.full_path, error=str(error)))
            continue
        if data.startswith(b'DDS ') and len(data) >= 128:
            height, width = struct.unpack_from('<II', data, 12)
            fourcc = data[84:88].decode('ascii', errors='replace').rstrip('\0')
            formats[fourcc or 'uncompressed'] += 1
            texture_bytes += len(data)
            # Base level only: not a runtime RAM prediction (no residency/mips).
            expanded_bytes += width * height * 4
        else:
            found = {name: data.find(magic) for name, magic in signatures.items()
                     if magic in data}
            if found:
                hits.append(dict(index=index, path=entry.full_path,
                                 bytes=len(data), signatures=found))
        if index % 2000 == 0:
            print(f'{path.name}: {index}/{len(entries)} entries', flush=True)
    return dict(archive=str(path), entries=len(entries), extensions=dict(extensions),
                dds_formats=dict(formats), sampled_dds_file_bytes=texture_bytes,
                sampled_rgba8_base_level_bytes=expanded_bytes,
                signature_candidates=hits, skipped=skipped, errors=errors,
                limitations=['Signature hits require control/code pairing validation.',
                             'DDS counts exclude textures embedded in other assets.',
                             'Size-limited and audio/video entries were not scanned.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', type=Path, nargs='+')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--max-entry-mb', type=int, default=256)
    args = parser.parse_args()
    if args.max_entry_mb <= 0:
        parser.error('--max-entry-mb must be positive')
    reports = [survey(path.resolve(), args.max_entry_mb) for path in args.archives]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(reports, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    for report in reports:
        print(json.dumps({key: report[key] for key in ('archive', 'entries', 'dds_formats')}, ensure_ascii=True))
        print(f"Signature candidates: {len(report['signature_candidates'])}; errors: {len(report['errors'])}")


if __name__ == '__main__':
    main()
