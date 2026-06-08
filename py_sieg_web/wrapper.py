import json
import threading
from time import sleep, time
from datetime import datetime, date
from collections import deque
import requests
import base64
import urllib.parse


class auth():

    # Limites oficiais Bling: 3 req/s e 120.000 req/dia por conta
    _RATE_LIMIT_PER_SECOND = 3
    _RATE_LIMIT_DAILY = 120_000

    def __init__(self, access_token="", client_id="", client_secret="", print_error=True):
        self.access_token = access_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://api.bling.com.br/Api/v3"
        self.print_error = print_error
        # Rate limiter Thread-safe por instância (limite é por conta Bling)
        self._rl_lock = threading.Lock()
        self._rl_second_ts: deque = deque()  # timestamps das req. no último segundo
        self._rl_daily_count = 0
        self._rl_daily_date = date.today()

    def _rl_acquire(self):
        """Garante respeito aos limites de 3 req/s e 120k req/dia. Thread-safe."""
        with self._rl_lock:
            now = time()
            today = date.today()

            # Reset contador diário se a data mudou
            if self._rl_daily_date != today:
                self._rl_daily_count = 0
                self._rl_daily_date = today

            # Limite diário atingido — não tem sentido continuar esperando
            if self._rl_daily_count >= self._RATE_LIMIT_DAILY:
                raise Exception(
                    f"Limite diário de {self._RATE_LIMIT_DAILY} requisições da API Bling atingido. "
                    "Tente novamente amanhã."
                )

            # Remove timestamps com mais de 1s da janela deslizante
            while self._rl_second_ts and now - self._rl_second_ts[0] > 1.0:
                self._rl_second_ts.popleft()

            # Se já há 3 req no último segundo, espera o tempo necessário
            if len(self._rl_second_ts) >= self._RATE_LIMIT_PER_SECOND:
                wait = 1.0 - (now - self._rl_second_ts[0])
                if wait > 0:
                    sleep(wait)
                now = time()
                # Limpa novamente após o sleep
                while self._rl_second_ts and now - self._rl_second_ts[0] > 1.0:
                    self._rl_second_ts.popleft()

            self._rl_second_ts.append(now)
            self._rl_daily_count += 1

    def gerar_url_autorizacao(self, state=None):
        """
        Gera a URL de autorização para o fluxo OAuth 2.0.
        
        Args:
            state (str, optional): Sequência aleatória de caracteres para CSRF protection
            
        Returns:
            str: URL de autorização
            
        Exemplo:
            url = client.gerar_url_autorizacao("estado_aleatorio_123")
            # Redirecione o usuário para esta URL
        """
        if not self.client_id:
            raise ValueError("client_id é obrigatório para gerar URL de autorização")
        
        params = {
            'response_type': 'code',
            'client_id': self.client_id
        }
        
        if state:
            params['state'] = state
        
        query_string = urllib.parse.urlencode(params)
        return f"https://www.bling.com.br/Api/v3/oauth/authorize?{query_string}"

    def trocar_code_por_tokens(self, authorization_code):
        """
        Troca o authorization code pelos tokens de acesso.
        
        Args:
            authorization_code (str): Código de autorização recebido do callback
            
        Returns:
            dict: Dicionário com os tokens ou erro
            
        Exemplo:
            tokens = client.trocar_code_por_tokens("codigo_do_callback")
            if 'access_token' in tokens:
                client.access_token = tokens['access_token']
                client.refresh_token = tokens['refresh_token']
        """
        if not self.client_id or not self.client_secret:
            raise ValueError("client_id e client_secret são obrigatórios")

        # Codificar credenciais em base64
        credentials = f"{self.client_id}:{self.client_secret}"
        credentials_b64 = base64.b64encode(credentials.encode()).decode()

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': '1.0',
            'Authorization': f'Basic {credentials_b64}'
        }

        data = {
            'grant_type': 'authorization_code',
            'code': authorization_code
        }

        try:
            response = requests.post(
                'https://api.bling.com.br/Api/v3/oauth/token',
                headers=headers,
                data=data
            )

            if response.status_code == 200:
                token_data = response.json()
            
                return token_data
            else:
                error_data = response.json() if response.text else {"error": "Erro desconhecido"}
                if self.print_error:
                    print(f"Erro ao obter tokens: {error_data}")
                return error_data
                
        except Exception as e:
            error = {"error": f"Erro na requisição: {str(e)}"}
            if self.print_error:
                print(error['error'])
            return error

    def renovar_access_token(self, refresh_token=None):
        """
        Renova o access token usando o refresh token.
        
        Args:
            refresh_token (str, optional): Refresh token. Usa o armazenado na instância se não fornecido
            
        Returns:
            dict: Dicionário com os novos tokens ou erro
            
        Exemplo:
            novos_tokens = client.renovar_access_token()
            if 'access_token' in novos_tokens:
                print("Token renovado com sucesso!")
        """
        
        if not refresh_token:
            raise ValueError("refresh_token é obrigatório")
            
        if not self.client_id or not self.client_secret:
            raise ValueError("client_id e client_secret são obrigatórios")

        # Codificar credenciais em base64
        credentials = f"{self.client_id}:{self.client_secret}"
        credentials_b64 = base64.b64encode(credentials.encode()).decode()

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': '1.0',
            'Authorization': f'Basic {credentials_b64}'
        }

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }

        try:
            response = requests.post(
                'https://api.bling.com.br/Api/v3/oauth/token',
                headers=headers,
                data=data
            )

            if response.status_code == 200:
                token_data = response.json()
                
                return token_data
            else:
                error_data = response.json() if response.text else {"error": "Erro desconhecido"}
                if self.print_error:
                    print(f"Erro ao renovar token: {error_data}")
                return error_data
                
        except Exception as e:
            error = {"error": f"Erro na requisição: {str(e)}"}
            if self.print_error:
                print(error['error'])
            return error

    def revogar_token(self, token=None, token_type="access_token", revoke_action=None, revoke_target="user"):
        """
        Revoga um access_token ou refresh_token.
        
        Args:
            token (str, optional): Token para revogar. Usa o access_token da instância se não fornecido
            token_type (str): Tipo do token ("access_token" ou "refresh_token")
            revoke_action (str, optional): Tipo de revogação ("logout" ou "uninstall")
            revoke_target (str): Alvo da revogação ("user" ou "company")
            
        Returns:
            bool: True se revogação foi bem-sucedida, False caso contrário
            
        Exemplo:
            # Revogar apenas o token atual
            sucesso = client.revogar_token()
            
            # Revogar todos os tokens do usuário (logout)
            sucesso = client.revogar_token(revoke_action="logout")
            
            # Desinstalar aplicativo (revoga todos os tokens)
            sucesso = client.revogar_token(revoke_action="uninstall")
        """
        token_para_revogar = token or self.access_token
        
        if not token_para_revogar:
            raise ValueError("token é obrigatório")
            
        if not self.client_id or not self.client_secret:
            raise ValueError("client_id e client_secret são obrigatórios")

        # Codificar credenciais em base64
        credentials = f"{self.client_id}:{self.client_secret}"
        credentials_b64 = base64.b64encode(credentials.encode()).decode()

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {credentials_b64}'
        }

        data = {
            'token': token_para_revogar,
            'token_type_hint': token_type
        }

        # Adicionar parâmetros de revogação avançada se fornecidos
        if revoke_action:
            data['revoke_action'] = revoke_action
        if revoke_target:
            data['revoke_target'] = revoke_target

        try:
            response = requests.post(
                'https://api.bling.com.br/oauth/revoke',
                headers=headers,
                data=data
            )

            if response.status_code == 200:
                return True
            else:
                if self.print_error:
                    error_data = response.json() if response.text else {"error": "Erro desconhecido"}
                    print(f"Erro ao revogar token: {error_data}")
                return False
                
        except Exception as e:
            if self.print_error:
                print(f"Erro na requisição de revogação: {str(e)}")
            return False

    def request(self, method="GET", url="", headers=None, params=None, data=None):

        req_params = params if params != None else {}
        req_headers = headers if headers != None else {}
        req_data = data if data != None else {}

        # Usar formato Bearer para OAuth tokens
        if self.access_token != "" and self.access_token != None:
            if self.access_token.startswith('Bearer '):
                req_headers['Authorization'] = self.access_token
            else:
                req_headers['Authorization'] = f'Bearer {self.access_token}'

        while True:
            self._rl_acquire()

            match method:
                case "GET":
                    response = requests.get(url=url, params=req_params, headers=req_headers, data=req_data)
                case "PUT":
                    response = requests.put(url=url, params=req_params, headers=req_headers, data=req_data)
                case "POST":
                    response = requests.post(url=url, params=req_params, headers=req_headers, data=req_data)
                case "DELETE":
                    response = requests.delete(url=url, params=req_params, headers=req_headers, data=req_data)
                case "HEAD":
                    response = requests.head(url=url, params=req_params, headers=req_headers, data=req_data)
                case "OPTIONS":
                    response = requests.options(url=url, params=req_params, headers=req_headers, data=req_data)

            if response.status_code == 200 or response.status_code == 201:
                return response
            elif response.status_code == 429:
                # Distingue limite por segundo (recuperável) de limite diário (fatal)
                try:
                    period = response.json().get("error", {}).get("period", "second")
                except Exception:
                    period = "second"
                if period == "day":
                    raise Exception(
                        f"Limite diário de {self._RATE_LIMIT_DAILY} requisições da API Bling atingido. "
                        "Tente novamente amanhã."
                    )
                # Limite por segundo: aguarda 1s e retenta (o _rl_acquire fará o ajuste fino)
                sleep(1)
            else:
                if self.print_error:
                    try:
                        response_json = response.json()
                        message = response_json['message'] if 'message' in response_json else ""
                        json_content = response_json
                    except:
                        message = ""
                        json_content = response.text
                    
                    print(f"""Erro no retorno da API do Bling
Mensagem: {message}
URL: {url}
Metodo: {method}
Parametros: {req_params}
Headers: {req_headers}
Data: {req_data}
Resposta JSON: {json_content}""")
                if response.status_code == 403 or response.status_code == 404:
                    return None
                else:
                    break

