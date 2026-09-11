# U-Boot patches applied to the tools built into the container

These are applied to the U-Boot checkout in the `uboot-builder` stage of
`torizoncore-builder.Dockerfile`, right after the clone, so that the binman built into the image
behaves like the one that produced the images this tool re-signs.

## `0001-binman-openssl-Make-generated-certificates-reproduci.patch`

Makes binman's X.509 certificates deterministic: the serial number is derived from the data being
signed, and the validity period runs from `SOURCE_DATE_EPOCH` to a fixed end date, instead of
OpenSSL inventing a random serial and a 30-day window on every run.

Without it, re-signing a TI K3 bootloader produces different bytes every time, and comparing a
re-signed artifact against the original tells you nothing.

- Authoritative copy: `meta-toradex-security`, `recipes-bsp/u-boot/files/`, branch
  `k3-reproducible-builds`, applied there by `recipes-bsp/u-boot/u-boot-k3-secboot-reproducible.inc`
  when `TDX_K3_SECBOOT_REPRODUCIBLE` is set.
- This copy is byte-identical to that one, so `diff` says whether they have diverged. Keep it that
  way: provenance belongs in this file, not in the patch.
- Upstream status: submitted, not yet merged. When it lands in a U-Boot release the container builds
  from, drop the file and this section.
- Applies cleanly to `v2024.07`, the tag the Dockerfile clones. The `ftest.py` hunk is not needed
  here and is kept only so the two copies stay comparable.

The validity pinning needs OpenSSL 3.4 or later; below that, binman warns and falls back to
wall-clock dates. Debian trixie ships 3.5.7, so the image is fine, but that is why `openssl` is a
declared runtime dependency rather than something inherited from another package.
