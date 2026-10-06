"""config/settings/prod.py carrega com o .env de producao e aplica cada opcao.

Roda num subprocesso: o pytest ja esta com o settings de dev carregado.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
BASE = {"DJANGO_SECRET_KEY": "x" * 50, "REDIS_URL": "redis://redis:6379/0",
        "POSTGRES_DB": "starhub", "POSTGRES_USER": "starhub", "POSTGRES_PASSWORD": "segredo",
        "POSTGRES_HOST": "banco.interno", "DJANGO_ALLOWED_HOSTS": "hub.exemplo.com"}
LER = """
import json, django
from django.conf import settings as s
django.setup()
print(json.dumps({
    "debug": s.DEBUG, "middleware": s.MIDDLEWARE, "apps": s.INSTALLED_APPS,
    "cors": getattr(s, "CORS_ALLOWED_ORIGINS", None),
    "cors_url": getattr(s, "CORS_URLS_REGEX", None),
    "ssl": s.SECURE_SSL_REDIRECT, "hsts": s.SECURE_HSTS_SECONDS, "media": s.SERVIR_MEDIA,
    "banco": {k: s.DATABASES["default"][k] for k in ("HOST", "NAME", "OPTIONS", "CONN_MAX_AGE")},
    "estaticos": s.STORAGES["staticfiles"]["BACKEND"], "log": s.LOGGING["root"]["level"],
    "thread": s.STARHUB_TAREFAS_EM_THREAD, "broker": s.CELERY_BROKER_URL,
}))
"""


def _prod(**extra):
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith(
        ("DJANGO_", "POSTGRES_", "CORS_", "AVALIACOES_", "SERVIR_", "REDIS_", "LOG_"))}
    ambiente |= {**BASE, **extra, "DJANGO_SETTINGS_MODULE": "config.settings.prod"}
    saida = subprocess.run([sys.executable, "-c", LER], cwd=RAIZ, env=ambiente,
                           capture_output=True, text=True, timeout=120)
    if saida.returncode:
        raise AssertionError(saida.stderr[-2000:])
    return json.loads(saida.stdout.strip().splitlines()[-1])


def test_prod_carrega_com_o_env_de_producao():
    s = _prod()
    assert s["debug"] is False and s["thread"] is False
    assert s["banco"] == {"HOST": "banco.interno", "NAME": "starhub",
                          "OPTIONS": {"sslmode": "prefer"}, "CONN_MAX_AGE": 60}
    assert s["broker"] == "redis://redis:6379/0"
    # WhiteNoise logo depois do SecurityMiddleware: uvicorn nao serve /static/.
    assert s["middleware"][1] == "whitenoise.middleware.WhiteNoiseMiddleware"
    assert s["estaticos"].startswith("whitenoise.")
    assert s["ssl"] is True and s["hsts"] > 0 and s["media"] is True and s["log"] == "INFO"
    assert "corsheaders" not in s["apps"]  # sem CORS geral; avaliacoes usam a conta


def test_cors_geral_vem_do_env_sem_controlar_avaliacoes():
    s = _prod(CORS_ALLOWED_ORIGINS="https://www.loja.com.br, https://loja.myshopify.com",
              AVALIACOES_ORIGENS="https://antiga.com.br")
    assert s["cors"] == ["https://www.loja.com.br", "https://loja.myshopify.com"]
    assert s["cors_url"] == "^$"
    assert s["middleware"][0] == "apps.shopify.avaliacoes_cors.CorsPadraoSemAvaliacoes"
    assert "apps.shopify.avaliacoes_cors.AvaliacoesCorsMiddleware" in s["middleware"]
    assert _prod(CORS_ALLOWED_ORIGINS="https://a.com", CORS_URLS_REGEX="^/wp-json/")[
        "cors_url"] == "^/wp-json/"


def test_banco_ssl_e_media_vem_do_env():
    s = _prod(POSTGRES_SSLMODE="require", POSTGRES_CONN_MAX_AGE="0", DJANGO_SSL_REDIRECT="0",
              SERVIR_MEDIA="0", LOG_LEVEL="WARNING")
    assert s["banco"]["OPTIONS"] == {"sslmode": "require"} and s["banco"]["CONN_MAX_AGE"] == 0
    assert s["ssl"] is False and s["hsts"] == 0 and s["media"] is False and s["log"] == "WARNING"


@pytest.mark.parametrize("faltando", ["DJANGO_SECRET_KEY", "POSTGRES_PASSWORD", "REDIS_URL"])
def test_sem_variavel_obrigatoria_nao_sobe_e_diz_qual(faltando):
    """Subir com segredo vazio ou sem banco falharia longe do motivo; aqui diz qual falta."""
    with pytest.raises(AssertionError, match=f"Defina a variavel de ambiente {faltando}"):
        _prod(**{faltando: ""})
