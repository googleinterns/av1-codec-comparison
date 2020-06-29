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

import os
import subprocess
import tempfile
import time
import global_variables
from binary_vars import *
import csv
import shutil


def find_bitrates(width, height):
    """
    Given the width and height of the video file, generate a list of bitrates
    to use for the encoder
    """
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


def find_qp(width, height):
    return [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]


def split_temporal_bitrates_kbps(target_bitrate_kbps, num_temporal_layers):

    layer_bitrates = [[1], [0.6, 1], [0.45, 0.65, 1]]

    bitrates_kbps = []
    for i in range(num_temporal_layers):
        layer_bitrate_kbps = int(
            layer_bitrates[num_temporal_layers - 1][i] * target_bitrate_kbps)
        bitrates_kbps.append(layer_bitrate_kbps)
    return bitrates_kbps


def run_command(job, encoder_command, job_temp_dir, encoded_file_dir):
    """
    This function will run the external encoder command and generate the metrics for
    the encoded file

    Args:
        job: {
          'encoder': str,
          'codec': str,
          'clip': {
              'file_type': str,
              'input_file': str,
              'height': int,
              'width': int,
              'fps': float,
              'yuv_file': str,
              'sha1sum': str,
              'input_total_frames': float
          },
          'target_bitrate_kbps': List[int],
          'num_spatial_layers': int,
          'num_temporal_layers': int
        }

        encoder_command: Tuple(
            List[str], # The command to run
            List[{
                'filename': str,
                'temporal-layer': str,
                'spatial-layer': str
            }]
        )

        job_temp_dir: str

        encoded_file_dir: str | None
    Returns:
        A tuple containing information about the results and the output
        from the external encoder process
    """

    # Get the command to run the encoder
    (command, encoded_files) = encoder_command

    # Metadata about the file
    clip = job['clip']

    # Start timing the encode time
    start_time = time.time()
    try:
        # Run the encoder process externally
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8')
    except OSError as e:
        return (None, "> %s\n%s" % (" ".join(command), e))
    # Wait for external process to finish
    (output, _) = process.communicate()

    # Measure the encoding time
    actual_encode_ms = (time.time() - start_time) * 1000

    # Get file information
    input_yuv_filesize = os.path.getsize(clip['yuv_file'])
    input_num_frames = int(input_yuv_filesize /
                           (6 * clip['width'] * clip['height'] / 4))
    target_encode_ms = float(input_num_frames) * 1000 / clip['fps']

    if process.returncode != 0:
        return (None, "> %s\n%s" % (" ".join(command), output))

    # Generate file metadata and output file results
    results = [{} for i in range(len(encoded_files))]

    for i in range(len(results)):
        results_dict = results[i]
        results_dict['input-file'] = os.path.basename(clip['input_file'])
        results_dict['input-file-sha1sum'] = clip['sha1sum']
        results_dict['input-total-frames'] = clip['input_total_frames']
        results_dict['frame-offset'] = global_variables.args.frame_offset
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
        results_dict['encode-time-utilization'] = actual_encode_ms / \
            target_encode_ms
        layer = encoded_files[i]

        results_dict['temporal-layer'] = layer['temporal-layer']
        results_dict['spatial-layer'] = layer['spatial-layer']

        # Generate the metrics for the output encoded file
        generate_metrics(results_dict, job, job_temp_dir, layer)

        if encoded_file_dir:
            param = job['qp_value'] if job['param'] == 'qp' else job['target_bitrates_kbps'][-1]
            encoded_file_pattern = "%s-%s-%s-%dsl%dtl-%d-sl%d-tl%d%s" % (os.path.splitext(os.path.basename(clip['input_file']))[
                                                                         0], job['encoder'], job['codec'], job['num_spatial_layers'], job['num_temporal_layers'], param, layer['spatial-layer'], layer['temporal-layer'], os.path.splitext(layer['filename'])[1])
            shutil.move(layer['filename'], os.path.join(
                encoded_file_dir, encoded_file_pattern))
        else:
            os.remove(layer['filename'])

    shutil.rmtree(job_temp_dir)

    # Return the results information along with encoder process' stdout
    return (results, output)


