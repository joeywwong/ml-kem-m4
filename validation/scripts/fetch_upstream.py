"""Fetch immutable source pins and hash-checked official vectors; no installs."""
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
from run_host import ROOT, VAL, EVIDENCE, run


def main():
    EVIDENCE.mkdir(exist_ok=True)
    lock = json.loads((VAL / 'provenance.json').read_text())
    # These exclusions are local to the checkout, never a versioned .gitignore.
    git_dir = subprocess.check_output(['git', 'rev-parse', '--git-dir'], cwd=ROOT, text=True).strip()
    exclude = ROOT / git_dir / 'info/exclude'
    old = exclude.read_text() if exclude.exists() else ''
    additions = ['/validation/upstream/', '/validation/build/', '/validation/backups/',
                 '/validation/scripts/__pycache__/']
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open('a') as f:
        for line in additions:
            if line not in old.splitlines():
                f.write('\n' + line + '\n')
    for name in ('mlkem-native', 'pqm4'):
        repo = VAL / 'upstream' / name
        pin = lock[name]
        if not repo.exists():
            repo.mkdir(parents=True)
            run(['git', 'init', repo], f'fetch-{name}-init.txt')
            run(['git', '-C', repo, 'remote', 'add', 'origin', pin['url']], f'fetch-{name}-remote.txt')
            run(['git', '-C', repo, 'fetch', '--depth', '1', 'origin', pin['commit']], f'fetch-{name}.txt')
            run(['git', '-C', repo, 'checkout', '--detach', pin['commit']], f'fetch-{name}-checkout.txt')
        actual = run(['git', '-C', repo, 'rev-parse', 'HEAD'], f'fetch-{name}-pin.txt').decode().strip()
        if actual != pin['commit']:
            raise RuntimeError(f'{repo} is at {actual}; expected {pin["commit"]}. Refusing to reset existing checkout.')
        if run(['git', '-C', repo, 'status', '--porcelain', '--untracked-files=no'], f'fetch-{name}-status.txt').strip():
            raise RuntimeError(f'{repo} has modifications; refusing to use altered cryptography')
    for relative, expected in lock['acvp']['sha256'].items():
        dest = VAL / 'upstream/acvp' / relative
        if not dest.exists():
            url = f'https://raw.githubusercontent.com/usnistgov/ACVP-Server/{lock["acvp"]["commit"]}/gen-val/json-files/{relative}'
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError(f'Vector hash mismatch: {relative}')
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        if hashlib.sha256(dest.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f'Local vector hash mismatch: {relative}')
    print('PASS: source pins and all six NIST ACVP vector-file hashes')


if __name__ == '__main__':
    main()
