# =========================================================
# logger_config.py
# Centralized Logging Configuration
# Used by: backtester.py, incremental_collector.py, feature_engine.py
# =========================================================

import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
import sys

# =========================================================
# LOGGER SETUP
# =========================================================

BASE_DIR = Path(__file__).parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Create logger
logger = logging.getLogger("stock_pipeline")
logger.setLevel(logging.DEBUG)

# Prevent duplicate handlers if this module is imported multiple times
if not logger.handlers:
    # -------------------------
    # FILE HANDLER (All levels)
    # -------------------------
    log_file = LOGS_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    
    # -------------------------
    # CONSOLE HANDLER (INFO and above)
    # -------------------------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # -------------------------
    # ROTATING FILE HANDLER (Keep last 5 files)
    # -------------------------
    rotating_file = LOGS_DIR / "pipeline.log"
    rotating_handler = logging.handlers.RotatingFileHandler(
        rotating_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5
    )
    rotating_handler.setLevel(logging.DEBUG)
    
    # -------------------------
    # FORMATTER
    # -------------------------
    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    rotating_handler.setFormatter(formatter)
    
    # -------------------------
    # ADD HANDLERS TO LOGGER
    # -------------------------
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.addHandler(rotating_handler)

# =========================================================
# CONVENIENCE FUNCTIONS
# =========================================================

def log_info(message: str):
    """Log info level message"""
    logger.info(message)

def log_debug(message: str):
    """Log debug level message"""
    logger.debug(message)

def log_warning(message: str):
    """Log warning level message"""
    logger.warning(message)

def log_error(message: str):
    """Log error level message"""
    logger.error(message)

def log_critical(message: str):
    """Log critical level message"""
    logger.critical(message)

def log_exception(exception: Exception, context: str = ""):
    """Log exception with context"""
    if context:
        logger.exception(f"{context}: {str(exception)}")
    else:
        logger.exception(str(exception))

def get_logger():
    """Get the global logger instance"""
    return logger

# =========================================================
# SECTION DIVIDERS (for readability)
# =========================================================

def log_section(title: str, char: str = "=", width: int = 70):
    """Log a section divider"""
    divider = char * width
    logger.info(divider)
    logger.info(f"{title.center(width)}")
    logger.info(divider)

def log_subsection(title: str, char: str = "-", width: int = 70):
    """Log a subsection divider"""
    logger.info(f"{char * width}")
    logger.info(f"{title}")
    logger.info(f"{char * width}")

# =========================================================
# METRICS LOGGING
# =========================================================

def log_metrics(metrics: dict, title: str = "Metrics"):
    """Log a dictionary of metrics"""
    logger.info(f"\n{title}:")
    for key, value in metrics.items():
        logger.info(f"  {key:.<40} {value}")

# =========================================================
# PIPELINE START/END
# =========================================================

def log_pipeline_start(pipeline_name: str, **kwargs):
    """Log pipeline start with parameters"""
    log_section(f"START: {pipeline_name}", char="=", width=70)
    if kwargs:
        for key, value in kwargs.items():
            logger.info(f"  {key}: {value}")

def log_pipeline_end(pipeline_name: str, status: str = "SUCCESS", **kwargs):
    """Log pipeline end with summary"""
    logger.info(f"\n{pipeline_name} Status: {status}")
    if kwargs:
        for key, value in kwargs.items():
            logger.info(f"  {key}: {value}")
    log_section(f"END: {pipeline_name}", char="=", width=70)
