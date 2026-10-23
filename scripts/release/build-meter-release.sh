#!/usr/bin/env bash
# The RatelMeter agent release for core-up: build-release.sh meter, kept under its old name.
#
#   scripts/release/build-meter-release.sh [commit] [output-folder]
exec "$(dirname "$0")/build-release.sh" meter "$@"
