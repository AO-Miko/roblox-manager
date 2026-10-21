#!/usr/bin/env bash
# Makes tests/fixtures: a signed sample file made with a throw-away key (the private key is deleted at once), so that the Windows tests
# can check signatures without ssh-keygen. Run once: tests/make_fixture.sh
set -euo pipefail
cd "$(dirname "$0")/fixtures"
rm -f key key.pub sample.bin sample.bin.sig allowed_signers
ssh-keygen -q -t ed25519 -N "" -C "fixture" -f key
printf 'Roblox Manager signature fixture\n%.0s' {1..50} > sample.bin
ssh-keygen -q -Y sign -f key -n roblox-manager-release sample.bin
printf 'fixture@test namespaces="roblox-manager-release" %s\n' "$(cut -d' ' -f1,2 key.pub)" > allowed_signers
rm -f key key.pub
ls -l
