#!/bin/sh
cd external/tdlib
mkdir build
cd build
cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DOPENSSL_ROOT_DIR=/opt/homebrew/opt/openssl@3 \
  -DOPENSSL_LIBRARIES=/opt/homebrew/opt/openssl@3/lib \
  -DOPENSSL_INCLUDE_DIR=/opt/homebrew/opt/openssl@3/include \
  -DJAVA_HOME=/Users/ymy/Library/Java/JavaVirtualMachines/corretto-21.0.6/Contents/Home/ \
  -DCMAKE_INSTALL_PREFIX:PATH=../example/java/td -DTD_ENABLE_JNI=ON ..
cmake --build . --target install
cd ..
cd example/java
rm -rf build
mkdir build
cd build
cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 -DJAVA_HOME=/Users/ymy/Library/Java/JavaVirtualMachines/corretto-21.0.6/Contents/Home -DCMAKE_INSTALL_PREFIX:PATH=../../../tdlib -DTd_DIR:PATH=/Users/ymy/IdeaProjects/bodhi/tg-harvester/external/tdlib/td/example/java/td/lib/cmake/Td ..
cmake --build . --target install