def run_tiny_ssim(results_dict, job, temp_dir, encoded_file):
    # Decode the video to generate a yuv file
    (decoded_file, decoder_framestats) = decode_file(
        job, temp_dir, encoded_file['filename'])
    clip = job['clip']
    temporal_divide = 2 ** (job['num_temporal_layers'] -
                            1 - encoded_file['temporal-layer'])
    temporal_skip = temporal_divide - 1

    ssim_command = ['libvpx/tools/tiny_ssim', clip['yuv_file'], decoded_file, "%dx%d" % (
        results_dict['width'], results_dict['height']), str(temporal_skip)]
    if global_variables.args.enable_framestats:
        # TODO(pbos): Perform SSIM on downscaled .yuv files for spatial layers.
        (fd, metrics_framestats) = tempfile.mkstemp(dir=temp_dir, suffix=".csv")
        os.close(fd)
        ssim_command.append(metrics_framestats)

    # Run the metrics command to generate the metrics
    ssim_results = subprocess.check_output(
        ssim_command, encoding='utf-8').splitlines()

    # Parse the metrics file
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

    # Parse the metrics file
    for line in ssim_results:
        if not line:
            continue
        (metric, value) = line.split(': ')
        if metric in metric_map:
            results_dict[metric] = float(value)
        elif metric == 'Nframes':
            layer_frames = int(value)
            results_dict['frame-count'] = layer_frames

    if global_variables.args.enable_framestats:
        if decoder_framestats:
            add_framestats(results_dict, decoder_framestats, int)
        add_framestats(results_dict, metrics_framestats, float)

    layer_fps = clip['fps'] / temporal_divide
    results_dict['layer-fps'] = layer_fps


def add_framestats(results_dict, framestats_file, statstype):
    """
    Given the framestats csv file, add the results into the results_dictionary
    """
    with open(framestats_file) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            for (metric, value) in list(row.items()):
                metric_key = 'frame-%s' % metric
                if metric_key not in results_dict:
                    results_dict[metric_key] = []
                results_dict[metric_key].append(statstype(value))


def decode_file(job, temp_dir, encoded_file):
    """
    Decode the encoded file and store it in a temporary directory
    """
    (fd, decoded_file) = tempfile.mkstemp(dir=temp_dir, suffix=".yuv")
    os.close(fd)
    (fd, framestats_file) = tempfile.mkstemp(dir=temp_dir, suffix=".csv")
    os.close(fd)
    with open(os.devnull, 'w') as devnull:
        if job['codec'] in ['av1', 'vp8', 'vp9']:
            decoder = AOM_DEC_BIN if job['codec'] == 'av1' else VPX_DEC_BIN
            subprocess.check_call([decoder, '--i420', '--codec=%s' % job['codec'], '-o', decoded_file,
                                   encoded_file, '--framestats=%s' % framestats_file], stdout=devnull, stderr=devnull)
        elif job['codec'] == 'h264':
            subprocess.check_call(
                [H264_DEC_BIN, encoded_file, decoded_file], stdout=devnull, stderr=devnull)
            # TODO(pbos): Generate H264 framestats.
            framestats_file = None
    return (decoded_file, framestats_file)


