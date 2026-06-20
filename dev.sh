#!/usr/bin/env bash
# dev.sh -- AIASys 开发入口脚本
# 实际逻辑在 scripts/dev/cli.sh，这里只是入口转发。

exec "$(dirname "$0")/scripts/dev/cli.sh" "$@"