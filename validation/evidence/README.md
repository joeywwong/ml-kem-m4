# Historical evidence: public copies

**This directory contains redacted public copies of historical evidence.**
Each original file is individually identified in
[redaction-manifest.json](redaction-manifest.json) with its original SHA-256,
public SHA-256, transformation and copy label. Unchanged files are identified
as unchanged. Unmodified originals and original Git history are retained
privately under the ignored `validation/backups/` directory and are excluded
from the publication export.

Redactions replace local workspace, home and installation prefixes with
`<repo>`, `<user-home>`, `<stm32-tools>`, `<python-install>`, `<msys2>` and
related placeholders. ST-Link serial values become `<probe-1>`. Arguments,
return/status text, device-family/register values and measurement values
otherwise retain their recorded contents. Placeholders in the historical
command ledger are descriptive; they are not executable filesystem paths.

In each `hardware-run-1.bin`, `hardware-run-2.bin` and `hardware-run-3.bin`,
only offsets **56–63 inclusive** were replaced with eight zero bytes. These
two reserved words were uninitialized in the historical firmware. Record
lengths, status/clock/stack fields and every cycle value remain unchanged.
The JSON run records and hardware summary are unchanged. These binaries
must not be described as unmodified raw SRAM captures.

The historical source-hash manifest and firmware hashes remain unchanged.
Current `src/validation.c` initializes the two reserved words before exposing
the report. A new build therefore has a different firmware identity; the
historical measurements do not describe that new image. No new hardware run
was performed for publication preparation.
