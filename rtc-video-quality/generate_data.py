#!/usr/bin/env python3
# Copyright 2016 Google Inc. All rights reserved.
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

import argparse
import csv
import json
import multiprocessing
import os
import pprint
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import shlex

from encoder_commands import *
import binary_vars

binary_absolute_paths = {}


def find_absolute_path(use_system_path, binary):
    global binary_absolute_paths
    if binary in binary_absolute_paths:
        return binary_absolute_paths[binary]

    if use_system_path:
        for path in os.environ["PATH"].split(os.pathsep):
            target = os.path.join(path.strip('"'), os.path.basename(binary))
            if os.path.isfile(target) and os.access(target, os.X_OK):
                binary_absolute_paths[binary] = target
                return target
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), binary)
    if os.path.isfile(target) and os.access(target, os.X_OK):
        if use_system_path:
            print(
                "WARNING: '%s' not in PATH (using --use-system-path), falling back on locally-compiled binary."
                % os.path.basename(binary))
        binary_absolute_paths[binary] = target
        return target

    sys.exit(
        "ERROR: '%s' missing, did you run the corresponding setup script?" %
        (os.path.basename(binary) if use_system_path else target))


yuv_clip_pattern = re.compile(r"^(.*[\._](\d+)_(\d+).yuv):(\d+)$")


def clip_arg(clip):
    (file_root, file_ext) = os.path.splitext(clip)
    if file_ext == '.y4m':
        width = int(
            subprocess.check_output(
                ["mediainfo", "--Inform=Video;%Width%", clip],
                encoding='utf-8'))
        height = int(
            subprocess.check_output(
                ["mediainfo", "--Inform=Video;%Height%", clip],
                encoding='utf-8'))
        fps = float(
            subprocess.check_output(
                ["mediainfo", "--Inform=Video;%FrameRate%", clip],
                encoding='utf-8'))
        return {
            'input_file': clip,
            'height': height,
            'width': width,
            'fps': fps,
            'file_type': 'y4m'
        }

    # Make sure YUV files are correctly formatted + look readable before actually
    # running the script on them.
    clip_match = yuv_clip_pattern.match(clip)
    if not clip_match:
        raise argparse.ArgumentTypeError(
            "Argument '%s' doesn't match input format.\n" % clip)
    input_file = clip_match.group(1)
    if not os.path.isfile(input_file) or not os.access(input_file, os.R_OK):
        raise argparse.ArgumentTypeError(
            "'%s' is either not a file or cannot be opened for reading.\n" %
            input_file)
    return {
        'input_file': clip_match.group(1),
        'width': int(clip_match.group(2)),
        'height': int(clip_match.group(3)),
        'fps': float(clip_match.group(4)),
        'file_type': 'yuv'
    }


def encoder_pairs(string):
    pair_pattern = re.compile(r"^([\w\-]+):(\w+)$")
    encoders = []
    for pair in string.split(','):
        pair_match = pair_pattern.match(pair)
        if not pair_match:
            raise argparse.ArgumentTypeError(
                "Argument '%s' of '%s' doesn't match input format.\n" %
                (pair, string))
        if not get_encoder_command(pair_match.group(1)):
            raise argparse.ArgumentTypeError(
                "Unknown encoder: '%s' in pair '%s'\n" %
                (pair_match.group(1), pair))
        encoders.append((pair_match.group(1), pair_match.group(2)))
    return encoders


def writable_dir(directory):
    if not os.path.isdir(directory) or not os.access(directory, os.W_OK):
        raise argparse.ArgumentTypeError(
            "'%s' is either not a directory or cannot be opened for writing.\n"
            % directory)
    return directory


def positive_int(num):
    num_int = int(num)
    if num_int <= 0:
        raise argparse.ArgumentTypeError("'%d' is not a positive integer.\n" %
                                         num)
    return num_int


parser = argparse.ArgumentParser(
    description='Generate graph data for video-quality comparison.')
parser.add_argument('clips',
                    nargs='+',
                    metavar='clip_WIDTH_HEIGHT.yuv:FPS|clip.y4m',
                    type=clip_arg)
