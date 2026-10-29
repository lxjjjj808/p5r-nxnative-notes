import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]


def shader(stage, inputs=0):
    code = bytearray(0x200)
    code[:4] = bytes.fromhex('78563412')
    struct.pack_into('<I', code, 0x30, (stage << 10) | 0x61)
    struct.pack_into('<I', code, 0x48, inputs)
    control = bytearray(0x760)
    control[:4] = bytes.fromhex('34127698')
    struct.pack_into('<I', control, 0x20, len(control))
    struct.pack_into('<I', control, 0x704, len(code))
    key = hashlib.sha256(control + code).hexdigest()[:16]
    return key, control, code


def record(control, code):
    header = bytearray(b'BTCDBTCD' + bytes(0x30))
    struct.pack_into('<II', header, 0x28, len(control), len(code))
    return header + code + control


class EmbeddedShaderPackagesTests(unittest.TestCase):
    def test_appends_four_byte_aligned_shader_and_preserves_update_on_repeat(self):
        scratch = REPO / '.webui-data/tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory)
            profile, packages = root / '0100000000000000', root / 'packages'
            profile.mkdir()
            packages.mkdir()
            (profile / 'game.tsv').write_text('title_id\t0100000000000000\nshader_groups\t/fixture/=fixture\nshader_note\tFixture\n')
            vertex = shader(1)
            pixel = shader(5, 1)
            added = shader(5, 0x100)
            original_package = record(vertex[1], vertex[2]) + record(pixel[1], pixel[2])
            (packages / 'existing.bin').write_bytes(original_package)
            old_rows = ''.join(f'existing.bin\t{i}\t{stage}\t{item[0]}\t/fixture#RAW@{i}\n'
                               for i, (stage, item) in enumerate([('vertex', vertex), ('pixel', pixel)]))
            (profile / 'shader_map.tsv').write_text('package\tindex\tstage\tdm_ctl_sha16\tsource\n' + old_rows)
            (profile / 'shader_facts.tsv').write_text('# no compute shaders\n')
            (profile / 'shader_pairs.tsv').write_text(vertex[0] + '\t' + pixel[0] + '\n')
            image = root / 'image.bin'
            image.write_bytes(bytes(4) + added[1] + added[2])
            command = [sys.executable, str(REPO / 'webui/tools/embedded_shader_packages.py'),
                       '--image', str(image), '--profile', str(profile), '--packages', str(packages)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            manifest = packages.parent / 'embedded-additions.json'
            before = manifest.read_bytes()
            update = json.loads(before)
            self.assertEqual(update['added'], [added[0]])
            self.assertIn(vertex[0], update['affected_vertex_keys'])
            self.assertIn(old_rows, (profile / 'shader_map.tsv').read_text())
            self.assertEqual((packages / 'existing.bin').read_bytes(), original_package)
            subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertEqual(manifest.read_bytes(), before)