class produtos(auth):

    def ver_produtos(self, all_pages=True, page=1, limite=100, **kwargs):
        """
        Buscar produtos cadastrados.
        
        Args:
            all_pages (bool): Se True, busca todas as páginas automaticamente (padrão: True)
            page (int): Número da página para retornar (padrão: 1)
            limite (int): Quantidade de registros por página (máximo: 100, padrão: 100)
            **kwargs: Parâmetros opcionais de filtro como:
                - criterio: Critério de ordenação (id, nome, codigo, preco, etc.)
                - tipo: Tipo de ordenação (ASC ou DESC)
                - dataInclusao: Data de inclusão (formato: YYYY-MM-DD)
                - dataAlteracao: Data de alteração (formato: YYYY-MM-DD)
                - codigo: Código do produto
                - nome: Nome do produto (busca parcial)
                - situacao: Situação do produto (Ativo, Inativo)
                - formato: Formato do produto (S - Simples, V - com Variações, E - com Composição)
                - tipo_produto: Tipo do produto (P - Produto, S - Serviço)
                - categoria: ID da categoria
                - estoque_minimo: Filtro por estoque mínimo
                - estoque_maximo: Filtro por estoque máximo
                
        Returns:
            dict: Dados dos produtos ou dict vazio se falhou
            
        Documentação: https://developer.bling.com.br/referencia#/Produtos/get_produtos
        """
        
        asct = True  # Acesso Só Com Token

        if asct and (self.access_token == "" or self.access_token == None or type(self.access_token) != str):
            print("Token inválido")
            return {}

        url = self.base_url + "/produtos"

        params = {
            'pagina': page,
            'limite': limite
        }

        # Adicionar parâmetros opcionais de filtro
        if kwargs:
            for key, value in kwargs.items():
                params[key] = value

        response = self.request("GET", url=url, params=params)

        if response:
            if all_pages:
                json_response = response.json()
                
                # Verificar se existe a estrutura de dados esperada
                if 'data' not in json_response:
                    return json_response
                
                produtos_list = json_response['data']
                
                # Continuar buscando páginas enquanto houver dados
                while len(json_response['data']) == limite:  # Se retornou a quantidade máxima, pode haver mais páginas
                    page += 1
                    params['pagina'] = page
                    response2 = self.request("GET", url=url, params=params)

                    if response2:
                        json_response2 = response2.json()
                        if 'data' in json_response2 and json_response2['data']:
                            produtos_list.extend(json_response2['data'])
                            json_response = json_response2
                        else:
                            break
                    else:
                        break

                # Atualizar a resposta final com todos os produtos
                json_response['data'] = produtos_list
                return json_response
            else:
                return response.json()
        else:
            return {}
    
    def ver_produto(self, id_produto):
        """
        Buscar produto por ID.
        
        Args:
            id_produto (int): ID do produto no Bling
            
        Returns:
            dict: Dados do produto ou dict vazio se falhou
            
        Documentação: https://developer.bling.com.br/referencia#/Produtos/get_produtos__idProduto_
        """
        
        asct = True  # Acesso Só Com Token

        if asct and (self.access_token == "" or self.access_token == None or type(self.access_token) != str):
            print("Token inválido")
            return {}

        url = self.base_url + f"/produtos/{id_produto}"

        response = self.request("GET", url=url)

        if response:
            return response.json()
        else:
            return {}
    
    def criar_produto(self, nome, codigo, **kwargs):
        """
        Criar um novo produto.
        
        Args:
            nome (str): Nome do produto
            codigo (str): Código do produto
            **kwargs: Dados opcionais do produto como:
                - descricao: Descrição do produto
                - unidade: Unidade de medida
                - preco: Preço do produto
                - tipo: Tipo do produto (P - Produto, S - Serviço)
                - situacao: Situação (A - Ativo, I - Inativo)
                - formato: Formato (S - Simples, V - com Variações, E - com Composição)
                - categoria: Dados da categoria
                - estoque: Dados de estoque
                - actionEstoque: Ação do estoque (S - Subtrair, N - Não subtrair)
                - dimensoes: Dimensões do produto
                - tributacao: Dados de tributação
                - midia: Mídias do produto
                
        Returns:
            dict: Dados do produto criado ou dict vazio se falhou
            
        Documentação: https://developer.bling.com.br/referencia#/Produtos/post_produtos
        """
        
        asct = True  # Acesso Só Com Token

        if asct and (self.access_token == "" or self.access_token == None or type(self.access_token) != str):
            print("Token inválido")
            return {}

        url = self.base_url + "/produtos"
        
        # Dados obrigatórios
        data = {
            "nome": nome,
            "codigo": codigo
        }
        
        # Adicionar parâmetros opcionais
        if kwargs:
            for key, value in kwargs.items():
                data[key] = value

        response = self.request("POST", url=url, data=json.dumps(data), headers={"Content-Type": "application/json"})

        if response:
            return response.json()
        else:
            return {}
    
    def editar_produto(self, id_produto, **kwargs):
        """
        Atualizar um produto existente.
        
        Args:
            id_produto (int): ID do produto no Bling
            **kwargs: Campos para atualizar como nome, codigo, descricao, preco, etc.
            
        Returns:
            dict: Dados do produto atualizado ou dict vazio se falhou
            
        Documentação: https://developer.bling.com.br/referencia#/Produtos/put_produtos__idProduto_
        """
        
        asct = True  # Acesso Só Com Token

        if asct and (self.access_token == "" or self.access_token == None or type(self.access_token) != str):
            print("Token inválido")
            return {}

        url = self.base_url + f"/produtos/{id_produto}"
        
        # Montar dados para atualização
        data = {}
        if kwargs:
            for key, value in kwargs.items():
                data[key] = value

        response = self.request("PUT", url=url, data=json.dumps(data), headers={"Content-Type": "application/json"})

        if response:
            return response.json()
        else:
            return {}
    
    def deletar_produto(self, id_produto):
        """
        Excluir um produto.
        
        Args:
            id_produto (int): ID do produto no Bling
            
        Returns:
            dict: Resposta de sucesso ou dict vazio se falhou
            
        Documentação: https://developer.bling.com.br/referencia#/Produtos/delete_produtos__idProduto_
        """
        
        asct = True  # Acesso Só Com Token

        if asct and (self.access_token == "" or self.access_token == None or type(self.access_token) != str):
            print("Token inválido")
            return {}

        url = self.base_url + f"/produtos/{id_produto}"

        response = self.request("DELETE", url=url)

        if response:
            return response.json()
        else:
            return {}


