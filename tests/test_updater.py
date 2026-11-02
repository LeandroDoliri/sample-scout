import io
import json

import pytest

from sample_scout import clap, updater

APP = {"tag_name": "v0.2.0", "draft": False, "prerelease": False, "body": "notas",
       "html_url": "https://github.com/x/y/releases/tag/v0.2.0",
       "assets": [{"name": "SampleScout-update-0.2.0.zip", "browser_download_url": "u"}]}
OLD = dict(APP, tag_name="v0.1.0", assets=[])
MODELS = {"tag_name": clap.MODEL_TAG, "draft": False, "prerelease": True,
          "assets": [{"name": clap.MODEL_ZIP}]}


@pytest.fixture
def api(monkeypatch):
    responses = {}

    def fake_get(url, timeout):
        for suffix, body in responses.items():
            if url.endswith(suffix):
                return io.BytesIO(json.dumps(body).encode())
        raise OSError("sin red")

    monkeypatch.setattr(updater, "_http_get", fake_get)
    return responses


def test_toma_el_release_de_la_app(api):
    api["/releases/latest"] = APP
    release = updater.latest_release()
    assert release["version"] == "0.2.0" and release["asset"]["name"].endswith("0.2.0.zip")


def test_un_release_de_modelos_nunca_cuenta_como_version(api):
    """Si el release del modelo quedara como "Latest" por error, el updater busca el de la
    app en la lista en vez de quedarse sin actualizaciones (o tomar el tag del modelo)."""
    api["/releases/latest"] = dict(MODELS, prerelease=False)
    api["/releases?per_page=30"] = [MODELS, OLD, APP]
    assert updater.latest_release()["version"] == "0.2.0"
    api["/releases?per_page=30"] = [MODELS]
    assert updater.latest_release() is None


def test_prereleases_y_borradores_no_cuentan(api):
    assert updater._app_version(MODELS) is None
    assert updater._app_version(dict(APP, prerelease=True)) is None
    assert updater._app_version(dict(APP, draft=True)) is None
    assert updater._app_version(APP) == "0.2.0"


def test_sin_red(api):
    assert updater.latest_release() is None
