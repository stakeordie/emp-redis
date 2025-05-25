#!/usr/bin/env python3

"""Checks and sets default values for config.json before starting the container."""

import os
import re
import json
import os.path
import sys
# [2025-05-25T18:40:00-04:00] Fixed imports for type annotations
from typing import Dict, Any, cast

DEFAULT_FILEPATH = '/data/config/auto/config.json'

DEFAULT_OUTDIRS = {
  "outdir_samples": "",
  "outdir_txt2img_samples": "/output/txt2img",
  "outdir_img2img_samples": "/output/img2img",
  "outdir_extras_samples": "/output/extras",
  "outdir_grids": "",
  "outdir_txt2img_grids": "/output/txt2img-grids",
  "outdir_img2img_grids": "/output/img2img-grids",
  "outdir_save": "/output/saved",
  "outdir_init_images": "/output/init-images",
  "sd_checkpoints_limit": 4,
  "sd_checkpoints_keep_in_cpu": bool(0),
}
RE_VALID_OUTDIR = re.compile(r"(^/output(/\.?[\w\-\_]+)+/?$)|(^\s?$)")

DEFAULT_OTHER = {
  "font": "DejaVuSans.ttf",
}

def dict_to_json_file(target_file: str, data: Dict[Any, Any]):
  """Write dictionary to specified json file"""

  with open(target_file, 'w') as f:
    json.dump(data, f)

def json_file_to_dict(config_file: str) -> Dict[Any, Any] | None:
  """Loads JSON file to dictionary"""
  # [2025-05-25T18:25:00-04:00] Fixed indentation and return type
  if os.path.exists(config_file):
    with open(config_file, 'r') as f:
      # Explicitly cast the return value to Dict[Any, Any] to match the declared return type
      return cast(Dict[Any, Any], json.load(f))
  else:
      return None

def replace_if_invalid(value: str, replacement: str, pattern: str|re.Pattern[str]) -> str:
  """Returns original value if valid, fallback value if invalid"""
  # [2025-05-25T18:25:00-04:00] Added type checking to ensure arguments are strings
  if not isinstance(value, str):
    # Convert value to string if it's not already
    value_str = str(value)
  else:
    value_str = value
    
  if not isinstance(replacement, str):
    # Convert replacement to string if it's not already
    replacement_str = str(replacement)
  else:
    replacement_str = replacement

  if re.match(pattern, value_str):
    return value_str
  else:
    return replacement_str

def check_and_replace_config(config_file: str, target_file: str | None = None):
  """Checks given file for invalid values. Replaces those with fallback values (default: overwrites file)."""

  # Get current user config, or empty if file does not exists
  data = json_file_to_dict(config_file) or {}

  # Check and fix output directories
  # [2025-05-25T18:35:00-04:00] Fixed type error with replacement argument
  for k, def_val in DEFAULT_OUTDIRS.items():
    if k not in data:
      data[k] = def_val
    else:
      # Ensure def_val is a string before passing it to replace_if_invalid
      def_val_str = str(def_val) if not isinstance(def_val, str) else def_val
      data[k] = replace_if_invalid(value=data[k], replacement=def_val_str, pattern=RE_VALID_OUTDIR)

  # Check and fix other default settings
  # [2025-05-25T18:45:00-04:00] Fixed type error with replacement argument for DEFAULT_OTHER
  for k, def_val in DEFAULT_OTHER.items():
    if k not in data:
      data[k] = def_val
    else:
      # Apply the same type checking for DEFAULT_OTHER items
      def_val_str = str(def_val) if not isinstance(def_val, str) else def_val
      data[k] = replace_if_invalid(value=data[k], replacement=def_val_str, pattern=r'.*')

  # Write results to file
  dict_to_json_file(target_file or config_file, data)

if __name__ == '__main__':
  if len(sys.argv) > 1:
    check_and_replace_config(*sys.argv[1:])
  else:
    check_and_replace_config(DEFAULT_FILEPATH)

