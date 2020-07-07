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
import binary_vars


libvpx_threads = 4

INTRA_IVAL_LOW_LATENCY = 60

RAV1E_SPEED = 4
SVT_SPEED = 2
AOM_SPEED = 2

AOM_RT_SPEED = 5
RAV1E_RT_SPEED = 7
SVT_RT_SPEED = 5

def rav1e_command(job, temp_dir):
    assert job['num_spatial_layers'] == 1
    assert job['num_temporal_layers'] == 1
    assert job['codec'] == 'av1'
    assert job['encoder'] in ['rav1e-1pass', 'rav1e-rt', 'rav1e-all_intra']

    (fd, encoded_filename) = tempfile.mkstemp(dir=temp_dir, suffix=".ivf")
    os.close(fd)

    clip = job['clip']
    fps = int(clip['fps'] + 0.5)

    common_params = [
        '-y',
        '--output', encoded_filename,
        '--bitrate', job['target_bitrates_kbps'][0],
        clip['y4m_file']
    ]


    encoder = job['encoder']

    if encoder == 'rav1e-1pass':
        codec_params = [
            '--speed', RAV1E_SPEED,
            '--low-latency',
            '--keyint', INTRA_IVAL_LOW_LATENCY
        ]
    elif encoder == 'rav1e-rt':
        codec_params = [
            '--low-latency',
            '--speed', RAV1E_RT_SPEED,
            '--keyint', INTRA_IVAL_LOW_LATENCY
        ]
    elif encoder == 'rav1e-all_intra':
        codec_params = [
            '--speed', '4',
            '--keyint', '1'
        ]

    command = [binary_vars.RAV1E_ENC_BIN] + codec_params + common_params

    command = [str(flag) for flag in command]

    encoded_files = [{'spatial-layer': 0,
                      'temporal-layer': 0, 'filename': encoded_filename
                      }]

    return command, encoded_files


def svt_command(job, temp_dir):
    assert job['num_spatial_layers'] == 1
    assert job['num_temporal_layers'] == 1
    assert job['codec'] == 'av1'
    assert job['encoder'] in ['svt-1pass', 'svt-rt', 'svt-all_intra']

    (fd, encoded_filename) = tempfile.mkstemp(dir=temp_dir, suffix=".ivf")
    os.close(fd)

    clip = job['clip']
    fps = int(clip['fps'] + 0.5)

    common_params = [
        '--fps', fps,
        '-w', clip['width'],
        '-h', clip['height'],
        '-i', clip['yuv_file'],
        '-b', encoded_filename,
        '--tbr', job['target_bitrates_kbps'][0]
    ]

    encoder = job['encoder']

    if encoder == 'svt-1pass':

        codec_params = [
            '--preset', "8",
        ]
    elif encoder == 'svt-rt':

        codec_params = [
            '--scm', 0,
            '--lookahead', 0,
            '--preset', SVT_RT_SPEED,
            '--keyint', (INTRA_IVAL_LOW_LATENCY - 1)
        ]

    elif encoder == 'svt-all_intra':

        codec_params = [
            '--scm', 0,
            '--keyint', 0,
            '--preset', SVT_SPEED,
        ]

    command = [binary_vars.SVT_ENC_BIN] + codec_params + common_params

    command = [str(flag) for flag in command]

    encoded_files = [{'spatial-layer': 0,
                      'temporal-layer': 0, 'filename': encoded_filename
                      }]

    return command, encoded_files


def aom_command(job, temp_dir):
    assert job['num_spatial_layers'] == 1
    assert job['num_temporal_layers'] == 1
    assert job['codec'] == 'av1'
    assert job['encoder'] in ['aom-good', 'aom-rt', 'aom-all_intra', 'aom-offline']

    (fd, first_pass_file) = tempfile.mkstemp(dir=temp_dir, suffix=".fpf")
    os.close(fd)

    (fd, encoded_filename) = tempfile.mkstemp(dir=temp_dir, suffix=".webm")
    os.close(fd)

    clip = job['clip']
    fps = int(clip['fps'] + 0.5)

    common_params = [
        '--codec=av1',
        '--width=%d' % clip['width'],
        '--height=%d' % clip['height'],
        '--output=%s' % encoded_filename,
        '--target-bitrate=%d' % job['target_bitrates_kbps'][0],
        clip['yuv_file']
    ]

    encoder = job['encoder']

    if encoder == 'aom-good':
        codec_params = [
            '--good',
            "-p", "2",
            "--lag-in-frames=25",
            '--cpu-used=3',
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
            "--profile=0"
        ]

    elif encoder == 'aom-all_intra':
        codec_params = [
            '--cpu-used=4',
            '--kf-max-dist=1',
            '--end-usage=q'
        ]
    elif encoder == 'aom-rt':
        codec_params = [
            '--cpu-used=%d' % AOM_RT_SPEED,
            '--disable-warning-prompt',
            '--enable-tpl-model=0',
            '--deltaq-mode=0',
            '--sb-size=0',
            '--ivf',
            '--profile=0',
            '--static-thresh=0',
            '--undershoot-pct=50',
            '--overshoot-pct=50',
            '--buf-sz=1000',
            '--buf-initial-sz=500',
            '--buf-optimal-sz=600',
            '--max-intra-rate=300',
            '--passes=1',
            '--rt',
            '--lag-in-frames=0',
            '--noise-sensitivity=0',
            '--error-resilient=1',
        ]
    elif encoder == 'aom-offline':
        codec_params = [
            '--good',
            "--passes=2",
            '--threads=0',
            "--lag-in-frames=25",
            '--cpu-used=%d' % AOM_SPEED,
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
            "--undershoot-pct=25",
            "--overshoot-pct=25",
            "--frame-parallel=1",
            "--tile-columns=3",
            "--profile=0"
        ]

    command = [binary_vars.AOM_ENC_BIN] + codec_params + common_params

    encoded_files = [{'spatial-layer': 0,
                      'temporal-layer': 0, 'filename': encoded_filename}]
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
        binary_vars.VPX_SVC_ENC_BIN,
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

    command = [binary_vars.VPX_ENC_BIN] + codec_params + common_params + [
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
      binary_vars.H264_ENC_BIN,
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
      binary_vars.YAMI_ENC_BIN,
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

def get_encoder_command(encoder):
    encoders = [
        'aom-good', 'aom-rt', 'aom-all_intra', 'aom-offline', ## AOM CONFIGS
        'rav1e-1pass', 'rav1e-rt', 'rav1e-all_intra', ## RAV1E CONFIGS
        'svt-1pass', 'svt-rt', 'svt-all_intra', ## SVT CONFIGS
        'openh264', ## OPENH264 CONFIGS
        'libvpx-rt', ## LIBVPX CONFIGS
        'yami' ## YAMI CONFIGS
    ]

    if encoder not in encoders:
        return None

    if 'aom' in encoder:
        return aom_command
    elif 'rav1e' in encoder:
        return rav1e_command
    elif 'svt' in encoder:
        return svt_command
    elif 'libvpx' in encoder:
        return libvpx_command
    elif 'openh264' in encoder:
        return openh264_command
    elif 'yami' in encoder:
        return yami_command
