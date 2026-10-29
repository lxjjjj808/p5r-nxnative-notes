import hashlib
import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / 'webui/tools/replace_ipa_executable.py'


class IpaResourceUpdateTests(unittest.TestCase):
    def test_replaces_and_adds_resources_and_verifies_unchanged_content(self):
        scratch = REPO / '.webui-data/tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory)
            prefix = 'Payload/DmIOS.app/'
            old = {prefix + 'DmIOS': b'old host', prefix + 'dm/table.tsv': b'old table',
                   prefix + 'romfs/data': b'preserved game resource'}
            source, output = root / 'old.ipa', root / 'new.ipa'
            with zipfile.ZipFile(source, 'w') as archive:
                for name, data in old.items():
                    info = zipfile.ZipInfo(name)
                    info.extra = struct.pack('<HHQ', 1, 8, 2**32)
                    with archive.open(info, 'w', force_zip64=True) as stream:
                        stream.write(data)
            source.with_suffix('.verification.json').write_text(json.dumps(dict(
                file_sha256={name: hashlib.sha256(data).hexdigest() for name, data in old.items()},
                files=len(old), shader_keys=0, signed=False, runtime_tested=False)))
            host = root / 'host'
            host.mkdir()
            executable = b'new verified host'
            (host / 'DmIOS').write_bytes(executable)
            (host / 'link_report.json').write_text(json.dumps(dict(
                signed=False, ios_platform=2, sha256=hashlib.sha256(executable).hexdigest())))
            replacement, addition = root / 'table.tsv', root / 'new.metallib'
            replacement.write_bytes(b'new table\n')
            addition.write_bytes(b'MTLBnew shader')
            manifest = root / 'resources.json'
            manifest.write_text(json.dumps({prefix + 'dm/table.tsv': str(replacement),
                                            prefix + 'msl/new.metallib': str(addition)}))
            command = [sys.executable, str(TOOL), '--source', str(source), '--host', str(host),
                       '--out', str(output), '--resources-manifest', str(manifest)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.read(prefix + 'DmIOS'), executable)
                self.assertEqual(archive.read(prefix + 'dm/table.tsv'), b'new table\n')
                self.assertEqual(archive.read(prefix + 'romfs/data'), old[prefix + 'romfs/data'])
                self.assertEqual(archive.read(prefix + 'msl/new.metallib'), addition.read_bytes())
                self.assertTrue(all(info.extract_version < 45 for info in archive.infolist()))
                self.assertTrue(all(not info.extra for info in archive.infolist()))
            report = json.loads(output.with_suffix('.verification.json').read_text())
            self.assertEqual(report['files'], 4)
            self.assertTrue(report['archive_source_hashes_verified'])
            with zipfile.ZipFile(source, 'w') as archive:
                for name, data in old.items():
                    archive.writestr(name, b'corrupted' if name.endswith('/data') else data)
            command[command.index('--out') + 1] = str(root / 'tampered.ipa')
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / 'tampered.ipa').exists())
