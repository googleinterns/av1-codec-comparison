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

# yapf: disable
import os
import subprocess
import tempfile

libvpx_threads = 4

def aom_command(job, temp_dir):
  assert job['num_spatial_layers'] == 1
  assert job['num_temporal_layers'] == 1
  assert job['codec'] == 'av1'
  # TODO(pbos): Add realtime config (aom-rt) when AV1 is realtime ready.
  assert job['encoder'] == 'aom-good'

  (fd, first_pass_file) = tempfile.mkstemp(dir=temp_dir, suffix=".fpf")
  os.close(fd)

  (fd, encoded_filename) = tempfile.mkstemp(dir=temp_dir, suffix=".webm")
  os.close(fd)

  clip = job['clip']
  fps = int(clip['fps'] + 0.5)
  command = [
    "aom/aomenc",
    "--codec=av1",
    "-p", "2",
    "--fpf=%s" % first_pass_file,
    "--good",
    "--cpu-used=0",
    "--target-bitrate=%d" % job['target_bitrates_kbps'][0],
    '--fps=%d/1' % fps,
    "--lag-in-frames=25",
    "--min-q=0",
    "--max-q=63",
    "--auto-alt-ref=1",
    "--kf-max-dist=150",
    "--kf-min-dist=0",
    "--drop-frame=0",
    "--static-thresh=0",
    "--bias-pct=50",
    "--minsection-pct=0",
    "--maxsection-pct=2000",
    "--arnr-maxframes=7",
    "--arnr-strength=5",
    "--sharpness=0",
    "--undershoot-pct=100",
    "--overshoot-pct=100",
    "--frame-parallel=0",
    "--tile-columns=0",
    "--profile=0",
    '--width=%d' % clip['width'],
    '--height=%d' % clip['height'],
    '--output=%s' % encoded_filename,
    clip['yuv_file'],
  ]
  encoded_files = [{'spatial-layer': 0, 'temporal-layer': 0, 'filename': encoded_filename}]
  return (command, encoded_files)

def libvpx_tl_command(job, temp_dir):
  # Parameters are intended to be as close as possible to realtime settings used
  # in WebRTC.
  assert job['num_temporal_layers'] <= 3
  # TODO(pbos): Account for low resolution CPU levels (see below).
  codec_cpu = 6 if job['codec'] == 'vp8' else 7
  layer_strategy = 8 if job['num_temporal_layers'] == 2 else 10
  outfile_prefix = '%s/out' % temp_dir
  clip = job['clip']
  fps = int(clip['fps'] + 0.5)

  command = [
      'libvpx/examples/vpx_temporal_svc_encoder',
      clip['yuv_file'],
      outfile_prefix,
      job['codec'],
      clip['width'],
      clip['height'],
      '1',
      fps,
      codec_cpu,
      '0',
      libvpx_threads,
      layer_strategy
  ] + job['target_bitrates_kbps']
  command = [str(i) for i in command]
  encoded_files = [{'spatial-layer': 0, 'temporal-layer': i, 'filename': "%s_%d.ivf" % (outfile_prefix, i)} for i in range(job['num_temporal_layers'])]

  return ([str(i) for i in command], encoded_files)

