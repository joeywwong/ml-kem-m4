"""Cross-compile only; independently check every ELF PT_LOAD range. No flashing."""
import hashlib
import json
from pathlib import Path
import struct
import sys
from run_host import ROOT, VAL, UP, BUILD, EVIDENCE, run, PIN

if not __debug__:
    raise RuntimeError('Do not use python -O: safety assertions must remain enabled')


def validate_elf(path, flash_kib):
    blob = path.read_bytes()
    assert blob[:6] == b'\x7fELF\x01\x01', 'Expected ELF32 little endian'
    h = struct.unpack_from('<HHIIIIIHHHHHH', blob, 16)
    assert h[1] == 40, 'Expected ARM ELF'
    entry, phoff, phsize, phcount = h[3], h[4], h[8], h[9]
    regions = [(0x08000000, 0x08000000 + flash_kib * 1024), (0x20000000, 0x20020000)]
    def contained(start, size, allowed):
        return any(lo <= start and start + size <= hi for lo, hi in allowed)
    assert contained(entry & ~1, 2, regions[:1])
    segments = []
    for i in range(phcount):
        kind, offset, va, pa, filesz, memsz, flags, align = struct.unpack_from('<8I', blob, phoff + i * phsize)
        if kind != 1:
            continue
        assert filesz <= memsz and offset + filesz <= len(blob)
        assert contained(va, memsz, regions), f'VMA out of range: {va:#x}+{memsz}'
        if filesz:
            assert contained(pa, filesz, regions[:1]), f'Flash LMA out of range: {pa:#x}+{filesz}'
        segments.append(dict(vaddr=hex(va), paddr=hex(pa), file_bytes=filesz, memory_bytes=memsz))
    assert segments
    return {'status': 'PASS', 'flash_limit_kib': flash_kib, 'ram_limit_kib': 128,
            'entry': hex(entry), 'segments': segments, 'elf_sha256': hashlib.sha256(blob).hexdigest()}


def main():
    arm = Path(sys.argv[1]) if len(sys.argv) > 1 else next(Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins').glob('*/tools/bin/arm-none-eabi-gcc.exe'))
    assert run(['git', '-C', UP, 'rev-parse', 'HEAD'], 'board-upstream-pin.txt').decode().strip() == PIN
    assert not run(['git', '-C', UP, 'status', '--porcelain', '--untracked-files=no'], 'board-upstream-status.txt').strip()
    run([arm, '--version'], 'arm-toolchain.txt')
    elf = BUILD / 'mlkem768-stm32f407vg.elf'
    flags = ['-mcpu=cortex-m4', '-mthumb', '-mfloat-abi=soft', '-O2', '-g3', '-std=c99',
             '-Wall', '-Wextra', '-Werror', '-ffunction-sections', '-fdata-sections', '-fstack-usage',
             '-DMLK_CONFIG_PARAMETER_SET=768', '-DMLK_CONFIG_NAMESPACE_PREFIX=mlkem',
             '-DMLK_CONFIG_NO_RANDOMIZED_API', '-I' + str(UP / 'mlkem'), '-I' + str(BUILD)]
    objects = []
    for source in (UP / 'mlkem/mlkem_native.c', VAL / 'src/validation.c', VAL / 'src/startup.S'):
        obj = BUILD / (source.stem + '.o')
        run([arm] + flags + ['-c', source, '-o', obj], f'board-compile-{source.stem}.txt')
        objects.append(obj)
    run([arm, '-mcpu=cortex-m4', '-mthumb', '-mfloat-abi=soft', '-nostartfiles',
         '-T', VAL / 'src/stm32f407vg.ld', '-Wl,--gc-sections',
         '-Wl,-Map=' + str(BUILD / 'firmware.map')] + objects + ['-lc', '-lgcc', '-o', elf], 'board-link.txt')
    result = validate_elf(elf, 1024)
    (EVIDENCE / 'elf-validation.json').write_text(json.dumps(result, indent=2) + '\n')
    for name, args in [('size', ['-A']), ('readelf', ['-lW']), ('objdump', ['-h'])]:
        run([arm.with_name(f'arm-none-eabi-{name}.exe')] + args + [elf], f'firmware-{name}.txt')
    run([arm.with_name('arm-none-eabi-objcopy.exe'), '-O', 'binary', elf, BUILD / 'firmware.bin'], 'board-objcopy.txt')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
