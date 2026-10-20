import requests

from apps.starchats.provedores import ErroProvedorMensagens


class ErroStarChats(ErroProvedorMensagens):
    pass


class ClienteStarChats:
    def __init__(self, configuracao):
        self.configuracao = configuracao
        self.base = configuracao.url_base.rstrip("/")
        self.conta = configuracao.conta_externa_id
        token = configuracao.token_acesso
        self.sessao = requests.Session()
        self.sessao.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "api_access_token": token,
                "Content-Type": "application/json",
            }
        )

    def request(self, metodo, caminho, **kwargs):
        try:
            resposta = self.sessao.request(
                metodo, f"{self.base}{caminho}", timeout=(5, 20), **kwargs
            )
        except requests.RequestException as erro:
            raise ErroStarChats(f"Nao foi possivel conectar ao StarChats: {erro}") from erro
        if not resposta.ok:
            detalhe = resposta.text.strip().replace("\n", " ")[:500]
            raise ErroStarChats(
                f"StarChats respondeu HTTP {resposta.status_code}: {detalhe or 'sem detalhe'}"
            )
        try:
            return resposta.json()
        except ValueError as erro:
            raise ErroStarChats("O StarChats devolveu uma resposta que nao e JSON.") from erro

    def caixas(self):
        return self.request("GET", f"/api/v1/accounts/{self.conta}/inboxes")

    def modelos(self, caixa_id):
        caminho = f"/api/v1/accounts/{self.conta}/inboxes/{caixa_id}/message_templates"
        return self.request("GET", caminho)

    def criar_contato(self, dados):
        return self.request("POST", f"/api/v1/accounts/{self.conta}/contacts", json=dados)

    def vincular_contato(self, contato_id, dados):
        caminho = f"/api/v1/accounts/{self.conta}/contacts/{contato_id}/contact_inboxes"
        return self.request("POST", caminho, json=dados)
    def criar_conversa(self, dados):
        return self.request("POST", f"/api/v1/accounts/{self.conta}/conversations", json=dados)

    def enviar_mensagem(self, conversa_id, dados):
        caminho = f"/api/v1/accounts/{self.conta}/conversations/{conversa_id}/messages"
        return self.request("POST", caminho, json=dados)