def libvpx_command(job, temp_dir):
  # Parameters are intended to be as close as possible to realtime settings used
  # in WebRTC.
  if (job['num_temporal_layers'] > 1):
    return libvpx_tl_command(job, temp_dir)
  assert job['num_spatial_layers'] == 1
  # TODO(pbos): Account for low resolutions (use -4 and 5 for CPU levels).
  common_params = [
    "--lag-in-frames=0",
    "--error-resilient=1",
    "--kf-min-dist=3000",
    "--kf-max-dist=3000",
    "--static-thresh=1",
    "--end-usage=cbr",
    "--undershoot-pct=100",
    "--overshoot-pct=15",
    "--buf-sz=1000",
    "--buf-initial-sz=500",
    "--buf-optimal-sz=600",
    "--max-intra-rate=900",
    "--resize-allowed=0",
    "--drop-frame=0",
    "--passes=1",
    "--rt",
    "--noise-sensitivity=0",
    "--threads=%d" % libvpx_threads,
  ]
  if job['codec'] == 'vp8':
    codec_params = [
      "--codec=vp8",
      "--cpu-used=-6",
      "--min-q=2",
      "--max-q=56",
      "--screen-content-mode=0",
    ]
  elif job['codec'] == 'vp9':
    codec_params = [
      "--codec=vp9",
      "--cpu-used=7",
      "--min-q=2",
      "--max-q=52",
      "--aq-mode=3",
    ]

  (fd, encoded_filename) = tempfile.mkstemp(dir=temp_dir, suffix=".webm")
  os.close(fd)

  clip = job['clip']
  # Round FPS. For quality comparisons it's likely close enough to not be
  # misrepresentative. From a quality perspective there's no point to fully
  # respecting NTSC or other non-integer FPS formats here.
  fps = int(clip['fps'] + 0.5)

  command = ['libvpx/vpxenc'] + codec_params + common_params + [
    '--fps=%d/1' % fps,
    '--target-bitrate=%d' % job['target_bitrates_kbps'][0],
    '--width=%d' % clip['width'],
    '--height=%d' % clip['height'],
    '--output=%s' % encoded_filename,
    clip['yuv_file']
  ]
  encoded_files = [{'spatial-layer': 0, 'temporal-layer': 0, 'filename': encoded_filename}]
  return (command, encoded_files)


def openh264_command(job, temp_dir):
  assert job['codec'] == 'h264'
  # TODO(pbos): Consider AVC support.
  assert job['num_spatial_layers'] == 1
  # TODO(pbos): Add temporal-layer support (-numtl).
  assert job['num_temporal_layers'] == 1

  (fd, encoded_filename) = tempfile.mkstemp(dir=temp_dir, suffix=".264")
  os.close(fd)

  clip = job['clip']

  command = [
    'openh264/h264enc',
    '-rc', 1,
    '-denois', 0,
    '-scene', 0,
    '-bgd', 0,
    '-fs', 0,
    '-tarb', job['target_bitrates_kbps'][0],
    '-sw', clip['width'],
    '-sh', clip['height'],
    '-frin', clip['fps'],
    '-org', clip['yuv_file'],
    '-bf', encoded_filename,
    '-numl', 1,
    '-dw', 0, clip['width'],
    '-dh', 0, clip['height'],
    '-frout', 0, clip['fps'],
    '-ltarb', 0, job['target_bitrates_kbps'][0],
  ]
  encoded_files = [{'spatial-layer': 0, 'temporal-layer': 0, 'filename': encoded_filename}]
  return ([str(i) for i in command], encoded_files)


def yami_command(job, temp_dir):
  assert job['num_spatial_layers'] == 1
  assert job['num_temporal_layers'] == 1

  (fd, encoded_filename) = tempfile.mkstemp(dir=temp_dir, suffix=".ivf")
  os.close(fd)

  clip = job['clip']
  # Round FPS. For quality comparisons it's likely close enough to not be
  # misrepresentative. From a quality perspective there's no point to fully
  # respecting NTSC or other non-integer FPS formats here.
  fps = int(clip['fps'] + 0.5)

  command = [
    'yami/libyami/bin/yamiencode',
    '--rcmode', 'CBR',
    '--ipperiod', 1,
    '--intraperiod', 3000,
    '-c', job['codec'].upper(),
    '-i', clip['yuv_file'],
    '-W', clip['width'],
    '-H', clip['height'],
    '-f', fps,
    '-o', encoded_filename,
    '-b', job['target_bitrates_kbps'][0],
  ]
  encoded_files = [{'spatial-layer': 0, 'temporal-layer': 0, 'filename': encoded_filename}]
  return ([str(i) for i in command], encoded_files)

encoder_commands = {
  'aom-good' : aom_command,
  'openh264' : openh264_command,
  'libvpx-rt' : libvpx_command,
  'yami' : yami_command,
}