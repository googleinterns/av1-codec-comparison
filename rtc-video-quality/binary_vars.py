# Copyright 2020 Google LLC

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     https://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Encoder Binaries
RAV1E_ENC_BIN = 'rav1e/target/release/rav1e'
SVT_ENC_BIN = 'SVT-AV1/Bin/Release/SvtAv1EncApp'
AOM_ENC_BIN = 'aom/aom_build/aomenc'
VPX_ENC_BIN = 'libvpx/vpxenc'
H264_ENC_BIN = 'openh264/h264enc'
YAMI_ENC_BIN = 'yami/libyami/bin/yamiencode'
VPX_SVC_ENC_BIN = 'libvpx/examples/vpx_temporal_svc_encoder'

# Decoder Binary
AOM_DEC_BIN = 'aom/aom_build/aomdec'
VPX_DEC_BIN = 'libvpx/vpxdec'
H264_DEC_BIN = 'openh264/h264dec'

# Metrics Binary
TINY_SSIM_BIN = 'libvpx/tools/tiny_ssim'
VMAF_BIN = 'vmaf/libvmaf/build/tools/vmafossexec'