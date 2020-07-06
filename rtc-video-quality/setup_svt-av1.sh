#!/bin/bash
# Copyright 2020 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -x 

# Download SVT-AV1 if not available
if [ ! -d SVT-AV1 ]; then 
    git clone https://github.com/OpenVisualCloud/SVT-AV1
fi

# Check out the pinned SVT-AV1 version
pushd SVT-AV1
git fetch
git checkout --detach ba72bc8511ed6a31544152590740e85f99a41300

# Build SVT-AV1
pushd Build/linux
./build.sh release