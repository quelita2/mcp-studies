import os
import subprocess
from mcp.server.fastmcp import FastMCP

# Cria uma instância do FastMCP com o nome "Terminal".
# O FastMCP é uma estrutura que permite expor funções Python como ferramentas para serem consumidas por um cliente MCP.
mcp = FastMCP("Terminal")

# Define o diretório de trabalho padrão.
# os.path.expanduser("~/mcp-client/output") expande para o diretório "output" dentro de "mcp-client"
# na pasta pessoal do usuário (ex: /home/usuario/mcp-client/output no Linux, ou C:\Users\Usuario\mcp-client\output no Windows).
DEFAULT_WORKSPACE = os.path.expanduser("~/mcp-client/output")

@mcp.tool()  
def run_command(command: str):  
    """ 
    Executa um comando de terminal dentro do diretório de trabalho (DEFAULT_WORKSPACE).

    Args:
        command (str): O comando a ser executado no terminal.

    Returns:
        str: A saída padrão (stdout) ou a saída de erro (stderr) do comando,
             ou a mensagem de erro se a execução falhar.
"""
    try:  
        # Executa o comando usando subprocess.run.
        # - command: O comando a ser executado.
        # - shell=True: Permite que o comando seja executado através do shell do sistema.
        # - cwd=DEFAULT_WORKSPACE: Define o diretório de trabalho atual para a execução do comando.
        # - capture_output=True: Captura a saída padrão e a saída de erro.
        # - text=True: Decodifica stdout e stderr como texto.
        result = subprocess.run(command, shell=True, cwd=DEFAULT_WORKSPACE, capture_output=True, text=True)  
        # Retorna a saída padrão se existir, caso contrário, retorna a saída de erro.
        return result.stdout or result.stderr  
    except Exception as e:  
        return str(e)
    
if __name__ == "__main__":  
    # Verifica se o script está sendo executado diretamente.
    # Inicia o servidor MCP usando o transporte 'stdio' (entrada/saída padrão).
    # Isso permite que o cliente MCP se comunique com este servidor através dos fluxos de E/S padrão.
    mcp.run(transport='stdio')