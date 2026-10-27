#!/usr/bin/env python3
import sys
from .console import build_arg_parser, run_interactive_console

if __name__ == "__main__":
    parser = build_arg_parser()
    sys.exit(run_interactive_console(parser.parse_args()))
