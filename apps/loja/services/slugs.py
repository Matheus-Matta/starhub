from django.utils.text import slugify


def slug_livre(modelo, base, pk_atual=None, conta=None):
    """"camisetas" ja existe na conta? devolve "camisetas-2", "camisetas-3"...

    O mesmo slug em outra conta e livre. `conta` explicita importa no admin do
    superusuario, em que o manager enxerga todas as contas.
    """
    base = slugify(base or "", allow_unicode=True) or modelo._meta.model_name
    existentes = modelo.objects.exclude(pk=pk_atual)
    if conta is not None:
        existentes = existentes.filter(account_id=conta)
    candidato, n = base, 2
    while existentes.filter(slug=candidato).exists():
        candidato, n = f"{base}-{n}", n + 1
    return candidato
