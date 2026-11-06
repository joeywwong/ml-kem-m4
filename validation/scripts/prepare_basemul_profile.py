"""Prepare matched, isolated ML-KEM basemul profiling images; never access USB.

Uses public historical test coins, but executes fresh host checks. Generated
derivatives retain upstream notices and never modify the pinned checkout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from run_host import ROOT, VAL, UP, PIN
from build_board import validate_elf

SAMPLES = 100
RECORD_WORDS = 6
OVERHEAD_SAMPLES = 64
REPORT_WORDS = 32 + SAMPLES * RECORD_WORDS + OVERHEAD_SAMPLES


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Source transformation anchor mismatch: ' + old[:100])
    return text.replace(old, new)


def profile_harness():
    text = (VAL / 'src/validation.c').read_text()
    text = replace_once(text, '#include "test_coins.h"',
                        '#include "test_coins.h"\n#include "profile_api.h"')
    start = text.index('struct report {')
    end = text.index('\n};', start) + len('\n};')
    text = text[:start] + '''struct report {
    uint32_t magic, version, status, completed, failure, level, samples, stack_bytes;
    uint32_t rcc_cr, rcc_cfgr, flash_acr, cpuid, dwt_ctrl, clock_hz, mode, primask;
    uint32_t record_words, overhead_samples, expected_total_calls, total_calls;
    uint32_t reserved[12];
    uint32_t cycles[SAMPLE_COUNT][6];
    uint32_t empty_bracket[64];
};''' + text[end:]
    text = replace_once(text, 'uint32_t cycles[3])', 'uint32_t cycles[6])')
    text = replace_once(text, '    uint8_t saved0, saved1;',
                        '    uint8_t saved0, saved1;\n'
                        '    lab_probe_calls = 0; lab_probe_cycles = 0;')
    text = replace_once(text, '    cycles[2] = ticks() - before;',
                        '    cycles[2] = ticks() - before;\n'
                        '    cycles[3] = lab_probe_cycles;\n'
                        '    cycles[4] = lab_probe_calls;\n'
                        '    if (cycles[4] != (LAB_INSTRUMENTED ? 1u : 0u)) return 11;')
    text = replace_once(text,
                        '    if (mlkem_dec(receiver, ct, sk) != MLK_ERR_INVALID_SK) return 9;\n    return 0;',
                        '    if (mlkem_dec(receiver, ct, sk) != MLK_ERR_INVALID_SK) return 9;\n'
                        '    cycles[5] = lab_probe_calls;\n'
                        '    if (cycles[5] != (LAB_INSTRUMENTED ? 3u : 0u)) return 12;\n'
                        '    return 0;')
    text = replace_once(text, '    uint32_t cycles[3];', '    uint32_t cycles[6];\n    unsigned j;')
    text = replace_once(text,
                        '    results.reserved[0] = 0;\n    results.reserved[1] = 0;',
                        '    for (i = 0; i < sizeof(results) / 4; ++i)\n'
                        '        ((volatile uint32_t *)&results)[i] = 0;')
    text = replace_once(text, 'results.magic = 0x4D4C4B45;', 'results.magic = 0x4D4C4250;')
    text = replace_once(text, 'results.version = 1;', 'results.version = 2;')
    text = replace_once(text, '    results.dwt_ctrl = REG32(0xE0001000); results.clock_hz = 16000000;',
                        '    results.dwt_ctrl = REG32(0xE0001000); results.clock_hz = 16000000;\n'
                        '    results.mode = LAB_INSTRUMENTED;\n'
                        '    __asm__ volatile ("mrs %0, primask" : "=r" (j));\n'
                        '    results.primask = j;\n'
                        '    results.record_words = 6; results.overhead_samples = 64;\n'
                        '    results.expected_total_calls = LAB_INSTRUMENTED ? 300 : 0;')
    text = replace_once(text, '#endif\n    for (i = 0; i < SAMPLE_COUNT; ++i) {',
                        '    for (i = 0; i < 64; ++i) results.empty_bracket[i] = lab_profile_empty();\n'
                        '    lab_probe_calls = 0; lab_probe_total_calls = 0; lab_probe_cycles = 0;\n'
                        '#endif\n    for (i = 0; i < SAMPLE_COUNT; ++i) {')
    text = replace_once(text, '        cycles[0] = cycles[1] = cycles[2] = 0;',
                        '        for (j = 0; j < 6; ++j) cycles[j] = 0;')
    text = replace_once(text,
                        '        results.cycles[i][0] = cycles[0]; results.cycles[i][1] = cycles[1];\n'
                        '        results.cycles[i][2] = cycles[2];',
                        '        for (j = 0; j < 6; ++j) results.cycles[i][j] = cycles[j];\n'
                        '        results.total_calls = lab_probe_total_calls;')
    return text


PRELUDE = '''/* LAB DERIVATIVE: DWT profiling, not GPIO or analog acquisition.
 * This prelude and the marked call-site transformation are lab additions.
 */
#include <stdint.h>
#include "profile_api.h"
volatile unsigned lab_probe_before, lab_probe_cycles, lab_probe_calls, lab_probe_total_calls;
static inline uint32_t lab_profile_ticks(void) {
#ifdef HOST_VERIFY
    return 0;
#else
    __asm__ volatile ("dsb\\nisb" ::: "memory");
    return *(volatile uint32_t *)0xE0001004;
#endif
}
static inline void lab_probe_begin(void) { lab_probe_before = lab_profile_ticks(); }
static inline void lab_probe_end(void) {
    uint32_t end = lab_profile_ticks();
    lab_probe_cycles = end - lab_probe_before;
    ++lab_probe_calls;
    ++lab_probe_total_calls;
}
uint32_t lab_profile_empty(void) {
    lab_probe_begin();
    __asm__ volatile ("" ::: "memory");
    lab_probe_end();
    return lab_probe_cycles;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--arm', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    commands = []

    def run(argv, name, cwd=ROOT):
        argv = list(map(str, argv))
        commands.append({'argv': argv, 'cwd': str(cwd), 'log': name})
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=300)
        (out / name).write_bytes(proc.stdout + proc.stderr)
        if proc.returncode:
            raise RuntimeError(f'{name} exited {proc.returncode}: ' +
                               (proc.stdout + proc.stderr).decode(errors='replace')[-3000:])
        return proc.stdout

    try:
        if run(['git', '-C', UP, 'rev-parse', 'HEAD'], 'pin.txt').decode().strip() != PIN:
            raise RuntimeError('Wrong upstream commit')
        if run(['git', '-C', UP, 'status', '--porcelain', '--untracked-files=no'], 'upstream-status.txt').strip():
            raise RuntimeError('Modified upstream checkout')
        run(['gcc', '--version'], 'host-toolchain.txt')
        arm = args.arm or next(Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins').glob('*/tools/bin/arm-none-eabi-gcc.exe'))
        arm = arm.resolve()
        run([arm, '--version'], 'arm-toolchain.txt')
        coins = (VAL / 'evidence/test-coins.bin').read_bytes()
        records = [json.loads(line) for line in (VAL / 'evidence/host-corpus.jsonl').read_bytes().splitlines()]
        if len(coins) != 9600 or len(records) != SAMPLES:
            raise RuntimeError('Wrong historical corpus dimensions')
        expected = []
        for i, row in enumerate(records):
            rejection = hashlib.shake_256(coins[i*96+32:i*96+64] + bytes.fromhex(row['mutated_ct'])).digest(32)
            if row['sample'] != i or rejection.hex() != row['rejected']:
                raise RuntimeError('Independent SHAKE256 rejection check failed')
            expected.append(bytes.fromhex(row['shared']) + rejection)
        headers = out / 'headers'
        headers.mkdir()
        def header(name, rows, declaration):
            body = ',\n'.join('{' + ','.join(map(str, row)) + '}' for row in rows)
            (headers / name).write_text(declaration + '{\n' + body + '\n};\n')
        header('test_coins.h', [coins[i:i+96] for i in range(0, 9600, 96)],
               '#define SAMPLE_COUNT 100\nstatic const unsigned char test_coins[100][96] = ')
        header('expected_secrets.h', expected, 'static const unsigned char expected_secrets[100][64] = ')
        (headers / 'profile_api.h').write_text(
            '#include <stdint.h>\nextern volatile unsigned lab_probe_before, lab_probe_cycles, lab_probe_calls, lab_probe_total_calls;\n'
            'uint32_t lab_profile_empty(void);\n')
        original = UP / 'mlkem/src/indcpa.c'
        call = '  mlk_polyvec_basemul_acc_montgomery_cached(sb, skpv, b, b_cache);'
        if original.read_text().count(call) != 1:
            raise RuntimeError('Decapsulation call-site anchor mismatch')
        lock = json.loads((VAL / 'provenance.json').read_text())['acvp']
        vectors = VAL / 'upstream/acvp'
        for relative, digest in lock['sha256'].items():
            if sha(vectors / relative) != digest:
                raise RuntimeError('ACVP vector hash mismatch: ' + relative)
        summary = {'status': 'PREPARING', 'upstream': PIN, 'samples': SAMPLES,
                   'report_version': 2, 'report_words': REPORT_WORDS, 'report_bytes': REPORT_WORDS * 4,
                   'record_columns': ['keygen_cycles', 'encaps_cycles', 'decaps_cycles',
                                      'basemul_cycles', 'valid_probe_calls', 'all_probe_calls'],
                   'coins_sha256': hashlib.sha256(coins).hexdigest(),
                   'original_indcpa_sha256': sha(original), 'modes': {},
                   'configuration': 'existing VG linker configuration; additional 512 KiB ELF bounds check; 128 KiB main SRAM; no CCM',
                   'measurement': 'raw DWT counts; basemul region excludes public NTT/cache and inverse NTT; valid call captured before rejection tests',
                   'limitations': ['No GPIO/analog capture', 'Nominal 16 MHz, not externally measured',
                                   'Instrumented whole-decapsulation includes profiling overhead',
                                   'Matched build comparison can also reflect code-layout changes',
                                   'Three reset repetitions of 100 inputs, not 300 independent inputs']}
        for mode, enabled in [('baseline', 0), ('instrumented', 1)]:
            directory = out / mode
            directory.mkdir()
            derived = PRELUDE + replace_once(original.read_text(), call,
                '  lab_probe_begin();\n' + call + '\n  lab_probe_end();' if enabled else call)
            (directory / 'indcpa-profile.c').write_text(derived)
            unit = directory / 'mlkem-profile.c'
            unit.write_text(replace_once((UP / 'mlkem/mlkem_native.c').read_text(),
                '#include "src/indcpa.c"', '#include "indcpa-profile.c"'))
            harness = directory / 'validation-profile.c'
            harness.write_text(profile_harness())
            wrapper = directory / 'host-profile.c'
            wrapper.write_text('#define main validation_main\n#include "validation-profile.c"\n#undef main\n'
                'int main(void) { int rc = validation_main(); if (rc) return rc;\n'
                'return lab_probe_total_calls == (LAB_INSTRUMENTED ? 300u : 0u) ? 0 : 99; }\n')
            common = ['-O2', '-std=c99', '-Wall', '-Wextra', '-Werror',
                      '-DMLK_CONFIG_NAMESPACE_PREFIX=mlkem', f'-DLAB_INSTRUMENTED={enabled}',
                      '-I' + str(UP / 'mlkem'), '-I' + str(UP / 'mlkem/src'), '-I' + str(headers)]
            binary = directory / 'host-corpus.exe'
            run(['gcc', *common, '-DMLK_CONFIG_PARAMETER_SET=768', '-DMLK_CONFIG_NO_RANDOMIZED_API',
                 '-DHOST_VERIFY', unit, wrapper, '-o', binary], mode + '-host-build.txt')
            corpus = run([binary], mode + '-host-corpus.jsonl')
            if [json.loads(line) for line in corpus.splitlines()] != records:
                raise RuntimeError('Fresh host corpus differs from archived expected outputs')
            for level in (512, 768, 1024):
                executable = directory / f'test/build/mlkem{level}/bin/acvp_mlkem{level}.exe'
                executable.parent.mkdir(parents=True)
                run(['gcc', *common, f'-DMLK_CONFIG_PARAMETER_SET={level}', '-DHOST_VERIFY', unit,
                     UP / 'test/notrandombytes/notrandombytes.c', UP / 'test/acvp/acvp_mlkem.c', '-o', executable],
                    f'{mode}-acvp-build-{level}.txt')
            cases = 0
            for group in ('ML-KEM-keyGen-FIPS203', 'ML-KEM-encapDecap-FIPS203', 'ML-KEM-encapDecap-FIPS203-tr1'):
                log = f'{mode}-{group}.txt'
                run([sys.executable, UP / 'test/acvp/acvp_client.py', '--prompt', vectors / group / 'prompt.json',
                     '--expected', vectors / group / 'expectedResults.json', '--jobs', '4'], log, cwd=directory)
                if 'ALL GOOD!' not in (out / log).read_text():
                    raise RuntimeError('Missing ACVP success marker')
                cases += sum(len(g['tests']) for g in json.loads((vectors / group / 'prompt.json').read_text())['testGroups'])
            flags = ['-mcpu=cortex-m4', '-mthumb', '-mfloat-abi=soft', '-ffunction-sections',
                     '-fdata-sections', '-fstack-usage']
            objects = []
            for source in (unit, harness, VAL / 'src/startup.S'):
                obj = directory / (source.stem + '.o')
                run([arm, *common, *flags, '-DMLK_CONFIG_PARAMETER_SET=768', '-DMLK_CONFIG_NO_RANDOMIZED_API',
                     '-c', source, '-o', obj], f'{mode}-compile-{source.stem}.txt')
                objects.append(obj)
            linker = directory / 'profile.ld'
            linker.write_text(replace_once((VAL / 'src/stm32f407vg.ld').read_text(),
                'SIZEOF(.results) == 1264', f'SIZEOF(.results) == {REPORT_WORDS * 4}'))
            elf = directory / 'profile.elf'
            run([arm, *flags, '-nostartfiles', '-T', linker, '-Wl,--gc-sections',
                 '-Wl,-Map=' + str(directory / 'profile.map'), *objects, '-lc', '-lgcc', '-o', elf], mode + '-link.txt')
            bounds = validate_elf(elf, 512)
            for tool, options, name in [('size', ['-A'], 'size.txt'), ('objdump', ['-d'], 'disassembly.txt'),
                                        ('nm', ['-n'], 'symbols.txt')]:
                output = run([arm.with_name('arm-none-eabi-' + tool + '.exe'), *options, elf], mode + '-' + name)
                (directory / name).write_bytes(output)
            firmware = directory / 'profile.bin'
            run([arm.with_name('arm-none-eabi-objcopy.exe'), '-O', 'binary', elf, firmware], mode + '-objcopy.txt')
            summary['modes'][mode] = {'host_corpus': 'PASS', 'host_cases': 100,
                'independent_shake256_checks': 100, 'expected_host_hook_calls': 300 if enabled else 0,
                'acvp': 'PASS', 'acvp_cases': cases, 'elf': bounds,
                'firmware_bytes': firmware.stat().st_size, 'firmware_sha256': sha(firmware),
                'derived_indcpa_sha256': sha(directory / 'indcpa-profile.c'),
                'harness_sha256': sha(harness)}
            print(f'PASS: {mode}: 100 host cases, {cases} ACVP cases, ARM ELF/bounds; {firmware.stat().st_size} flash bytes', flush=True)
        summary['status'] = 'PASS HOST AND BUILD; DEVICE NOT RUN'
        (out / 'build-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    finally:
        (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')


if __name__ == '__main__':
    main()
