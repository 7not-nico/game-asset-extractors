#!/bin/bash
set -e
python3 /tmp/opencode/extract_9d.py > /tmp/opencode/extract_9d.log 2>&1
python3 /tmp/opencode/extract_9d_audio.py > /tmp/opencode/extract_9d_audio.log 2>&1
