# Importa bibliotecas necessárias
import asyncio
import os
import sys

# Importa componentes do cliente MCP
from typing import Optional  # Para dicas de tipo de valores opcionais
from contextlib import AsyncExitStack  # Para gerenciar múltiplas tarefas assíncronas
from mcp import ClientSession, StdioServerParameters  # Gerenciamento de sessão MCP
from mcp.client.stdio import stdio_client  # Cliente MCP para comunicação de E/S padrão

# Importa o SDK de IA Generativa do Google
from google import genai
from google.genai import types
from google.genai.types import Tool, FunctionDeclaration
from google.genai.types import GenerateContentConfig

from dotenv import load_dotenv  # Para carregar chaves de API do arquivo .env
load_dotenv()

class MCPClient:
    def __init__(self):
        """Inicializa o cliente MCP e configura a API Gemini."""
        self.session: Optional[ClientSession] = None  # Sessão MCP para comunicação
        self.exit_stack = AsyncExitStack()  # Gerencia a limpeza de recursos assíncronos

        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY não encontrada. Adicione-a ao seu arquivo .env.")

        # Configura o cliente de IA Gemini
        self.genai_client = genai.Client(api_key=gemini_api_key)

    async def connect_to_server(self, server_script_path: str):
        """Conecta ao servidor MCP e lista as ferramentas disponíveis."""

        # Determina se o script do servidor está escrito em Python ou JavaScript
        # Isso nos permite executar o comando correto para iniciar o servidor MCP
        command = "python" if server_script_path.endswith('.py') else "node"

        # Define os parâmetros para conexão ao servidor MCP
        server_params = StdioServerParameters(command=command, args=[server_script_path])

        # Estabelece comunicação com o servidor MCP usando entrada/saída padrão (stdio)
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))

        # Extrai os fluxos de leitura/escrita do objeto de transporte
        self.stdio, self.write = stdio_transport

        # Inicializa a sessão do cliente MCP, que permite a interação com o servidor
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        # Envia uma solicitação de inicialização ao servidor MCP
        await self.session.initialize()

        # Solicita a lista de ferramentas disponíveis do servidor MCP
        response = await self.session.list_tools()
        tools = response.tools  # Extrai a lista de ferramentas da resposta

        # Imprime uma mensagem mostrando os nomes das ferramentas disponíveis no servidor
        print("\nConectado ao servidor com as ferramentas:", [tool.name for tool in tools])

        # Converte as ferramentas MCP para o formato Gemini
        self.function_declarations = convert_mcp_tools_to_gemini(tools)


    async def process_query(self, query: str) -> str:
        """
        Processa uma consulta do usuário usando a API Gemini e executa chamadas de ferramentas, se necessário.

        Args:
            query (str): A consulta de entrada do usuário.

        Returns:
            str: A resposta gerada pelo modelo Gemini.
        """

        # Formata a entrada do usuário como um objeto Content estruturado para Gemini
        user_prompt_content = types.Content(
            role='user',  
            parts=[types.Part.from_text(text=query)]  # Converte a consulta de texto em um formato compatível com Gemini
        )

        # Envia a entrada do usuário para a IA Gemini e inclui as ferramentas disponíveis para chamadas de função
        response = self.genai_client.models.generate_content(
            model='gemini-1.5-flash',  
            contents=[user_prompt_content],  # Envia a entrada do usuário para Gemini
            config=types.GenerateContentConfig(
                tools=self.function_declarations,  # Passa a lista de ferramentas MCP disponíveis para o Gemini usar
            ),
        )

        # Inicializa variáveis para armazenar o texto da resposta final e as mensagens do assistente
        final_text = [] 
        assistant_message_content = []  # Armazena as respostas do assistente

        # Processa a resposta recebida do Gemini
        for candidate in response.candidates:
            if candidate.content.parts:  # Garante que a resposta tenha conteúdo
                for part in candidate.content.parts:
                    if isinstance(part, types.Part):  # Verifica se a parte é uma unidade de resposta Gemini válida
                        if part.function_call:  # Se o Gemini sugerir uma chamada de função, processe-a
                            # Extrai os detalhes da chamada de função
                            function_call_part = part  # Armazena a resposta da chamada de função
                            tool_name = function_call_part.function_call.name  # Nome da ferramenta MCP que o Gemini quer chamar
                            tool_args = function_call_part.function_call.args  # Argumentos necessários para a execução da ferramenta

                            # Imprime informações de depuração: Qual ferramenta está sendo chamada e com quais argumentos
                            print(f"\n[Gemini solicitou chamada de ferramenta: {tool_name} com args {tool_args}]")

                            # Executa a ferramenta usando o servidor MCP
                            try:
                                result = await self.session.call_tool(tool_name, tool_args)  # Chama a ferramenta MCP com os argumentos
                                function_response = {"result": result.content}  # Armazena a saída da ferramenta
                            except Exception as e:
                                function_response = {"error": str(e)}

                            # Formata a resposta da ferramenta para o Gemini de uma forma que ele entenda
                            function_response_part = types.Part.from_function_response(
                                name=tool_name,  # Nome da função/ferramenta executada
                                response=function_response  # O resultado da execução da função
                            )

                            # Estrutura a resposta da ferramenta como um objeto Content para Gemini
                            function_response_content = types.Content(
                                role='tool',  # Especifica que esta resposta vem de uma ferramenta
                                parts=[function_response_part]  # Anexa a parte da resposta formatada
                            )

                            # Envia os resultados da execução da ferramenta de volta para o Gemini para processamento
                            response = self.genai_client.models.generate_content(
                                model='gemini-1.5-flash',  # Usa o mesmo modelo
                                contents=[
                                    user_prompt_content,  # Inclui a consulta original do usuário
                                    function_call_part,  # Inclui a solicitação de chamada de função do Gemini
                                    function_response_content,  # Inclui o resultado da execução da ferramenta
                                ],
                                config=types.GenerateContentConfig(
                                    tools=self.function_declarations,  # Fornece as ferramentas disponíveis para uso contínuo
                                ),
                            )

                            # Extrai o texto da resposta final do Gemini após processar a chamada da ferramenta
                            final_text.append(response.candidates[0].content.parts[0].text)
                        else:
                            # Se nenhuma chamada de função foi solicitada, simplesmente adicione a resposta de texto do Gemini
                            final_text.append(part.text)

        # Retorna a resposta combinada como uma única string formatada
        return "\n".join(final_text)


    async def chat_loop(self):
        """Executa uma sessão de bate-papo interativa com o usuário."""
        print("\nCliente MCP Iniciado! Digite 'quit' para sair.")

        while True:
            query = input("\nConsulta: ").strip()
            if query.lower() == 'quit':
                break

            # Processa a consulta do usuário e exibe a resposta
            response = await self.process_query(query)
            print("\n" + response)

    async def cleanup(self):
        """Limpa os recursos antes de sair."""
        await self.exit_stack.aclose()