class nfe(auth):
    """Operações de Nota Fiscal Eletrônica (NF-e) na API Bling v3.

    Limites respeitados automaticamente pelo rate limiter da classe auth:
    - 3 requisições por segundo por conta
    - 120.000 requisições por dia por conta
    """

    _SITUACOES_COM_XML = {2, 5, 6, 9}  # Cancelada, Autorizada, Emitida DANFE, Denegada

    def listar(self, date_start, date_end, tipo=1, all_pages=True, limite=100, **kwargs):
        """Lista NF-e no período informado.

        Args:
            date_start (date | str): Data inicial (YYYY-MM-DD ou objeto date).
            date_end   (date | str): Data final   (YYYY-MM-DD ou objeto date).
            tipo       (int):  1=Saída (padrão), 2=Entrada.
            all_pages  (bool): Se True percorre todas as páginas automaticamente.
            limite     (int):  Registros por página (máx. 100).
            **kwargs:  Parâmetros extras repassados à query string (ex.: situacao=5).

        Returns:
            list[dict]: Lista de resumos de NF-e.
        """
        if not self.access_token:
            print("Token inválido")
            return []

        # Aceita tanto datetime.date quanto string YYYY-MM-DD
        fmt = lambda d: d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)

        url = self.base_url + "/nfe"
        page = 1
        results = []

        while True:
            params = {
                "pagina": page,
                "limite": limite,
                "tipo": tipo,
                "dataEmissaoInicial": fmt(date_start),
                "dataEmissaoFinal": fmt(date_end),
            }
            params.update(kwargs)

            response = self.request("GET", url=url, params=params)
            if not response:
                break

            body = response.json()
            data = body.get("data", [])
            if data:
                results.extend(data)

            if not all_pages or len(data) < limite:
                break
            page += 1

        return results

    def obter(self, nfe_id):
        """Retorna os detalhes completos de uma NF-e, incluindo a URL do XML.

        Args:
            nfe_id (int | str): ID da NF-e no Bling.

        Returns:
            dict: Dados completos da NF-e (campo ``data`` da resposta).
                  Contém ``xml`` com a URL para download do arquivo XML.
                  Retorna {} em caso de erro.
        """
        if not self.access_token:
            print("Token inválido")
            return {}

        url = self.base_url + f"/nfe/{nfe_id}"
        response = self.request("GET", url=url)

        if response:
            return response.json().get("data", {})
        return {}
