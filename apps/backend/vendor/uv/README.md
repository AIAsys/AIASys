# Bundled uv binaries

This directory holds platform-specific `uv` binaries that are bundled into the
desktop package runtime.

## Directory layout

```
vendor/uv/
  darwin-arm64/uv       → macOS Apple Silicon
  darwin-x64/uv         → macOS Intel
  linux-arm64/uv        → Linux ARM64
  linux-x64/uv          → Linux x64
  windows-x64/uv.exe    → Windows x64
```

## How binaries are populated

Binaries are **not** committed to the repository.
During packaging, `apps/desktop/scripts/download-uv-binary.cjs` detects the
current platform and downloads the matching release from
<https://github.com/astral-sh/uv/releases>, placing the binary in the correct
subdirectory.

```bash
# Manual download (any platform)
node apps/desktop/scripts/download-uv-binary.cjs

# Specify a platform explicitly
node apps/desktop/scripts/download-uv-binary.cjs linux-x64
```

`prepare-runtime.cjs` invokes this script automatically before copying
`vendor/` into the staging directory.

## Version

Bundled uv version is pinned in `download-uv-binary.cjs` (currently **0.11.3**).
