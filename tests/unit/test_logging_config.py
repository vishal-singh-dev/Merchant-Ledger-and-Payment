import logging

from app.logging_config import configure_logging


def test_configure_logging_writes_to_file(tmp_path):
    log_file = tmp_path / "app.log"
    configure_logging(level="INFO", log_to_file=True, log_file_path=str(log_file))

    logger = logging.getLogger("test_logger")
    logger.info("file logging works")

    logging.shutdown()
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "file logging works" in content
