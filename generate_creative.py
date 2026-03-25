"""Batch script to generate marketing creative for Brewers POC.

Usage:
    python generate_creative.py --segment "Die-hard" --game "2026-02-21" --use-llm
    python generate_creative.py --limit 10 --use-llm
    python generate_creative.py --limit 20 --use-llm --workers 5
    python generate_creative.py --use-llm
"""

import argparse
import logging
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from creative_engine import (
    SEGMENT_LABELS,
    build_ollama_service,
    generate_for_game_segment,
    load_data,
    save_results,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Generate Brewers marketing creative")
    parser.add_argument("--segment", choices=list(SEGMENT_LABELS.keys()), help="Segment to generate for")
    parser.add_argument("--game", help="Game date in YYYY-MM-DD format")
    parser.add_argument("--use-llm", action="store_true", help="Generate LLM creative")
    parser.add_argument("--limit", type=int, default=None, help="Max random combinations to generate (default: all)")
    parser.add_argument("--workers", type=int, default=3, help="Number of parallel workers for batch generation")
    args = parser.parse_args()

    logger.info("Loading data...")
    schedule_df, fan_df = load_data()

    ollama_service = None
    if args.use_llm:
        ollama_service = build_ollama_service()
        if not ollama_service.is_running():
            logger.error("Ollama service is not running")
            sys.exit(1)
        if not ollama_service.model_exists():
            logger.error("Configured Ollama model is not available")
            sys.exit(1)

    if args.segment and args.game:
        logger.info(f"Generating for {args.segment} - {args.game}")
        results = generate_for_game_segment(
            schedule_df,
            fan_df,
            args.game,
            args.segment,
            use_llm=args.use_llm,
            ollama_service=ollama_service,
        )
        if "error" in results:
            logger.error(results["error"])
            sys.exit(1)
        save_results(results, args.game, args.segment)
        logger.info("Generation complete!")
        return

    game_dates = [value for value in schedule_df["GAME_DATE_DISPLAY"].unique() if pd.notna(value)]
    combinations = [(game_date, segment) for game_date in game_dates for segment in SEGMENT_LABELS]
    sampled = random.sample(combinations, min(args.limit, len(combinations))) if args.limit else combinations
    logger.info(f"Generating {len(sampled)} combinations with {args.workers} workers...")

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                generate_for_game_segment,
                schedule_df,
                fan_df,
                game_date,
                segment,
                args.use_llm,
                ollama_service,
            ): (game_date, segment)
            for game_date, segment in sampled
        }
        for future in as_completed(futures):
            game_date, segment = futures[future]
            try:
                results = future.result()
                if "error" in results:
                    logger.warning(f"Skipped {segment} - {game_date}: {results['error']}")
                    continue
                save_results(results, game_date, segment)
                logger.info(f"Saved {segment} - {game_date}")
            except Exception as exc:
                logger.exception(f"Failed {segment} - {game_date}: {exc}")


if __name__ == "__main__":
    main()
