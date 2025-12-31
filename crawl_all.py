#!/usr/bin/env python3
"""
Wrapper script to crawl all configured cities.

Usage:
    python crawl_all.py                    # Crawl all cities sequentially
    python crawl_all.py --workers 4        # Use 4 workers per city
    python crawl_all.py --parallel 2       # Run 2 cities in parallel
    python crawl_all.py --cities modiin,batyam  # Only specific cities
    python crawl_all.py --exclude batyam   # Exclude specific cities
    python crawl_all.py --dry-run          # Show what would be crawled
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config import CITIES, list_cities


def crawl_city(city_key: str, workers: int = 1, force: bool = False,
               skip_details: bool = False, verbose: bool = False) -> dict:
    """
    Crawl a single city and return results.

    Returns dict with: city, status, duration, streets, records, details, error
    """
    start_time = time.time()
    result = {
        "city": city_key,
        "status": "pending",
        "duration": 0,
        "streets": 0,
        "records": 0,
        "details": 0,
        "error": None
    }

    # Build command
    cmd = [sys.executable, "main.py", city_key, f"--workers={workers}"]
    if force:
        cmd.append("--force")
    if skip_details:
        cmd.append("--skip-details")
    if verbose:
        cmd.append("--verbose")

    try:
        print(f"\n{'='*60}")
        print(f"STARTING: {city_key}")
        print(f"Command: {' '.join(cmd)}")
        print(f"{'='*60}")

        # Run the crawler
        process = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=False,  # Show output in real-time
            text=True
        )

        if process.returncode == 0:
            result["status"] = "success"

            # Read output files to get counts
            data_dir = project_root / "data" / city_key

            streets_file = data_dir / "streets.json"
            if streets_file.exists():
                with open(streets_file) as f:
                    data = json.load(f)
                    result["streets"] = data.get("total_streets", 0)

            records_file = data_dir / "building_records.json"
            if records_file.exists():
                with open(records_file) as f:
                    data = json.load(f)
                    result["records"] = data.get("total_records", 0)

            details_file = data_dir / "building_details.json"
            if details_file.exists():
                with open(details_file) as f:
                    data = json.load(f)
                    result["details"] = data.get("total_records", 0)
        else:
            result["status"] = "failed"
            result["error"] = f"Exit code: {process.returncode}"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    result["duration"] = time.time() - start_time
    return result


def crawl_city_wrapper(args: tuple) -> dict:
    """Wrapper for ProcessPoolExecutor"""
    city_key, workers, force, skip_details, verbose = args
    return crawl_city(city_key, workers, force, skip_details, verbose)


def print_summary(results: list[dict], total_duration: float):
    """Print summary of all crawl results"""
    print("\n")
    print("#" * 70)
    print("CRAWL SUMMARY")
    print("#" * 70)

    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = sum(1 for r in results if r["status"] != "success")

    total_streets = sum(r["streets"] for r in results)
    total_records = sum(r["records"] for r in results)
    total_details = sum(r["details"] for r in results)

    print(f"\nTotal cities: {len(results)} ({success_count} success, {failed_count} failed)")
    print(f"Total duration: {total_duration/60:.1f} minutes")
    print(f"\nTotals across all cities:")
    print(f"  Streets:  {total_streets:,}")
    print(f"  Records:  {total_records:,}")
    print(f"  Details:  {total_details:,}")

    print(f"\n{'City':<15} {'Status':<10} {'Duration':<12} {'Streets':<10} {'Records':<10} {'Details':<10}")
    print("-" * 70)

    for r in sorted(results, key=lambda x: x["city"]):
        duration_str = f"{r['duration']/60:.1f} min"
        status_icon = "✓" if r["status"] == "success" else "✗"
        print(f"{r['city']:<15} {status_icon} {r['status']:<8} {duration_str:<12} {r['streets']:<10} {r['records']:<10} {r['details']:<10}")
        if r["error"]:
            print(f"  └─ Error: {r['error']}")

    print("-" * 70)

    # Save summary to file
    summary_file = project_root / "data" / "crawl_summary.json"
    summary = {
        "crawled_at": datetime.now().isoformat(),
        "total_duration_seconds": total_duration,
        "total_cities": len(results),
        "success_count": success_count,
        "failed_count": failed_count,
        "total_streets": total_streets,
        "total_records": total_records,
        "total_details": total_details,
        "results": results
    }

    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nSummary saved to: {summary_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Crawl all configured cities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawl_all.py                         # Crawl all cities
  python crawl_all.py --workers 4             # Use 4 workers per city
  python crawl_all.py --parallel 2            # Run 2 cities simultaneously
  python crawl_all.py --cities modiin,batyam  # Only specific cities
  python crawl_all.py --exclude batyam        # Exclude batyam
  python crawl_all.py --dry-run               # Preview without crawling
  python crawl_all.py --force                 # Force re-crawl all
  python crawl_all.py --skip-details          # Skip building details (faster)
        """
    )

    parser.add_argument("--workers", type=int, default=1,
                        help="Number of workers per city (default: 1)")
    parser.add_argument("--parallel", type=int, default=1,
                        help="Number of cities to crawl in parallel (default: 1)")
    parser.add_argument("--cities", type=str, default=None,
                        help="Comma-separated list of cities to crawl")
    parser.add_argument("--exclude", type=str, default=None,
                        help="Comma-separated list of cities to exclude")
    parser.add_argument("--force", action="store_true",
                        help="Force re-crawl even if cached")
    parser.add_argument("--skip-details", action="store_true",
                        help="Skip fetching building details")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be crawled without running")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose logging")
    parser.add_argument("--list", action="store_true",
                        help="List all available cities")

    args = parser.parse_args()

    # List cities and exit
    if args.list:
        print("\nAvailable cities:")
        print("-" * 50)
        for city in list_cities():
            print(f"  {city['key']:<15} {city['name']}")
        print("-" * 50)
        return

    # Determine which cities to crawl
    all_cities = list(CITIES.keys())

    if args.cities:
        cities_to_crawl = [c.strip() for c in args.cities.split(",")]
        # Validate cities
        invalid = [c for c in cities_to_crawl if c not in all_cities]
        if invalid:
            print(f"Error: Unknown cities: {', '.join(invalid)}")
            print(f"Available: {', '.join(all_cities)}")
            return
    else:
        cities_to_crawl = all_cities

    # Apply exclusions
    if args.exclude:
        exclude_list = [c.strip() for c in args.exclude.split(",")]
        cities_to_crawl = [c for c in cities_to_crawl if c not in exclude_list]

    if not cities_to_crawl:
        print("No cities to crawl!")
        return

    # Dry run mode
    if args.dry_run:
        print("\n[DRY RUN] Would crawl the following cities:")
        print("-" * 50)
        for city in cities_to_crawl:
            config = CITIES[city]
            print(f"  {city:<15} (streets: {config.street_range[0]}-{config.street_range[1]}, api: {config.api_type})")
        print("-" * 50)
        print(f"\nTotal: {len(cities_to_crawl)} cities")
        print(f"Workers per city: {args.workers}")
        print(f"Parallel cities: {args.parallel}")
        if args.force:
            print("Mode: Force re-crawl")
        if args.skip_details:
            print("Mode: Skip details")
        return

    # Start crawling
    print("#" * 70)
    print("COMPLOT CRAWLER - ALL CITIES")
    print("#" * 70)
    print(f"Cities to crawl: {len(cities_to_crawl)}")
    print(f"Cities: {', '.join(cities_to_crawl)}")
    print(f"Workers per city: {args.workers}")
    print(f"Parallel cities: {args.parallel}")
    print(f"Force: {args.force}")
    print(f"Skip details: {args.skip_details}")
    print("#" * 70)

    start_time = time.time()
    results = []

    if args.parallel > 1:
        # Parallel execution across cities
        print(f"\nRunning {args.parallel} cities in parallel...")

        # Prepare arguments for each city
        crawl_args = [
            (city, args.workers, args.force, args.skip_details, args.verbose)
            for city in cities_to_crawl
        ]

        with ProcessPoolExecutor(max_workers=args.parallel) as executor:
            futures = {executor.submit(crawl_city_wrapper, arg): arg[0] for arg in crawl_args}

            for future in as_completed(futures):
                city = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    print(f"\n[COMPLETED] {city}: {result['status']} ({result['duration']/60:.1f} min)")
                except Exception as e:
                    results.append({
                        "city": city,
                        "status": "error",
                        "duration": 0,
                        "streets": 0,
                        "records": 0,
                        "details": 0,
                        "error": str(e)
                    })
    else:
        # Sequential execution
        for i, city in enumerate(cities_to_crawl):
            print(f"\n[{i+1}/{len(cities_to_crawl)}] Processing {city}...")
            result = crawl_city(city, args.workers, args.force, args.skip_details, args.verbose)
            results.append(result)
            print(f"[COMPLETED] {city}: {result['status']} ({result['duration']/60:.1f} min)")

    total_duration = time.time() - start_time
    print_summary(results, total_duration)


if __name__ == "__main__":
    main()
