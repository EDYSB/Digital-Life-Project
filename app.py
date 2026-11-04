#!/usr/bin/env python3
"""数字生命初级 启动器。

  python app.py                启动 Web 界面（默认 8017 端口）
  python app.py --port 8080
  python app.py serve --no-browser
  python app.py scan --eeg samples/eeg_meditation.csv --dna samples/dna_sensitive.fasta
"""

import sys

from suoling.cli import main

if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv:
        argv = ["serve"]
    main(argv)