def generate_metrics(results_dict, job, temp_dir, encoded_file):
    """
    Given an encoded file, decode it and generate some metrics around it.
    Currently, the rtc metrics are generated using the `libvpx/tools/tiny_ssim command`

    Args:
        results_dict: Dictionary containing the metrics results

        job: {
          'encoder': str,
          'codec': str,
          'clip': {
              'file_type': str,
              'input_file': str,
              'height': int,
              'width': int,
              'fps': float,
              'yuv_file': str,
              'sha1sum': str,
              'input_total_frames': float
          },
          'target_bitrate_kbps': List[int],
          'num_spatial_layers': int,
          'num_temporal_layers': int
        }

        encoded_file: {
            'filename': str,
            'spatial-layer': str,
            'temporal-layer': str
        }

        temp_dir: str
    """

    # Decode the video to generate a yuv file
    (decoded_file, decoder_framestats) = decode_file(
        job, temp_dir, encoded_file['filename'])
    clip = job['clip']
    temporal_divide = 2 ** (job['num_temporal_layers'] -
                            1 - encoded_file['temporal-layer'])
    temporal_skip = temporal_divide - 1

    (fd, metrics_framestats) = tempfile.mkstemp(dir=temp_dir, suffix=".csv")
    os.close(fd)

    # Run the metrics command to generate the metrics
    ssim_results = subprocess.check_output(['libvpx/tools/tiny_ssim', clip['yuv_file'], decoded_file, "%dx%d" % (
        results_dict['width'], results_dict['height']), str(temporal_skip), metrics_framestats], encoding='utf-8').splitlines()

    # Parse the metrics file
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

    # Parse the metrics file
    for line in ssim_results:
        if not line:
            continue
        (metric, value) = line.split(': ')
        if metric in metric_map:
            results_dict[metric_map[metric]] = float(value)
        elif metric == 'Nframes':
            layer_frames = int(value)
            results_dict['frame-count'] = layer_frames

    if global_variables.args.enable_framestats:
        if decoder_framestats:
            add_framestats(results_dict, decoder_framestats, int)
        add_framestats(results_dict, metrics_framestats, float)

    # VMAF option if enabled. TODO: Remove this
    if global_variables.args.enable_vmaf:
        results_file = 'sample.json'
        vmaf_results = subprocess.check_output(['vmaf/libvmaf/build/tools/vmafossexec', 'yuv420p', str(results_dict['width']), str(
            results_dict['height']), clip['yuv_file'], decoded_file, 'vmaf/model/vmaf_v0.6.1.pkl', '--log-fmt', 'json', '--log', results_file], encoding='utf-8')
        # vmaf_obj = json.loads(vmaf_results)
        with open('sample.json', 'r') as results_file:
            vmaf_obj = json.load(results_file)

        results_dict['vmaf'] = float(vmaf_obj['aggregate']['VMAF_score'])

        results_dict['frame-vmaf'] = []
        for frame in vmaf_obj['frames']:
            results_dict['frame-vmaf'].append(frame['VMAF_score'])

    layer_fps = clip['fps'] / temporal_divide
    results_dict['layer-fps'] = layer_fps

    spatial_divide = 2 ** (job['num_spatial_layers'] -
                           1 - encoded_file['spatial-layer'])
    results_dict['layer-width'] = results_dict['width'] // spatial_divide
    results_dict['layer-height'] = results_dict['height'] // spatial_divide

    # Calculate and compare target bitrate with actual bitrate used
    # target_bitrate_bps = job['target_bitrates_kbps'][encoded_file['temporal-layer']] * 1000
    bitrate_used_bps = os.path.getsize(
        encoded_file['filename']) * 8 * layer_fps / layer_frames
    # results_dict['target-bitrate-bps'] = target_bitrate_bps
    results_dict['actual-bitrate-bps'] = bitrate_used_bps
    # results_dict['bitrate-utilization'] = float(
    #     bitrate_used_bps) / target_bitrate_bps
    
    if global_variables.args.enable_bitrate:
        target_bitrate_bps = job['target_bitrates_kbps'][encoded_file['temporal-layer']] * 1000
        results_dict['target-bitrate-bps'] = target_bitrate_bps
        # results_dict['actual-bitrate-bps'] = bitrate_used_bps
        results_dict['bitrate-utilization'] = float(
            bitrate_used_bps) / target_bitrate_bps
    else:
        results_dict['target-bitrate-bps'] = bitrate_used_bps
        results_dict['bitrate-config-kbps'] = [bitrate_used_bps // 1000]


def prepare_clips(args, temp_dir):
    """
    Given args object and temporary directory, prepare the clips for the pipeline. 
    We do this by the following steps:

    * Convert all y4m to yuv and store in tmp dir
    * Get sha1sum for the converted yuv files
    * Store the height and width of the clips
    * Store the total number of frames and the size of the file
    """
    clips = args.clips
    non_yuv_clips = [clip for clip in clips if clip['file_type'] != '.yuv']

    # Convert all non yuv clips to yuv using ffmpeg
    if non_yuv_clips:
        print("Converting %d clip%s to yuv..." %
              (len(non_yuv_clips), "" if len(non_yuv_clips) == 1 else "s"))
        for clip in non_yuv_clips:
            (fd, yuv_file) = tempfile.mkstemp(dir=temp_dir,
                                              suffix=".%d_%d.yuv" % (clip['width'], clip['height']))
            os.close(fd)
            with open(os.devnull, 'w') as devnull:
                subprocess.check_call(
                    ['ffmpeg', '-y', '-i', clip['input_file'], yuv_file], stdout=devnull, stderr=devnull)
            clip['yuv_file'] = yuv_file

    # Get sha1sum of file and other metadata
    for clip in clips:
        clip['sha1sum'] = subprocess.check_output(
            ['sha1sum', clip['input_file']], encoding='utf-8').split(' ', 1)[0]
        if 'yuv_file' not in clip:
            clip['yuv_file'] = clip['input_file']
        frame_size = int(6 * clip['width'] * clip['height'] / 4)
        input_yuv_filesize = os.path.getsize(clip['yuv_file'])
        clip['input_total_frames'] = input_yuv_filesize / frame_size
        # Truncate file if necessary.
        if args.frame_offset > 0 or args.num_frames > 0:
            (fd, truncated_filename) = tempfile.mkstemp(
                dir=temp_dir, suffix=".yuv")
            blocksize = 2048 * 1024
            total_filesize = args.num_frames * frame_size
            with os.fdopen(fd, 'wb', blocksize) as truncated_file:
                with open(clip['yuv_file'], 'rb') as original_file:
                    original_file.seek(args.frame_offset * frame_size)
                    while total_filesize > 0:
                        data = original_file.read(
                            blocksize if blocksize < total_filesize else total_filesize)
                        truncated_file.write(data)
                        total_filesize -= blocksize
            clip['yuv_file'] = truncated_filename

        (fd, y4m_file) = tempfile.mkstemp(dir=temp_dir, suffix='.y4m')
        os.close(fd)

        with open(os.devnull, 'w') as devnull:
            subprocess.check_call(
                ['ffmpeg', '-y', '-s', '%dx%d' % (clip['width'], clip['height']), '-r', str(int(clip['fps'] + 0.5)), '-pix_fmt', 'yuv420p', '-i', clip['yuv_file'], y4m_file],
                stdout=devnull,
                stderr=devnull
            )

        clip['y4m_file'] = y4m_file
