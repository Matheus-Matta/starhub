class TenantError(RuntimeError):
    """Erro de seguranca no isolamento entre contas."""


class TenantContextMissing(TenantError):
    pass


class TenantMismatchError(TenantError):
    pass
