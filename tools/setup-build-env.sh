#!/usr/bin/env bash
# Sets up a computer to build and publish Roblox Manager releases (tools/release.sh, tools/promote.sh): Linux, or Windows through WSL.
#
#   Windows:  in PowerShell, once:   wsl --install -d Ubuntu     (restart if asked, make the Ubuntu user)
#             then in the Ubuntu window:   bash tools/setup-build-env.sh
#   Linux:    bash tools/setup-build-env.sh
#
# It installs: python3 + pip, git, gh (GitHub), the OpenSSH client, curl, unzip, and into ~/android-toolchain: JDK 21 and the Android SDK
# (the places tools/android-env.sh expects). Nothing outside your home folder is changed except the packages. Safe to run again.
# The signing keys are NOT made here: copy ~/.config/roblox-manager-release/ from the backup (see the end of this script's output).
set -euo pipefail
TC="${ANDROID_TOOLCHAIN:-$HOME/android-toolchain}"
JDK_URL="https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jdk/hotspot/normal/eclipse"
CMDLINE_URL="https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"

echo "== Packages"
if command -v apt-get >/dev/null; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3 python3-pip python3-venv git openssh-client curl unzip ca-certificates
  if ! command -v gh >/dev/null; then
    sudo mkdir -p -m 755 /etc/apt/keyrings
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
    sudo apt-get update -qq && sudo apt-get install -y -qq gh
  fi
elif command -v dnf >/dev/null; then
  sudo dnf install -y -q python3 python3-pip git openssh-clients curl unzip gh
else
  echo "Install python3, pip, git, gh, openssh, curl and unzip yourself, then run this again."
fi

mkdir -p "$TC/downloads"
if [[ ! -x "$TC/jdk21/bin/java" ]]; then
  echo "== JDK 21"
  curl -fL --retry 3 -o "$TC/downloads/jdk21.tar.gz" "$JDK_URL"
  rm -rf "$TC/jdk21"; mkdir -p "$TC/jdk21"
  tar -xzf "$TC/downloads/jdk21.tar.gz" -C "$TC/jdk21" --strip-components=1
fi

if [[ ! -x "$TC/sdk/cmdline-tools/latest/bin/sdkmanager" ]]; then
  echo "== Android command-line tools"
  curl -fL --retry 3 -o "$TC/downloads/cmdline-tools.zip" "$CMDLINE_URL"
  rm -rf "$TC/sdk/cmdline-tools"; mkdir -p "$TC/sdk/cmdline-tools"
  unzip -q "$TC/downloads/cmdline-tools.zip" -d "$TC/sdk/cmdline-tools"
  mv "$TC/sdk/cmdline-tools/cmdline-tools" "$TC/sdk/cmdline-tools/latest"
fi

echo "== Android SDK parts (platforms 35 and 37, build tools 35 and 36)"
export JAVA_HOME="$TC/jdk21" ANDROID_HOME="$TC/sdk" ANDROID_SDK_ROOT="$TC/sdk"
SDKM="$TC/sdk/cmdline-tools/latest/bin/sdkmanager"
yes | "$SDKM" --licenses >/dev/null 2>&1 || true
"$SDKM" "platform-tools" "platforms;android-35" "platforms;android-37.0" "build-tools;35.0.0" "build-tools;36.0.0" >/dev/null

echo
echo "Done. Checks:"
. "$(cd "$(dirname "$0")" && pwd)/android-env.sh"
java -version 2>&1 | head -1
for t in python3 git gh ssh-keygen curl; do printf '  %-11s %s\n' "$t" "$(command -v "$t" || echo MISSING)"; done
if [[ -f "$HOME/.config/roblox-manager-release/signing_key" ]]; then
  echo "  signing keys: found"
else
  echo "  signing keys: MISSING. From the backup folder run:"
  echo "    mkdir -p ~/.config/roblox-manager-release && cp /mnt/<drive>/.../signing-keys/* ~/.config/roblox-manager-release/ && chmod 600 ~/.config/roblox-manager-release/*"
  echo "  (in WSL a Windows drive D: is /mnt/d)"
fi
echo "Next: gh auth login   then in the repository:  git config gpg.format ssh && git config user.signingkey ~/.config/roblox-manager-release/signing_key.pub"
echo "      git config commit.gpgsign true && git config tag.gpgsign true && git config gpg.ssh.allowedsignersfile tools/trust/allowed_signers"
