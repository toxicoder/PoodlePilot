#!/bin/bash

set -e

# Install dependencies
pip install scons numpy pycryptodome

# Install Flutter SDK
FLUTTER_VERSION="3.10.5"
FLUTTER_DIR="$HOME/flutter"

if [ ! -d "$FLUTTER_DIR" ]; then
  git clone https://github.com/flutter/flutter.git -b $FLUTTER_VERSION --depth 1 $FLUTTER_DIR
fi

export PATH="$FLUTTER_DIR/bin:$PATH"

flutter precache
flutter doctor
