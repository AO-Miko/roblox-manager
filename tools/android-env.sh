# Source this file to build the Android app:  . tools/android-env.sh
# The tools live in ~/android-toolchain (JDK 21, Android SDK, Gradle), outside the repository.
export ANDROID_TOOLCHAIN="${ANDROID_TOOLCHAIN:-$HOME/android-toolchain}"
export JAVA_HOME="$ANDROID_TOOLCHAIN/jdk21"
export ANDROID_HOME="$ANDROID_TOOLCHAIN/sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_TOOLCHAIN/gradle-8.10.2/bin:$PATH"