parser.add_argument('--dump-commands', action='store_true')
parser.add_argument('--enable-vmaf', action='store_true')
parser.add_argument('--encoded-file-dir', default=None, type=writable_dir)
parser.add_argument('--encoders',
                    required=True,
                    metavar='encoder:codec,encoder:codec...',
                    type=encoder_pairs)
parser.add_argument('--frame-offset', default=0, type=positive_int)
parser.add_argument('--num-frames', default=-1, type=positive_int)
# TODO(pbos): Add support for multiple spatial layers.
parser.add_argument('--num-spatial-layers', type=int, default=1, choices=[1])
parser.add_argument('--num-temporal-layers',
                    type=int,
                    default=1,
                    choices=[1, 2, 3])
parser.add_argument('--out',
                    required=True,
                    metavar='output.txt',
                    type=argparse.FileType('w'))
parser.add_argument('--use-system-path', action='store_true')
parser.add_argument('--workers', type=int, default=multiprocessing.cpu_count())


def prepare_clips(args, temp_dir):
    clips = args.clips
    y4m_clips = [clip for clip in clips if clip['file_type'] == 'y4m']
    if y4m_clips:
        print("Converting %d .y4m clip%s..." %
              (len(y4m_clips), "" if len(y4m_clips) == 1 else "s"))
        for clip in y4m_clips:
            (fd, yuv_file) = tempfile.mkstemp(dir=temp_dir,
                                              suffix=".%d_%d.yuv" %
                                              (clip['width'], clip['height']))
            os.close(fd)
            with open(os.devnull, 'w') as devnull:
                subprocess.check_call(
                    ['ffmpeg', '-y', '-i', clip['input_file'], yuv_file],
                    stdout=devnull,
                    stderr=devnull,
                    encoding='utf-8')
            clip['yuv_file'] = yuv_file
    for clip in clips:
        clip['sha1sum'] = subprocess.check_output(
            ['sha1sum', clip['input_file']], encoding='utf-8').split(' ', 1)[0]
        if 'yuv_file' not in clip:
            clip['yuv_file'] = clip['input_file']
        frame_size = 6 * clip['width'] * clip['height'] / 4
        input_yuv_filesize = os.path.getsize(clip['yuv_file'])
        clip['input_total_frames'] = input_yuv_filesize / frame_size
        # Truncate file if necessary.
        if args.frame_offset > 0 or args.num_frames > 0:
            (fd, truncated_filename) = tempfile.mkstemp(dir=temp_dir,
                                                        suffix=".yuv")
            blocksize = 2048 * 1024
            total_filesize = args.num_frames * frame_size
            with os.fdopen(fd, 'wb', blocksize) as truncated_file:
                with open(clip['yuv_file'], 'rb') as original_file:
                    original_file.seek(args.frame_offset * frame_size)
                    while total_filesize > 0:
                        data = original_file.read(
                            blocksize
                            if blocksize < total_filesize else total_filesize)
                        truncated_file.write(data)
                        total_filesize -= blocksize
            clip['yuv_file'] = truncated_filename

        (fd, y4m_file) = tempfile.mkstemp(dir=temp_dir, suffix='.y4m')
        os.close(fd)

        with open(os.devnull, 'w') as devnull:
            subprocess.check_call([
                'ffmpeg', '-y', '-s',
                '%dx%d' % (clip['width'], clip['height']), '-r',
                str(int(clip['fps'] + 0.5)), '-pix_fmt', 'yuv420p', '-i',
                clip['yuv_file'], y4m_file
            ],
                                  stdout=devnull,
                                  stderr=devnull)

        clip['y4m_file'] = y4m_file


def decode_file(job, temp_dir, encoded_file):
    (fd, decoded_file) = tempfile.mkstemp(dir=temp_dir, suffix=".yuv")
    os.close(fd)
    (fd, framestats_file) = tempfile.mkstemp(dir=temp_dir, suffix=".csv")
    os.close(fd)
    with open(os.devnull, 'w') as devnull:
        if job['codec'] in ['av1', 'vp8', 'vp9']:
            decoder = binary_vars.AOM_DEC_BIN if job[
                'codec'] == 'av1' else binary_vars.VPX_DEC_BIN
            subprocess.check_call([
                decoder, '--i420',
                '--codec=%s' % job['codec'], '-o', decoded_file, encoded_file,
                '--framestats=%s' % framestats_file
            ],
                                  stdout=devnull,
                                  stderr=devnull,
                                  encoding='utf-8')
        elif job['codec'] == 'h264':
            subprocess.check_call(
                [binary_vars.H264_DEC_BIN, encoded_file, decoded_file],
                stdout=devnull,
                stderr=devnull,
                encoding='utf-8')
            # TODO(pbos): Generate H264 framestats.
            framestats_file = None
    return (decoded_file, framestats_file)


