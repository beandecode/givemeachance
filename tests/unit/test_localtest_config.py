from pathlib import Path

import yaml


def test_pytest_settings_remain_mock_only():
    project_root = Path(__file__).resolve().parents[2]
    raw = yaml.safe_load((project_root / "config" / "settings.test.yaml").read_text(encoding="utf-8"))

    assert raw["data_sources"]["primary"].startswith("mock_")
    assert raw["llm"]["provider"].startswith("mock_")


def test_localtest_settings_use_live_providers_and_localtest_paths():
    project_root = Path(__file__).resolve().parents[2]
    raw = yaml.safe_load((project_root / "config" / "settings.localtest.yaml").read_text(encoding="utf-8"))

    assert raw["data_sources"]["primary"] == "adzuna_api"
    assert raw["llm"]["provider"] == "gemini_api"
    assert raw["app"]["db_path"].startswith("output_localtest/")
    assert raw["app"]["log_path"].startswith("logs_localtest/")
    # Adzuna allows 250 calls a day; the owner wants localtest to stay under half of that.
    assert int(raw["api_limits"]["adzuna_daily_limit"]) <= 125


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader that tolerates Compose-specific tags such as `!reset`."""


_ComposeLoader.add_multi_constructor("!", lambda loader, suffix, node: None)


def test_compose_files_do_not_hardcode_secrets_or_expose_localtest():
    project_root = Path(__file__).resolve().parents[2]
    secret_keys = ("FLASK_SECRET_KEY", "ADMIN_BOOTSTRAP_PASSWORD", "CLOUDFLARE_TUNNEL_TOKEN")
    for compose_file in project_root.glob("docker-compose*.yml"):
        raw = yaml.load(compose_file.read_text(encoding="utf-8"), Loader=_ComposeLoader)
        for service in (raw.get("services") or {}).values():
            environment = service.get("environment") or {}
            for key in secret_keys:
                value = str(environment.get(key, "${}"))
                assert value.startswith("${"), f"{compose_file.name}: {key} must come from .env"

    localtest = yaml.safe_load((project_root / "docker-compose.localtest.yml").read_text(encoding="utf-8"))
    for port in localtest["services"]["app_localtest"]["ports"]:
        # Loopback by default; a LAN IP may be opted into through LOCALTEST_BIND_ADDR in the gitignored .env.
        assert str(port).startswith(("127.0.0.1:", "${LOCALTEST_BIND_ADDR:-127.0.0.1}:")), (
            "localtest must default to localhost"
        )
        assert "0.0.0.0" not in str(port)
