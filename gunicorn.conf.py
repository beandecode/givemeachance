"""Gunicorn settings (loaded automatically from the working directory)."""

import os

bind = "0.0.0.0:5001"
# Several workers are safe: SQLite runs in WAL mode and orphaned tasks are recovered by heartbeat.
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "4"))
# Provider calls run in background tasks; synchronous legacy routes may still take a while.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
accesslog = "-"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(M)sms'
if os.getenv("LOG_FORMAT", "").lower() == "json":
    # Gunicorn's own messages (worker boot, timeouts) use the same JSON lines as the app. Start from gunicorn's
    # defaults: this dict is merged over them key by key, so a partial one would drop handlers the root logger needs.
    import copy

    from gunicorn.glogging import CONFIG_DEFAULTS

    logconfig_dict = copy.deepcopy(CONFIG_DEFAULTS)
    logconfig_dict["formatters"]["json"] = {"()": "core.logging_setup.JsonFormatter"}
    logconfig_dict["handlers"]["error_console"]["formatter"] = "json"
    logconfig_dict["root"]["handlers"] = []  # the app installs its own root handler (core.logging_setup)
    logconfig_dict["loggers"]["gunicorn.error"]["propagate"] = False
    logconfig_dict["loggers"]["gunicorn.access"]["propagate"] = False
