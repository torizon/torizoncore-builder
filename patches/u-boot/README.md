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

## `0002-lib-rsa-allow-matching-pkcs11-path-by-object-id.patch`

Lets mkimage identify a key on a PKCS#11 token by `id=` in addition to `object=`. Without it, a
URI passed with `-k` that does not contain `object=` gets `;object=<key name>` appended, so the
token is asked for an object labelled after the key name, which it does not have.

Matching by label is not enough on a YubiKey: for a key imported into a PIV slot, ykcs11 labels the
private and public objects differently ("Private key for ...", "Public key for ...") while giving
them the same id. Signing the kernel only needs the private key, but adding the public key to the
U-Boot DTB needs the public one, so no single `object=` value serves both.

- Authoritative copy: upstream U-Boot, commit `0707f73a8ba2` ("lib/rsa: allow matching pkcs11 path
  by object id"); this file is its `git format-patch` output, unmodified.
- `meta-toradex-security` carries the same change as
  `recipes-bsp/u-boot/files/0001-lib-rsa-allow-matching-pkcs11-path-by-object-id.patch`, applied
  to u-boot-tools when `TDX_SIGNED_HSM` is set. That copy is rebased onto an older `rsa-sign.c`
  and does not apply to `v2024.07`, which is why this one is taken from upstream instead.
- Upstream status: merged, first released in `v2025.10`. When the Dockerfile clones that tag or a
  later one, drop the file and this section.
- Applies cleanly to `v2024.07`, the tag the Dockerfile clones.
