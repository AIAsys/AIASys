# Bundled fnm binaries

This directory holds platform-specific `fnm` binaries that are bundled into the
desktop package runtime.

## Directory layout

```
vendor/node/
  darwin-arm64/fnm    → macOS Apple Silicon
  darwin-x64/fnm      → macOS Intel
  linux-arm64/fnm     → Linux ARM64
  linux-x64/fnm       → Linux x64
  win-x64/fnm.exe     → Windows x64
```

## How binaries are populated

Binaries are **not** committed to the repository.
During packaging, `apps/desktop/scripts/download-fnm-binary.cjs` detects the
current platform and downloads the matching release from
<https://github.com/Schniz/fnm/releases>, placing the binary in the correct
subdirectory.

```bash
# Manual download (any platform)
node apps/desktop/scripts/download-fnm-binary.cjs

# Specify a platform explicitly
node apps/desktop/scripts/download-fnm-binary.cjs linux-x64
```

`prepare-runtime.cjs` invokes this script automatically before copying
`vendor/` into the staging directory.

## Version

Bundled fnm version is pinned in `download-fnm-binary.cjs` (currently **1.39.0**).
