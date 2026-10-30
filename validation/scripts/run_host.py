"""Build unmodified upstream tests and a reproducible host test corpus."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

if not __debug__:
    raise RuntimeError('Do not use python -O: validation assertions must remain enabled')

ROOT = Path(__file__).resolve().parents[2]
VAL = ROOT / 'validation'
UP = VAL / 'upstream/mlkem-native'
# Optional local output directories keep reruns separate from archived evidence.
# Relative overrides are resolved from the repository root, not the caller's cwd.
BUILD = (ROOT / os.environ.get('MLKEM_BUILD_DIR', 'validation/build')).resolve()
EVIDENCE = (ROOT / os.environ.get('MLKEM_EVIDENCE_DIR', 'validation/evidence')).resolve()
PIN = '08e1f3881ec140f79c2d1c14e482a32a782c5312'


def run(args, name, cwd=ROOT):
    args = list(map(str, args))
    with (EVIDENCE / 'commands.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps({'cwd': str(cwd), 'argv': args}) + '\n')
    result = subprocess.run(args, cwd=cwd, capture_output=True)
    (EVIDENCE / name).write_bytes(result.stdout + result.stderr)
    if result.returncode:
        print((result.stdout + result.stderr).decode(errors='replace')[-6000:])
        raise RuntimeError(f'{args[0]} exited {result.returncode}; see {name}')
    return result.stdout


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    assert run(['git', '-C', UP, 'rev-parse', 'HEAD'], 'upstream-pin.txt').decode().strip() == PIN
    assert not run(['git', '-C', UP, 'status', '--porcelain', '--untracked-files=no'], 'upstream-status.txt').strip()
    run(['gcc', '--version'], 'host-toolchain.txt')
    base = ['gcc', '-O2', '-std=c99', '-Wall', '-Wextra', '-Werror',
            '-DMLK_CONFIG_NAMESPACE_PREFIX=mlkem', '-I' + str(UP / 'mlkem')]
    lib = UP / 'mlkem/mlkem_native.c'
    rng = UP / 'test/notrandombytes/notrandombytes.c'
    for level in (512, 768, 1024):
        flags = base + [f'-DMLK_CONFIG_PARAMETER_SET={level}']
        binary = BUILD / f'upstream-functional-{level}.exe'
        run(flags + [lib, rng, UP / 'test/src/test_mlkem.c', '-o', binary], f'build-functional-{level}.txt')
        run([binary], f'functional-{level}.txt')
        acvp = UP / f'test/build/mlkem{level}/bin/acvp_mlkem{level}.exe'
        acvp.parent.mkdir(parents=True, exist_ok=True)
        run(flags + [lib, rng, UP / 'test/acvp/acvp_mlkem.c', '-o', acvp], f'build-acvp-{level}.txt')
        print(f'PASS: upstream functional suite ML-KEM-{level}', flush=True)
    # Persist public TEST-ONLY randomness. Never use these published coins for keys.
    corpus = EVIDENCE / 'test-coins.bin'
    if not corpus.exists():
        recorded = VAL / 'evidence/test-coins.bin'
        corpus.write_bytes(recorded.read_bytes() if recorded.exists() else os.urandom(100 * 96))
    data = corpus.read_bytes()
    assert len(data) == 9600
    header = '#define SAMPLE_COUNT 100\nstatic const unsigned char test_coins[100][96] = {\n'
    header += ',\n'.join('{' + ','.join(map(str, data[i:i+96])) + '}' for i in range(0, len(data), 96))
    (BUILD / 'test_coins.h').write_text(header + '\n};\n')
    binary = BUILD / 'host-corpus-768.exe'
    run(base + ['-DMLK_CONFIG_PARAMETER_SET=768', '-DMLK_CONFIG_NO_RANDOMIZED_API',
                '-DHOST_VERIFY', '-I' + str(BUILD), lib, VAL / 'src/validation.c', '-o', binary], 'build-host-corpus.txt')
    raw = run([binary], 'host-corpus.jsonl')
    records = [json.loads(line) for line in raw.splitlines()]
    assert len(records) == 100
    expected = []
    for i, record in enumerate(records):
        assert record['sample'] == i
        rejected = bytes.fromhex(record['rejected'])
        ct = bytes.fromhex(record['mutated_ct'])
        z = data[i*96+32:i*96+64]
        assert rejected == hashlib.shake_256(z + ct).digest(32), f'Implicit rejection mismatch {i}'
        expected.append(bytes.fromhex(record['shared']) + rejected)
    header = 'static const unsigned char expected_secrets[100][64] = {\n'
    header += ',\n'.join('{' + ','.join(map(str, row)) + '}' for row in expected)
    (BUILD / 'expected_secrets.h').write_text(header + '\n};\n')
    summary = {'status': 'PASS', 'parameter_set': 768, 'independent_test_inputs': 100,
               'roundtrips': 100, 'implicit_rejection_shake256_checks': 100,
               'invalid_public_key_checks': 100, 'invalid_secret_key_checks': 100,
               'coins_sha256': hashlib.sha256(data).hexdigest(), 'upstream': PIN}
    (EVIDENCE / 'host-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('PASS: 100 host roundtrips, key errors, repeated rejection, and independent hashlib SHAKE256 rejection checks')


if __name__ == '__main__':
    main()
