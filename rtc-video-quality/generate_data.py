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

from encoder_commands import *
from helper_script import *
import global_variables
from binary_vars import *

libvpx_threads = 4

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
      print("WARNING: '%s' not in PATH (using --use-system-path), falling back on locally-compiled binary." % os.path.basename(binary))
    binary_absolute_paths[binary] = target
    return target

  sys.exit("ERROR: '%s' missing, did you run the corresponding setup script?" % (os.path.basename(binary) if use_system_path else target))

yuv_clip_pattern = re.compile(r"^(.*[\._](\d+)_(\d+).yuv):(\d+)$")
def clip_arg(clip):
  (file_root, file_ext) = os.path.splitext(clip)
  if file_ext != '.yuv':
    width = int(subprocess.check_output(["mediainfo", "--Inform=Video;%Width%", clip], encoding='utf-8'))
    height = int(subprocess.check_output(["mediainfo", "--Inform=Video;%Height%", clip], encoding='utf-8'))
    fps = float(subprocess.check_output(["mediainfo", "--Inform=Video;%FrameRate%", clip], encoding='utf-8'))
    return {'input_file': clip, 'height': height, 'width': width, 'fps': fps, 'file_type': file_ext}

  # Make sure YUV files are correctly formatted + look readable before actually
  # running the script on them.
  clip_match = yuv_clip_pattern.match(clip)
  if not clip_match:
    raise argparse.ArgumentTypeError("Argument '%s' doesn't match input format.\n" % clip)
  input_file = clip_match.group(1)
  if not os.path.isfile(input_file) or not os.access(input_file, os.R_OK):
    raise argparse.ArgumentTypeError("'%s' is either not a file or cannot be opened for reading.\n" % input_file)
  return {'input_file': clip_match.group(1), 'width': int(clip_match.group(2)), 'height': int(clip_match.group(3)), 'fps' : float(clip_match.group(4)), 'file_type': 'yuv'}


def encoder_pairs(string):
  pair_pattern = re.compile(r"^([\w\-]+):(\w+)$")
  encoders = []
  for pair in string.split(','):
    pair_match = pair_pattern.match(pair)
    if not pair_match:
      raise argparse.ArgumentTypeError("Argument '%s' of '%s' doesn't match input format.\n" % (pair, string))
    if not get_encoder_command(pair_match.group(1)):
      raise argparse.ArgumentTypeError("Unknown encoder: '%s' in pair '%s'\n" % (pair_match.group(1), pair))
    encoders.append((pair_match.group(1), pair_match.group(2)))
  return encoders


def writable_dir(directory):
  if not os.path.isdir(directory) or not os.access(directory, os.W_OK):
    raise argparse.ArgumentTypeError("'%s' is either not a directory or cannot be opened for writing.\n" % directory)
  return directory


def positive_int(num):
  num_int = int(num)
  if num_int <= 0:
    raise argparse.ArgumentTypeError("'%d' is not a positive integer.\n" % num)
  return num_int


parser = argparse.ArgumentParser(description='Generate graph data for video-quality comparison.')
parser.add_argument('clips', nargs='+', metavar='clip_WIDTH_HEIGHT.yuv:FPS|clip.y4m', type=clip_arg)
parser.add_argument('--dump-commands', action='store_true')
parser.add_argument('--enable-vmaf', action='store_true')
parser.add_argument('--enable-bitrate', action='store_true')
parser.add_argument('--enable-framestats', action='store_true')
parser.add_argument('--encoded-file-dir', default=None, type=writable_dir)
parser.add_argument('--encoders', required=True, metavar='encoder:codec,encoder:codec...', type=encoder_pairs)
parser.add_argument('--frame-offset', default=0, type=positive_int)
parser.add_argument('--num-frames', default=-1, type=positive_int)
# TODO(pbos): Add support for multiple spatial layers.
parser.add_argument('--num-spatial-layers', type=int, default=1, choices=[1])
parser.add_argument('--num-temporal-layers', type=int, default=1, choices=[1,2,3])
parser.add_argument('--out', required=True, metavar='output.txt', type=argparse.FileType('w'))
parser.add_argument('--use-system-path', action='store_true')
parser.add_argument('--workers', type=int, default=multiprocessing.cpu_count())