def add_framestats(results_dict, framestats_file, statstype):
    with open(framestats_file) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            for (metric, value) in row.items():
                metric_key = 'frame-%s' % metric
                if metric_key not in results_dict:
                    results_dict[metric_key] = []
                results_dict[metric_key].append(statstype(value))


def generate_metrics(results_dict, job, temp_dir, encoded_file):
    (decoded_file, decoder_framestats) = decode_file(job, temp_dir,
                                                     encoded_file['filename'])
    clip = job['clip']
    temporal_divide = 2**(job['num_temporal_layers'] - 1 -
                          encoded_file['temporal-layer'])
    temporal_skip = temporal_divide - 1
    # TODO(pbos): Perform SSIM on downscaled .yuv files for spatial layers.
    (fd, metrics_framestats) = tempfile.mkstemp(dir=temp_dir, suffix=".csv")
    os.close(fd)
    ssim_results = subprocess.check_output([
        binary_vars.TINY_SSIM_BIN, clip['yuv_file'], decoded_file,
        "%dx%d" % (results_dict['width'], results_dict['height']),
        str(temporal_skip), metrics_framestats
    ],
                                           encoding='utf-8').splitlines()

    metric_map = {
        'AvgPSNR': 'avg-psnr',
        'AvgPSNR-Y': 'avg-psnr-y',
        'AvgPSNR-U': 'avg-psnr-u',
        'AvgPSNR-V': 'avg-psnr-v',
        'GlbPSNR': 'glb-psnr',
        'GlbPSNR-Y': 'glb-psnr-y',
        'GlbPSNR-U': 'glb-psnr-u',
        'GlbPSNR-V': 'glb-psnr-v',
        'SSIM': 'ssim',
        'SSIM-Y': 'ssim-y',
        'SSIM-U': 'ssim-u',
        'SSIM-V': 'ssim-v',
        'VpxSSIM': 'vpx-ssim',
    }
    for line in ssim_results:
        if not line:
            continue
        (metric, value) = line.split(': ')
        if metric in metric_map:
            results_dict[metric_map[metric]] = float(value)
        elif metric == 'Nframes':
            layer_frames = int(value)
            results_dict['frame-count'] = layer_frames

    if decoder_framestats:
        add_framestats(results_dict, decoder_framestats, int)
    add_framestats(results_dict, metrics_framestats, float)

    if args.enable_vmaf:
        (fd, results_file) = tempfile.mkstemp(
            dir=temp_dir,
            suffix="%s-%s-%d.json" %
            (job['encoder'], job['codec'], job['qp_value']))
        os.close(fd)
        vmaf_results = subprocess.check_output([
            binary_vars.VMAF_BIN, 'yuv420p',
            str(results_dict['width']),
            str(results_dict['height']), clip['yuv_file'], decoded_file,
            '--out-fmt', 'json'
        ],
                                               encoding='utf-8')
        with open(results_file, 'r') as results_file:
            vmaf_obj = json.load(results_file)
        results_dict['vmaf'] = float(vmaf_obj['VMAF score'])

        results_dict['frame-vmaf'] = []
        for frame in vmaf_obj['frames']:
            results_dict['frame-vmaf'].append(frame['metrics']['vmaf'])

    layer_fps = clip['fps'] / temporal_divide
    results_dict['layer-fps'] = layer_fps

    spatial_divide = 2**(job['num_spatial_layers'] - 1 -
                         encoded_file['spatial-layer'])

    results_dict['layer-width'] = results_dict['width'] // spatial_divide
    results_dict['layer-height'] = results_dict['height'] // spatial_divide

    target_bitrate_bps = job['target_bitrates_kbps'][
        encoded_file['temporal-layer']] * 1000
    bitrate_used_bps = os.path.getsize(
        encoded_file['filename']) * 8 * layer_fps / layer_frames
    results_dict['target-bitrate-bps'] = target_bitrate_bps
    results_dict['actual-bitrate-bps'] = bitrate_used_bps
    results_dict['bitrate-utilization'] = float(
        bitrate_used_bps) / target_bitrate_bps


