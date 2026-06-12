# Bundled uv binaries

This directory contains platform-specific `uv` binaries that are bundled with AIASys Desktop.
They are copied into the packaged runtime by `prepare-runtime.cjs` and used by the backend
so that workspace Python environments can be created without network access.

## Platforms

| Directory | Target platform | Binary |
|-----------|----------------|--------|
| darwin-arm64 | macOS Apple Silicon | uv |
| darwin-x64 | macOS Intel | uv |
| linux-arm64 | Linux ARM64 | uv |
| linux-x64 | Linux x64 | uv |
| windows-x64 | Windows x64 | uv.exe |

## How to add/update

Download the official release from https://github.com/astral-sh/uv/releases and place the
`uv` (or `uv.exe`) binary in the matching directory. The version should match the one used
in CI/lock files when possible.
