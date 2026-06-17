# Third-Party Licenses

This directory contains license texts and attribution notices for third-party
software that AIASYS either bundles or refers users to download. AIASYS itself
is licensed under the Apache License 2.0 (see `LICENSE` in the project root).

## Bundled components

These components are shipped inside the AIASYS desktop installer/package.
They run as separate external processes or runtime-loaded extensions; they are
not statically linked into AIASYS source code.

| Component   | Project URL                              | License(s)                | Notice file                   |
|-------------|------------------------------------------|---------------------------|-------------------------------|
| fnm         | https://github.com/Schniz/fnm            | GPL-3.0                   | `fnm-GPL-3.0.txt`             |
| uv          | https://github.com/astral-sh/uv          | Apache-2.0 OR MIT         | `uv-Apache-2.0-MIT.txt`       |
| sqlite-vec  | https://github.com/asg017/sqlite-vec     | MIT OR Apache-2.0         | `sqlite-vec-MIT-Apache-2.0.txt` |

## Optional / user-installed components

These components are **not** bundled with AIASYS. They are offered to users
through the in-app "Environment Enhancements" panel and are downloaded or
installed by the user. Full license texts are included here for compliance and
transparency.

| Component          | Project URL                       | License   | Notice file                        |
|--------------------|-----------------------------------|-----------|------------------------------------|
| Git for Windows    | https://gitforwindows.org/        | GPL-2.0   | `git-for-windows-GPL-2.0.txt`      |
| busybox-w32        | https://frippery.org/busybox/     | GPL-2.0   | `busybox-w32-GPL-2.0.txt`          |

## Full license texts

- `GPL-3.0.txt` — GNU General Public License v3.0
- `GPL-2.0.txt` — GNU General Public License v2.0
- `Apache-2.0.txt` — Apache License 2.0
- `MIT.txt` — MIT License

## Source availability

Source code for each bundled or referenced component can be obtained from the
project URL listed above. If you need a physical copy of source code for a
bundled GPL component, please contact the AIASYS maintainers.