def generate_jobs(args, temp_dir):
  jobs = []
  for clip in args.clips:
    bitrates = find_bitrates(clip['width'], clip['height'])
    qp_values = find_qp(clip['width'], clip['height'])
    if args.enable_bitrate:
        params = bitrates
    else:
        params = qp_values
    for param in params:
      for (encoder, codec) in args.encoders:
        job = {
          'param': 'bitrate' if args.enable_bitrate else 'qp',  
          'encoder': encoder,
          'codec': codec,
          'clip': clip,
          'qp_value': param if not args.enable_bitrate else -1,
          'target_bitrates_kbps': split_temporal_bitrates_kbps(100, args.num_temporal_layers) if args.enable_bitrate else [],
          'num_spatial_layers': args.num_spatial_layers,
          'num_temporal_layers': args.num_temporal_layers,
        }
        job_temp_dir = tempfile.mkdtemp(dir=temp_dir)
        encoder_command_function = get_encoder_command(job['encoder'])
        (command, encoded_files) = encoder_command_function(job, job_temp_dir)
        command[0] = find_absolute_path(args.use_system_path, command[0])
        jobs.append((job, (command, encoded_files), job_temp_dir))
  return jobs

def start_daemon(func):
  t = threading.Thread(target=func)
  t.daemon = True
  t.start()
  return t

def job_to_string(job):
    return "%s:%s %dsl%dtl %s %s" % (job['encoder'], job['codec'], job['num_spatial_layers'], job['num_temporal_layers'], ":".join(str(i) for i in job['target_bitrates_kbps']), os.path.basename(job['clip']['input_file']))

def worker():
  # global args
  # global jobs
  # global current_job
  # global has_errored
  # global total_jobs
  pp = pprint.PrettyPrinter(indent=2)
  while True:
    with thread_lock:
      if not global_variables.jobs:
        return
      (job, command, job_temp_dir) = global_variables.jobs.pop()

    (results, error) = run_command(job, command, job_temp_dir, global_variables.args.encoded_file_dir)

    job_str = job_to_string(job)

    with thread_lock:
      global_variables.current_job += 1
      run_ok = results is not None
      print("[%d/%d] %s (%s)" % (global_variables.current_job, global_variables.total_jobs, job_str, "OK" if run_ok else "ERROR"))
      if not run_ok:
        global_variables.has_errored = True
        print(error)
      else:
        for result in results:
          global_variables.args.out.write(pp.pformat(result))
          global_variables.args.out.write(',\n')
        global_variables.args.out.flush()


thread_lock = threading.Lock()

def main():
  # global args
  # global jobs
  # global total_jobs
  # global current_job
  # global has_errored

  temp_dir = tempfile.mkdtemp()

  global_variables.args = parser.parse_args()
  prepare_clips(global_variables.args, temp_dir)
  global_variables.jobs = generate_jobs(global_variables.args, temp_dir)
  global_variables.total_jobs = len(global_variables.jobs)
  global_variables.current_job = 0
  global_variables.has_errored = False

  if global_variables.args.dump_commands:
    for (job, (command, encoded_files), job_temp_dir) in global_variables.jobs:
      global_variables.current_job += 1
      print("[%d/%d] %s" % (global_variables.current_job, global_variables.total_jobs, job_to_string(job)))
      print("> %s" % " ".join(command))
      print()

    shutil.rmtree(temp_dir)
    return 0

  # Make sure commands for quality metrics are present.
  find_absolute_path(False, TINY_SSIM_BIN)
  for (encoder, codec) in global_variables.args.encoders:
    if codec in ['vp8', 'vp9']:
      find_absolute_path(False, VPX_DEC_BIN)
    elif codec == 'av1':
      find_absolute_path(False, AOM_DEC_BIN)
    elif codec == 'h264':
      find_absolute_path(False, H264_DEC_BIN)

    if 'svt' in encoder:
      find_absolute_path(False, SVT_ENC_BIN)
    if 'rav1e' in encoder:
      find_absolute_path(False, RAV1E_ENC_BIN)

  if global_variables.args.enable_vmaf:
    find_absolute_path(False, VMAF_BIN)

  print("[0/%d] Running jobs..." % global_variables.total_jobs)

  global_variables.args.out.write('[')

  workers = [start_daemon(worker) for i in range(global_variables.args.workers)]
  [t.join() for t in workers]

  global_variables.args.out.write(']\n')

  shutil.rmtree(temp_dir)
  return 1 if global_variables.has_errored else 0

if __name__ == '__main__':
  sys.exit(main())
