"""CLI 入口：加载配置，启动或单次执行监控"""

import argparse
import logging
import sys
from pathlib import Path

from .config import load_config
from .report import print_report, print_metrics_report
from .scheduler import MonitorScheduler
from .storage import ResultStorage

DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "api_monitor.yaml"
DEFAULT_DB = Path(__file__).parent.parent / "data" / "api_monitor.db"


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def main():
    parser = argparse.ArgumentParser(description="API 健康监控工具")
    parser.add_argument(
        "-c", "--config",
        default=str(DEFAULT_CONFIG),
        help=f"配置文件路径 (默认: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "-d", "--db",
        default=str(DEFAULT_DB),
        help=f"数据库路径 (默认: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="单次检查模式（不启动定时调度）",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="查看历史检查报告（不执行新检查）",
    )
    parser.add_argument(
        "--metrics",
        action="store_true",
        help="查看今日详细指标（P95/P99 延迟、端点可用率、连续失败）",
    )
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    logger.info(f"加载配置: {config.task_name}, {len(config.endpoints)} 个端点")
    for ep in config.endpoints:
        logger.info(f"  - {ep.name}: {ep.method} {ep.url}")

    scheduler = MonitorScheduler(config, db_path=args.db)

    if args.report:
        storage = ResultStorage(args.db)
        print_report(storage, config.task_name)
        storage.close()
    elif args.metrics:
        storage = ResultStorage(args.db)
        print_metrics_report(storage, config.task_name)
        storage.close()
    elif args.once:
        scheduler.run_once()
        scheduler.stop()
    else:
        scheduler.start()
