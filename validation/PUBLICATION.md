# Publication preparation — 2026-10-30

The working tree contains labeled public copies. The original harness,
scripts and documentation are licensed under [MIT](../LICENSE), as selected
by the owner. [Third-party terms](../THIRD_PARTY_NOTICES.md) remain intact.

## Changes to evidence

- Local usernames, workspace and installation prefixes use consistent
  placeholders; ST-Link serial values use `<probe-1>`.
- Each historical hardware RAM record has only offsets 56–63 zeroed. All
  other binary bytes are preserved. The 900 cycle values, status/clock/stack
  fields, decoded JSON, medians/ranges and historical firmware hashes remain
  unchanged.
- [The manifest](evidence/redaction-manifest.json) labels every original
  evidence file, records original and public hashes, and describes each
  transformation. [The evidence notice](evidence/README.md) identifies the
  records as public copies. Evidence line endings are preserved by
  [`.gitattributes`](../.gitattributes).
- `src/validation.c` now explicitly zeroes both reserved words before
  publishing the report header. This changes future firmware, not the
  historical measurement record. No board flashing, reset or hardware run
  was performed during publication preparation.

## Private originals

Before editing, 109 tracked files were copied byte-for-byte to
`validation/backups/publication-originals-20261030/files/` with a SHA-256
inventory. `original-history.bundle` in the same directory retains the
original local Git history. This entire directory is ignored and excluded
from the export. Keep a separate private backup; Git ignore rules do not
encrypt files or prevent forced addition.

## Verification and public export

From the repository root:

```powershell
python validation/scripts/publication.py verify --originals validation/backups/publication-originals-20261030
python validation/scripts/publication.py export
```

Verification checks every historical evidence file against its public hash,
the three binary masks, all 900 cycles against JSON and summaries, register
and stack values, JSON syntax, and identifying-path/probe patterns. With
`--originals`, it also verifies original evidence hashes and that each binary
differs only by its documented mask.

Export uses an explicit publication allowlist, excludes private snapshots,
dependencies and build outputs, and verifies every archived byte. Its default
output is the ignored `validation/publication-export/ml-kem-m4-public.zip`.
It refuses to overwrite an existing archive; use `--output` for a new name.
The ZIP contains source and public evidence, with **no `.git` history**.

## Checks completed during preparation

- All 109 private snapshot files still match their recorded hashes; all 93
  historical public evidence files match the redaction manifest.
- All three public RAM records differ from the originals only at offsets
  56–63. All 900 cycles, registers, stack values and summaries agree.
- Fresh upstream host functional suites passed for 512, 768 and 1024
  (1,000 iterations each). The 100-case host corpus, malformed-key checks,
  repeated rejection and independent SHAKE256 checks passed; corpus and
  summary match the historical evidence.
- The patched firmware cross-build and all five ELF validator tests passed.
  Disassembly confirms zero stores at report offsets 56 and 60 before the
  report header. The compiler required a retry outside the sandbox after
  Windows error 623. No hardware was accessed.
- Negative export checks rejected reserved-byte changes, re-hashed cycle
  tampering and re-hashed probe identifiers; a private-backup sentinel was
  excluded. Archive entries and bytes are checked against the allowlist.

Fresh outputs remain under ignored `validation/build/publication-check/`.
The earlier 435-case ACVP result is historical and was not rerun for these
publication-only changes.

## Existing Git history

Earlier commits in this checkout still contain original paths, raw reserved
bytes and author email metadata. Committing these edits alone will not remove
that material. A Git bundle of the original history is deliberately private.
The existing repository and any earlier remote copies must not be treated as
sanitized by this working-tree change.

For a clean public repository, extract the verified ZIP into a new directory
and initialize fresh Git history there. Choose the desired public author
name/email before the first commit. No existing branch/history or remote
visibility has been changed, and nothing has been committed or pushed by this
publication work. If earlier copies were already shared, this export cannot
remove those copies.
