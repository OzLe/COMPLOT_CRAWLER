#!/usr/bin/env python3
"""
Complot Building Permit Crawler - Entry Point

A unified crawler for Israeli municipality building permit systems.

Usage:
    python main.py <city_name_or_url> [options]

Examples:
    python main.py batyam
    python main.py ofaqim --streets-only
    python main.py --list-cities

For more options:
    python main.py --help
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.complot_crawler import main

if __name__ == "__main__":
    main()
