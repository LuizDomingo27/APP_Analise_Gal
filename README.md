# 🔍 Dashboard de Controle de Qualidade e Cobrança de Fornecedores

Este é um sistema desenvolvido em Streamlit projetado para monitorar a qualidade na linha de acabamento de produção, gerenciar o histórico de defeitos/remontes e processar cobranças individuais de fornecedores de forma segura.

---

## 🛠️ Arquitetura e Organização do Projeto

O projeto adota uma arquitetura limpa em camadas para manter a separação de responsabilidades:

```text
APP_Defeito_Gal/
├── app.py                     # Ponto de entrada (Layout e orquestração do Dashboard)
├── requirements.txt           # Dependências do projeto
├── dataset/                   # Armazenamento de dados
│   ├── bd_principal.xlsx      # Base principal de dados ativos
│   ├── bd_principal_backup.xlsx # Backup único da última versão válida
│   └── bd_cobranca.xlsx       # Histórico de cobranças efetuadas e status
├── pages/                     # Páginas secundárias do Streamlit
│   ├── 2_Cobranca.py          # Interface de Lançamento de Cobranças
│   └── 3_Historico_Cobranca.py # Visualização e edição do Histórico de Cobranças
└── src/                       # Código-fonte modularizado
    ├── charts/
    │   └── builder.py         # Criação de gráficos em Plotly (design premium)
    ├── config/
    │   └── settings.py        # Configurações do sistema (paleta de cores, colunas)
    ├── data/
    │   ├── loader.py          # Validação, backups e salvamento de novos arquivos Excel
    │   ├── processor.py       # Regras de negócio, KPIs e agregação de dados
    │   ├── cnpj_loader.py     # Carregamento e cache dos CNPJs de fornecedores
    │   └── cobranca_history.py # Operações de leitura/escrita no histórico de cobrança
    ├── services/
    │   ├── exporter.py        # Exportação geral de resumos em Excel (vários fornecedores)
    │   └── charge_exporter.py # Geração da planilha individual de cobrança (.xlsx)
    ├── ui/
    │   ├── filters.py         # Componentes de filtros e sidebar
    │   ├── metrics.py         # Visualização de KPIs e insights automáticos
    │   ├── layout.py          # Renderização de seções de gráficos e tabela interativa
    │   ├── preview.py         # Visualização para impressão em HTML
    │   └── cobranca.py        # Lançamento e regras de validação de cobrança
    └── utils/
        └── cnpj_validator.py  # Algoritmo de validação e formatação de CNPJ
```

---

## 📋 Regras de Negócio Implementadas

### 1. Política de Backup Simplificada
Para evitar o consumo desnecessário de armazenamento, o sistema mantém **exclusivamente um único arquivo de backup** chamado `bd_principal_backup.xlsx`. Toda vez que uma operação de salvamento ou upload de novos dados é executada:
- A base ativa antiga é salva diretamente por cima de `bd_principal_backup.xlsx`.
- A nova versão passa a ser a base ativa em `bd_principal.xlsx`.

### 2. Upload de Dados e Prevenção de Duplicados (Deduplicação por Data)
Ao fazer upload de um novo lote de dados através da sidebar:
- A chave de validação de duplicidade é a **data de produção** (`DATA DE PRODUÇÃO ACABAMENTO`).
- Se o lote importado contiver datas que já existem na base principal, a importação é bloqueada para evitar duplicidade de registros históricos.
- Nomes de fornecedores repetidos são perfeitamente aceitos, contanto que as ordens (OM) e datas de produção sejam distintas.

### 3. Regra de Cobrança e Descontos
- **Limite Mínimo de Cobrança (Threshold)**: O sistema impõe um limite mínimo de valor acumulado para que uma cobrança seja elegível para emissão (padrão de R$ 400,00). Esse limite é ajustável dinamicamente através do painel lateral da página de Cobrança.
- **Processamento Individual**: A cobrança é gerada e tratada individualmente por fornecedor, mesmo que múltiplos fornecedores atinjam o limite estipulado simultaneamente.
- **Ciclo de Lançamento**:
  1. A cobrança é calculada sobre os dados ativos do fornecedor selecionado.
  2. O operador informa e valida o CNPJ do fornecedor.
  3. Ao confirmar, o documento profissional em Excel (.xlsx) é gerado para download.
  4. Os dados cobrados são removidos de `bd_principal.xlsx` e movidos para o histórico `bd_cobranca.xlsx`.

### 4. Controle de Status de Cobrança
Cada cobrança efetuada possui um status de pagamento registrado no histórico (`bd_cobranca.xlsx`):
- `Pendente` (Padrão)
- `Pago`
- `Contestado`
Esse status pode ser alterado diretamente na tabela editável da página de Histórico de Cobrança.

---

## 🚀 Instalação e Execução

### Pré-requisitos
- Python 3.11+
- Instalar dependências listadas no arquivo `requirements.txt`.

### Passos para Execução
1. Abra a pasta do projeto em seu terminal.
2. Ative seu ambiente virtual (recomendado):
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   source .venv/bin/activate  # Linux/macOS
   ```
3. Instale os pacotes necessários:
   ```bash
   pip install -r requirements.txt
   ```
4. Inicie o painel do Streamlit:
   ```bash
   streamlit run app.py
   ```