def clean_schema(schema):
    """
    Remove recursivamente os campos 'title' do esquema JSON.

    Args:
        schema (dict): O dicionário do esquema.

    Returns:
        dict: Esquema limpo sem os campos 'title'.
    """
    if isinstance(schema, dict):
        schema.pop("title", None)  # Remove o título se presente

        # Limpa recursivamente as propriedades aninhadas
        if "properties" in schema and isinstance(schema["properties"], dict):
            for key in schema["properties"]:
                schema["properties"][key] = clean_schema(schema["properties"][key])

    return schema

def convert_mcp_tools_to_gemini(mcp_tools):
    """
    Converte as definições de ferramentas MCP para o formato correto para chamadas de função da API Gemini.

    Args:
        mcp_tools (list): Lista de objetos de ferramentas MCP com 'name', 'description' e 'inputSchema'.

    Returns:
        list: Lista de objetos Gemini Tool com declarações de função formatadas corretamente.
    """
    gemini_tools = []

    for tool in mcp_tools:
        # Garante que inputSchema seja um esquema JSON válido e o limpa
        parameters = clean_schema(tool.inputSchema)

        # Constrói a declaração da função
        function_declaration = FunctionDeclaration(
            name=tool.name,
            description=tool.description,
            parameters=parameters  # Agora formatado corretamente
        )

        # Envolve em um objeto Tool
        gemini_tool = Tool(function_declarations=[function_declaration])
        gemini_tools.append(gemini_tool)

    return gemini_tools


async def main():
    """Função principal para iniciar o cliente MCP."""
    if len(sys.argv) < 2:
        print("Uso: python client.py <caminho_para_o_script_do_servidor>")
        sys.exit(1)

    client = MCPClient()
    try:
        # Conecta ao servidor MCP e inicia o loop de bate-papo
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        # Garante que os recursos sejam limpos
        await client.cleanup()

if __name__ == "__main__":
    # Executa a função principal dentro do loop de eventos asyncio
    asyncio.run(main())