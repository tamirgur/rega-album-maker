#!/usr/bin/env bash
set -eu
# the same synthetic party photos as english-party-qr, without a second copy in the repo
cp -R "$(dirname "$0")/../english-party-qr/files/." .
