import io
from datetime import date, datetime

import openpyxl
import requests
from bs4 import BeautifulSoup


class auth:
    """Autenticação na plataforma web do Sieg via cookie COFRE.AUTH."""

    _HUB_LOGIN_URL = "https://hub.sieg.com/"
    _AUTH_URL = "https://auth.sieg.com/"
    _COOKIE_NAME = "COFRE.AUTH"
    _DEFAULT_HEADERS = {
        "accept-language": "pt-BR,pt;q=0.7",
    }

    def __init__(self, email: str, password: str, print_error: bool = True):
        self.email = email
        self.password = password
        self.print_error = print_error
        self._session = requests.Session()
        self._auth_cookie: str | None = None

    def _obter_campos_login(self) -> dict:
        """GET hub.sieg.com/, extrai os campos hidden do formulário de login."""
        response = self._session.get(
            self._HUB_LOGIN_URL,
            headers=self._DEFAULT_HEADERS,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        fields = {}
        for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
            field = soup.find("input", {"name": name})
            if field is None or not field.get("value"):
                raise ValueError(f"Campo de login '{name}' não encontrado na página do Sieg")
            fields[name] = field["value"]

        return fields

    def _autenticar(self) -> None:
        """Obtém os campos hidden e faz login em auth.sieg.com/."""
        campos = self._obter_campos_login()
        data = {
            **campos,
            "txtEmail": self.email,
            "txtPassword": self.password,
            "btnSubmit": "Entrar",
        }

        response = self._session.post(
            self._AUTH_URL,
            data=data,
            headers={
                **self._DEFAULT_HEADERS,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        response.raise_for_status()

        self._auth_cookie = (
            response.cookies.get(self._COOKIE_NAME)
            or self._session.cookies.get(self._COOKIE_NAME)
        )
        if not self._auth_cookie:
            raise Exception("Falha na autenticação: cookie COFRE.AUTH não recebido")

        self._session.cookies.set(
            self._COOKIE_NAME,
            self._auth_cookie,
            domain="hub.sieg.com",
        )

    def _garantir_autenticado(self) -> None:
        """Autentica apenas quando o cookie ainda não estiver disponível."""
        if self._auth_cookie is None:
            self._autenticar()

    def request(self, method: str, url: str, params=None, **kwargs):
        """Executa requisição autenticada com retry de autenticação (1x)."""
        self._garantir_autenticado()

        response = None
        for tentativa in range(2):
            response = self._session.request(
                method,
                url,
                params=params,
                headers={**self._DEFAULT_HEADERS, **kwargs.pop("headers", {})},
                **kwargs,
            )
            if response.ok:
                return response

            if tentativa == 0:
                self._auth_cookie = None
                self._autenticar()
                continue

            if self.print_error:
                print(
                    f"Erro no retorno da API do Sieg Web\n"
                    f"Status: {response.status_code}\n"
                    f"URL: {url}\n"
                    f"Método: {method}\n"
                    f"Parâmetros: {params}\n"
                    f"Resposta: {response.text[:500]}"
                )
            raise Exception(
                f"Erro após reautenticação: {response.status_code} — {url}"
            )

        raise Exception(f"Erro na requisição: {url}")


class hub(auth):
    """Operações do Hub Sieg Web."""

    _BASE_URL = "https://hub.sieg.com/Handler/HubInfo.ashx"

    @staticmethod
    def _fmt_date(value: str | date | datetime) -> str:
        """Converte data para o formato DD/MM/YYYY esperado pelo Sieg."""
        if isinstance(value, datetime):
            return value.strftime("%d/%m/%Y")
        if isinstance(value, date):
            return value.strftime("%d/%m/%Y")
        return str(value)

    @staticmethod
    def _xlsx_para_json(content: bytes) -> list[dict]:
        """Lê bytes de um arquivo .xlsx e retorna lista de dicts."""
        workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        worksheet = workbook.active
        rows = list(worksheet.iter_rows(values_only=True))
        workbook.close()

        if not rows:
            return []

        headers = [
            str(header) if header is not None else f"col_{index}"
            for index, header in enumerate(rows[0])
        ]

        return [dict(zip(headers, row)) for row in rows[1:]]

    def exportar_xmls(
        self,
        dashboard_id: str,
        cnpj: str,
        date_start: str | date | datetime,
        date_end: str | date | datetime,
        cnpj_emit: str = "",
        cnpj_dest: str = "",
        cnpj_rem: str = "",
        cnpj_tom: str = "",
        xml_type: int = 99,
        number_xml: int = 0,
    ) -> list[dict]:
        """
        Exporta XMLs do Hub Sieg e retorna o relatório Excel como JSON.

        Args:
            dashboard_id: ID do dashboard (ex.: "15490-32946452000157").
            cnpj: CNPJ do certificado (ex.: "32946452000157").
            date_start: Data inicial de emissão (DD/MM/YYYY ou date/datetime).
            date_end: Data final de emissão (DD/MM/YYYY ou date/datetime).
            cnpj_emit: Filtro opcional de CNPJ emitente.
            cnpj_dest: Filtro opcional de CNPJ destinatário.
            cnpj_rem: Filtro opcional de CNPJ remetente.
            cnpj_tom: Filtro opcional de CNPJ tomador.
            xml_type: Tipo de XML (padrão: 99).
            number_xml: Número do XML (padrão: 0).

        Returns:
            list[dict]: Linhas da planilha como dicionários.
        """
        params = {
            "action": "exportXmlDownloadExcel",
            "dashboardId": dashboard_id,
            "dateStartEmissionStr": self._fmt_date(date_start),
            "dateEndEmissionStr": self._fmt_date(date_end),
            "xmlKey": "",
            "xmlType": xml_type,
            "typeDownload": "",
            "cnpjEmit": cnpj_emit,
            "cnpjDest": cnpj_dest,
            "cnpjRem": cnpj_rem,
            "cnpjTom": cnpj_tom,
            "numberXml": number_xml,
            "dateDownloadInitStr": "",
            "dateDownloadFimStr": "",
            "certificateId": dashboard_id,
            "cnpjCertificate": cnpj,
        }

        response = self.request("GET", self._BASE_URL, params=params)
        return self._xlsx_para_json(response.content)
