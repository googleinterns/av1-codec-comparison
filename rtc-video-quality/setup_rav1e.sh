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

## Check if cargo command exists for building
if ! [ -x "$(command -v cargo)" ]; then 
    echo "Error: Cargo is not installed." >&2
    exit 1
fi

set -x 

# Download rav1e if not available
if [ ! -d rav1e ]; then 
    git clone https://github.com/xiph/rav1e
fi

## Check out the pinned rav1e version
pushd rav1e
git fetch 
git checkout --detach 99114995e8771dd923a146e5616f7474e9b33eb7

## Build rav1e
cargo build --release
