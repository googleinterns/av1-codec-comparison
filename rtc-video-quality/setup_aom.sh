#!/bin/bash
# Copyright 2017 Google Inc. All rights reserved.
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

## Note: This is a fork from the google/rtc-video-quality with modified changes made

set -x

# Download aom if not available.
if [ ! -d aom ]; then
  git clone https://aomedia.googlesource.com/aom
fi

# Check out the pinned aom version.
pushd aom
git fetch
git checkout --detach b2209ceed75ba9e48b680f94d4fbca419a4eec6d

mkdir -p aom_build
pushd aom_build
# Build aom
cmake ../
make