def run_command(job, encoder_command, job_temp_dir, encoded_file_dir):
    (command, encoded_files) = encoder_command
    clip = job['clip']
    start_time = time.time()
    try:
        process = subprocess.Popen(' '.join(
            shlex.quote(arg) if arg != '&&' else arg for arg in command),
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,
                                   encoding='utf-8',
                                   shell=True)
    except OSError as e:
        return (None, "> %s\n%s" % (" ".join(command), e))
    (output, _) = process.communicate()
    actual_encode_ms = (time.time() - start_time) * 1000
    input_yuv_filesize = os.path.getsize(clip['yuv_file'])
    input_num_frames = int(input_yuv_filesize /
                           (6 * clip['width'] * clip['height'] / 4))
    target_encode_ms = float(input_num_frames) * 1000 / clip['fps']
    if process.returncode != 0:
        return (None, "> %s\n%s" % (" ".join(command), output))
    results = [{} for i in range(len(encoded_files))]
    for i in range(len(results)):
        results_dict = results[i]
        results_dict['input-file'] = os.path.basename(clip['input_file'])
        results_dict['input-file-sha1sum'] = clip['sha1sum']
        results_dict['input-total-frames'] = clip['input_total_frames']
        results_dict['frame-offset'] = args.frame_offset
        results_dict['bitrate-config-kbps'] = job['target_bitrates_kbps']
        results_dict['layer-pattern'] = "%dsl%dtl" % (
            job['num_spatial_layers'], job['num_temporal_layers'])
        results_dict['encoder'] = job['encoder']
        results_dict['codec'] = job['codec']
        results_dict['height'] = clip['height']
        results_dict['width'] = clip['width']
        results_dict['fps'] = clip['fps']
        results_dict['actual-encode-time-ms'] = actual_encode_ms
        results_dict['target-encode-time-ms'] = target_encode_ms
        results_dict[
            'encode-time-utilization'] = actual_encode_ms / target_encode_ms
        layer = encoded_files[i]

        results_dict['temporal-layer'] = layer['temporal-layer']
        results_dict['spatial-layer'] = layer['spatial-layer']

        generate_metrics(results_dict, job, job_temp_dir, layer)
        if encoded_file_dir:
            encoded_file_pattern = "%s-%s-%s-%dsl%dtl-%d-sl%d-tl%d%s" % (
                os.path.splitext(os.path.basename(
                    clip['input_file']))[0], job['encoder'], job['codec'],
                job['num_spatial_layers'], job['num_temporal_layers'],
                job['target_bitrates_kbps'][-1], layer['spatial-layer'],
                layer['temporal-layer'], os.path.splitext(layer['filename'])[1])
            shutil.move(layer['filename'],
                        os.path.join(encoded_file_dir, encoded_file_pattern))
        else:
            os.remove(layer['filename'])

    shutil.rmtree(job_temp_dir)

    return (results, output)


def find_bitrates(width, height):
    # Do multiples of 100, because grouping based on bitrate splits in
    # generate_graphs.py doesn't round properly.

    # TODO(pbos): Propagate the bitrate split in the data instead of inferring it
    # from the job to avoid rounding errors.

    # Significantly lower than exact value, so 800p still counts as 720p for
    # instance.
    pixel_bound = width * height / 1.5
    if pixel_bound <= 320 * 240:
        return [100, 200, 400, 600, 800, 1200]
    if pixel_bound <= 640 * 480:
        return [200, 300, 500, 800, 1200, 2000]
    if pixel_bound <= 1280 * 720:
        return [400, 800, 1200, 1600, 2500, 5000]
    if pixel_bound <= 1920 * 1080:
        return [800, 1200, 2000, 3000, 5000, 10000]
    return [1200, 1800, 3000, 6000, 10000, 15000]


layer_bitrates = [[1], [0.6, 1], [0.45, 0.65, 1]]


