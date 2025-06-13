#!/usr/bin/env python
"""
langchain_mcp_client.py

Este arquivo implementa um cliente MCP que:
  - Conecta a um servidor MCP via uma conexão stdio.
  - Carrega as ferramentas MCP disponíveis usando a função adaptadora load_mcp_tools.
  - Instancia o modelo ChatGoogleGenerativeAI (Google Gemini) usando sua GOOGLE_API_KEY.
  - Cria um agente React usando o agente pré-construído do LangGraph (create_react_agent) com o LLM e as ferramentas.
  - Executa um loop de chat interativo assíncrono para processar consultas do usuário.

Explicações detalhadas:
  - Retries (max_retries=2): Se uma chamada de API falhar devido a erros transitórios (ex: problemas de rede),
    a chamada será automaticamente retentada até 2 vezes. Aumente isso se você experimentar falhas temporárias.
  - Temperature (definido como 0): Controla a aleatoriedade. Uma temperatura de 0 produz respostas determinísticas.
    Valores mais altos (ex: 0.7) produzem respostas mais criativas e variadas.
  - GOOGLE_API_KEY: Necessária para autenticação com o serviço de IA generativa do Google.
  
As respostas são impressas como JSON usando um codificador personalizado para lidar com objetos não serializáveis.
"""

import asyncio                      # Para operações assíncronas
import os                           # Para acessar variáveis de ambiente
import sys                          # Para processamento de argumentos de linha de comando
import json                         # Para impressão formatada de saída JSON
from contextlib import AsyncExitStack # Garante que todos os recursos assíncronos sejam fechados corretamente
from typing import Optional, List   # Para dicas de tipo

# ---------------------------
# Importações do Cliente MCP
# ---------------------------
from mcp import ClientSession, StdioServerParameters  # Gerenciamento de sessão MCP e parâmetros de inicialização
from mcp.client.stdio import stdio_client             # Para conectar ao servidor MCP via stdio

# ---------------------------
# Importações de Agente e LLM
# ---------------------------
from langchain_mcp_adapters.tools import load_mcp_tools  # Adaptador para carregar ferramentas MCP corretamente
from langgraph.prebuilt import create_react_agent         # Agente React pré-construído do LangGraph
from langchain_google_genai import ChatGoogleGenerativeAI  # Wrapper do LLM Google Gemini

# ---------------------------
# Configuração do Ambiente
# ---------------------------
from dotenv import load_dotenv
load_dotenv()  # Carrega variáveis de ambiente de um arquivo .env (ex: GOOGLE_API_KEY)

# ---------------------------
# Codificador JSON Personalizado
# ---------------------------
class CustomEncoder(json.JSONEncoder):
    """
    Codificador JSON personalizado que lida com objetos com um atributo 'content'.
    
    Se um objeto tiver um atributo 'content', ele retorna um dicionário com o tipo do objeto e seu conteúdo.
    Caso contrário, ele retorna ao codificador padrão.
    """
    def default(self, o):
        if hasattr(o, "content"):
            return {"type": o.__class__.__name__, "content": o.content}
        return super().default(o)

# ---------------------------
# Instanciação do LLM
# ---------------------------
# Cria uma instância do LLM Google Gemini.
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",    # Modelo Gemini a ser usado
    temperature=0,               # 0 = saída determinística; aumente para mais criatividade
    max_retries=2,               # Tenta novamente automaticamente as chamadas de API até 2 vezes para erros transitórios
    google_api_key=os.getenv("GOOGLE_API_KEY")  # A chave da API do Google deve ser definida no seu ambiente ou arquivo .env
)

# ---------------------------
# Argumento do Script do Servidor MCP
# ---------------------------
if len(sys.argv) < 2:
    print("Uso: python client_langchain_google_genai_bind_tools.py <caminho_para_o_script_do_servidor>")
    sys.exit(1)
server_script = sys.argv[1]

# ---------------------------
# Parâmetros do Servidor MCP
# ---------------------------
# Configura parâmetros para iniciar o servidor MCP.
server_params = StdioServerParameters(
    command="python" if server_script.endswith(".py") else "node",
    args=[server_script],
)

# Variável global para manter a sessão MCP ativa.
# Este é um simples recipiente com um atributo "session" para uso pelo adaptador de ferramenta.
mcp_client = None

# ---------------------------
# Função Assíncrona Principal: run_agent
# ---------------------------
async def run_agent():
    """
    Conecta ao servidor MCP, carrega as ferramentas MCP, cria um agente React e executa um loop de chat interativo.
    
    Passos:
      1. Abre uma conexão stdio com o servidor MCP.
      2. Cria e inicializa uma sessão MCP.
      3. Armazena a sessão em um recipiente global (mcp_client) para acesso às ferramentas.
      4. Carrega as ferramentas MCP usando load_mcp_tools.
      5. Cria um agente React usando create_react_agent com o LLM e as ferramentas carregadas.
      6. Entra em um loop interativo: para cada consulta do usuário, invoca o agente assincronamente usando ainvoke,
         então imprime a resposta como JSON formatado usando nosso codificador personalizado.
    """
    global mcp_client
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()  # Inicializa a sessão MCP
            # Define o mcp_client global para um objeto simples contendo a sessão.
            mcp_client = type("MCPClientHolder", (), {"session": session})()
            # Carrega as ferramentas MCP usando o adaptador; isso lida com aguardar e a conversão.
            tools = await load_mcp_tools(session)
            # Cria um agente React usando o LLM e as ferramentas carregadas.
            agent = create_react_agent(llm, tools)
            print("Cliente MCP Iniciado! Digite 'quit' para sair.")
            while True:
                query = input("\nConsulta: ").strip()
                if query.lower() == "quit":
                    break
                # O agente espera a entrada como um dict com a chave "messages".
                response = await agent.ainvoke({"messages": query})
                # Formata a resposta como JSON usando o codificador personalizado.
                try:
                    formatted = json.dumps(response, indent=2, cls=CustomEncoder)
                except Exception as e:
                    formatted = str(response)
                print("\nResposta:")
                print(formatted)
    return

# ---------------------------
# Bloco de Execução Principal
# ---------------------------
if __name__ == "__main__":
    asyncio.run(run_agent())