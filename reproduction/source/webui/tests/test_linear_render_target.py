"""Exercise the texture layout used by the P5R boot failure on a native CPU."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from webui import diffapply

REPO = Path(__file__).resolve().parents[2]
CLANG = Path(os.environ.get('NX_TEST_CLANG', REPO / '.webui-data/tools/ios-cross/toolchain/windows/iphone/bin/clang.exe'))


@unittest.skipUnless(CLANG.is_file() and os.name == 'nt', 'Requires the Windows native C compiler')
class LinearRenderTargetTests(unittest.TestCase):
    def test_independent_render_target_flag_and_explicit_stride(self):
        harness = r'''
#include <assert.h>
#include "nvn_tex.h"
#include "nvn_deswizzle.h"
int main(void) {
    nvn_texdesc d = {.target=1, .format=0x25, .flags=0x44,
        .width=16, .height=16, .depth=1, .levels=1, .stride=128};
    nvn_texlayout rt, both, plain;
    nvn_tex_layout(&d, &rt);
    assert(rt.size == 2048 && rt.align == 128);
    assert(nvn_tex_level_offset(&d, 1) == 0);
    assert(nvn_tex_level_gobs(&d, 0) == 0);
    uint32_t row, rows, slices, bpb; uint64_t base; unsigned th, td;
    assert(nvn_deswizzle_geom(&d, 0, 0, &row, &rows, &slices, &base, &th, &td, &bpb) == -1);
    d.flags |= 0x10;
    nvn_tex_layout(&d, &both);
    assert(both.size == rt.size && both.align == rt.align);
    d.stride = 0;
    nvn_tex_layout(&d, &both);
    assert(both.size == 2048);
    d.flags = 0x14;
    nvn_tex_layout(&d, &plain);
    assert(plain.size == 1024 && plain.align == 32);
    d.flags = 0x44; d.width = 100; d.height = 100;
    nvn_tex_layout(&d, &rt);
    assert(rt.size == 51200 && rt.align == 128);
    return 0;
}
'''
        scratch = REPO / '.webui-data/tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            sources = []
            for target, patch in [('dm/gfx/nvn/nvn_tex.c', '0010-nvn-linear-render-target-layout.patch'),
                                  ('dm/gfx/tex/nvn_deswizzle.c', '0011-nvn-linear-render-target-deswizzle.patch')]:
                path = root / Path(target).name
                path.write_bytes(diffapply.apply_file(REPO / target, (REPO / 'webui/patches' / patch).read_bytes(), target))
                sources.append(str(path))
            (root / 'check.c').write_text(harness, encoding='utf-8')
            executable = root / 'check.exe'
            command = [str(CLANG), '-I' + str(REPO / 'dm/gfx/nvn'), '-I' + str(REPO / 'dm/gfx/tex'),
                       str(root / 'check.c'), *sources, '-o', str(executable)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run([str(executable)], check=True, capture_output=True, text=True)