def split_temporal_bitrates_kbps(target_bitrate_kbps, num_temporal_layers):
    bitrates_kbps = []
    for i in range(num_temporal_layers):
        layer_bitrate_kbps = int(layer_bitrates[num_temporal_layers - 1][i] *
                                 target_bitrate_kbps)
        bitrates_kbps.append(layer_bitrate_kbps)
    return bitrates_kbps


def generate_jobs(args, temp_dir):
    jobs = []
    for clip in args.clips:
        bitrates = find_bitrates(clip['width'], clip['height'])
        for bitrate_kbps in bitrates:
            for (encoder, codec) in args.encoders:
                job = {
                    'encoder':
                        encoder,
                    'codec':
                        codec,
                    'clip':
                        clip,
                    'target_bitrates_kbps':
                        split_temporal_bitrates_kbps(bitrate_kbps,
                                                     args.num_temporal_layers),
                    'num_spatial_layers':
                        args.num_spatial_layers,
                    'num_temporal_layers':
                        args.num_temporal_layers,
                }
                job_temp_dir = tempfile.mkdtemp(dir=temp_dir)
                (command, encoded_files) = get_encoder_command(job['encoder'])(
                    job, job_temp_dir)
                full_command = find_absolute_path(args.use_system_path,
                                                  command[0])
                command = [
                    full_command if word == command[0] else word
                    for word in command
                ]
                jobs.append((job, (command, encoded_files), job_temp_dir))
    return jobs


def start_daemon(func):
    t = threading.Thread(target=func)
    t.daemon = True
    t.start()
    return t


def job_to_string(job):
    return "%s:%s %dsl%dtl %s %s" % (
        job['encoder'], job['codec'], job['num_spatial_layers'],
        job['num_temporal_layers'], ":".join(
            str(i) for i in job['target_bitrates_kbps']),
        os.path.basename(job['clip']['input_file']))


def worker():
    global args
    global jobs
    global current_job
    global has_errored
    global total_jobs
    pp = pprint.PrettyPrinter(indent=2)
    while True:
        with thread_lock:
            if not jobs:
                return
            (job, command, job_temp_dir) = jobs.pop()

        (results, error) = run_command(job, command, job_temp_dir,
                                       args.encoded_file_dir)

        job_str = job_to_string(job)

        with thread_lock:
            current_job += 1
            run_ok = results is not None
            print(
                "[%d/%d] %s (%s)" %
                (current_job, total_jobs, job_str, "OK" if run_ok else "ERROR"))
            if not run_ok:
                has_errored = True
                print(error)
            else:
                for result in results:
                    args.out.write(pp.pformat(result))
                    args.out.write(',\n')
                args.out.flush()


thread_lock = threading.Lock()


def main():
    global args
    global jobs
    global total_jobs
    global current_job
    global has_errored

    temp_dir = tempfile.mkdtemp()

    args = parser.parse_args()
    prepare_clips(args, temp_dir)
    jobs = generate_jobs(args, temp_dir)
    total_jobs = len(jobs)
    current_job = 0
    has_errored = False

    if args.dump_commands:
        for (job, (command, encoded_files), job_temp_dir) in jobs:
            current_job += 1
            print("[%d/%d] %s" % (current_job, total_jobs, job_to_string(job)))
            print("> %s" % " ".join(command))
            print()

        shutil.rmtree(temp_dir)
        return 0

    # Make sure commands for quality metrics are present.
    find_absolute_path(False, binary_vars.TINY_SSIM_BIN)
    for (encoder, codec) in args.encoders:
        if codec in ['vp8', 'vp9']:
            find_absolute_path(False, binary_vars.VPX_DEC_BIN)
        elif codec == 'av1':
            find_absolute_path(False, binary_vars.AOM_DEC_BIN)
        elif codec == 'h264':
            find_absolute_path(False, binary_vars.H264_DEC_BIN)
    if args.enable_vmaf:
        find_absolute_path(False, binary_vars.VMAF_BIN)

    print("[0/%d] Running jobs..." % total_jobs)

    args.out.write('[')

    workers = [start_daemon(worker) for i in range(args.workers)]
    [t.join() for t in workers]

    args.out.write(']\n')

    shutil.rmtree(temp_dir)
    return 1 if has_errored else 0


if __name__ == '__main__':
    sys.exit(main())
