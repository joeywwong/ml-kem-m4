# Third-party attribution

The root [MIT license](LICENSE) covers this project's original harness,
scripts and documentation. It does not replace third-party licenses.

- mlkem-native is fetched at commit
  `08e1f3881ec140f79c2d1c14e482a32a782c5312`. Its `mlkem/` and `dev/` code
  offers Apache-2.0 OR ISC OR MIT and acknowledges the public-domain Kyber
  reference implementation. Auxiliary and test files carry their own SPDX
  terms; upstream documentation uses CC-BY-4.0. Retain the applicable
  [upstream license and notices](https://github.com/pq-code-package/mlkem-native/blob/08e1f3881ec140f79c2d1c14e482a32a782c5312/LICENSE)
  when redistributing its source or compiled firmware.
- pqm4 was inspected for context and was not compiled into the measured
  firmware. Its components retain their respective licenses.
- NIST ACVP vectors are fetched from the official pinned source and checked
  against the hashes in [provenance.json](validation/provenance.json).
  They are not covered by this project's MIT license.

Fetched dependencies and generated firmware are excluded from this source
repository. Consult the fetched files' notices before distributing them.
