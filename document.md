# Documentação do Projeto — Análise Gal

**Sistema de Controle de Qualidade e Cobrança de Fornecedores**

> Documento de referência para apresentação à diretoria.
> Data: 25/07/2026 · Versão do sistema em produção (Streamlit Cloud + Supabase)

---

## 1. Resumo Executivo

O **Análise Gal** é um sistema web interno que monitora a qualidade da linha de
acabamento de produção, registra o histórico permanente de defeitos (remontes)
e automatiza todo o ciclo de **cobrança dos fornecedores** responsáveis pelos
defeitos — do lançamento diário dos dados até a emissão do documento de
cobrança em Excel e o acompanhamento do status (Pendente, Pago ou Devolução).

**O que o sistema entrega ao negócio:**

- **Visibilidade imediata da qualidade**: dashboards com KPIs, gráficos e
  insights automáticos por fornecedor, defeito e período.
- **Recuperação financeira**: transforma o custo do retrabalho (minutos e valor
  do processo) em cobranças formais e rastreáveis aos fornecedores.
- **Memória permanente**: histórico imutável de todos os defeitos importados,
  com registro fotográfico dos tipos de defeito para evitar contestações.
- **Multiusuário e seguro**: login com senha criptografada, perfis de acesso
  (administrador × usuário comum) e uso simultâneo por várias pessoas sem
  perda de dados.

**Números do projeto:** 161 commits · 6 páginas funcionais · 14 suítes de
testes automatizados · arquitetura em camadas com ~45 módulos Python.

---

## 2. O Problema que o Sistema Resolve

Antes do sistema, o controle era feito em planilhas Excel isoladas:

| Dor anterior | Solução implementada |
|---|---|
| Planilhas manuais, sem padrão e sem histórico confiável | Banco de dados central (PostgreSQL/Supabase) com histórico permanente e imutável |
| Cobranças calculadas à mão, sujeitas a erro | Cálculo automático por fornecedor com limite mínimo configurável (threshold de R$ 400) |
| Sem rastreabilidade do que já foi cobrado/pago | Ciclo completo com status: Pendente → Pago ou Devolução, cada etapa em tabela própria |
| Contestações de fornecedores sem evidência | Catálogo de imagens por tipo de defeito, vinculado às consultas por oficina |
| Dados duplicados em importações | Deduplicação automática pela data de produção — importação com data repetida é bloqueada |
| Acesso sem controle | Autenticação própria com perfis; funções críticas restritas a administradores |

---

## 3. Funcionalidades (por página)

### 3.1 Análise de Defeitos (Dashboard principal)
- Importação diária da planilha de produção (append com deduplicação por data).
- KPIs e insights automáticos: totais de remontes, ordens, minutos gerados e
  valor do processo (R$).
- Gráficos interativos (ECharts): ranking de fornecedores, distribuição por
  tipo de defeito, evolução temporal.
- Filtros por fornecedor, defeito e período.
- Tabela interativa e exportação de resumos em Excel.

### 3.2 Histórico de Defeitos
- **Registro permanente** de todos os defeitos importados — nunca apaga;
  novas cargas só acrescentam (dedup por data).
- Mesmos cards, insights e gráficos do dashboard, com filtros de oficina e período.
- Exportação por fornecedor e **filtro por faixa** (popup): escolhe a métrica
  (remontes, ordens ou valor) e o intervalo De/Até, com lista agrupada e
  exportação em PDF — ferramenta para decidir quem cobrar primeiro.
- Upload e correção de nomes de fornecedor na própria página (somente admin).

### 3.3 Cobranças (Histórico de Cobrança)
Página em 4 abas que consolida o ciclo financeiro completo:
1. **Histórico de Cobranças** — lançamentos emitidos e edição de status.
2. **Cobrança de Fornecedores** — geração da cobrança: seleção do fornecedor,
   validação de CNPJ (algoritmo oficial), emissão do documento Excel
   profissional e baixa dos registros cobrados da base ativa.
3. **Pagamentos Concluídos** — cobranças marcadas como *Pago* migram para cá.
4. **Devolução** — quando a oficina opta por consertar as peças em vez de
   pagar, o lançamento migra para a tabela de devoluções.

Recurso adicional — **Cobrança Dividida**: divisão configurável (percentual)
do valor entre fornecedor e empresa; as duas metades são gravadas na mesma
transação com o mesmo código de lançamento, garantindo consistência contábil.

### 3.4 Imagens de Defeitos
- Catálogo visual: uma imagem de referência por tipo de defeito, armazenada
  no próprio banco de dados.
- Consulta por oficina: tabela com OM, oficina, quantidade, defeito e a imagem
  correspondente, além do quadro com os **TOP 3 defeitos** da oficina.
- Cadastro e exclusão de imagens restritos a administradores.

### 3.5 Editar Registros (somente admin)
- Correção segura de valores digitados incorretamente na base ativa
  (ex.: nome de fornecedor com/sem acento).
- Afeta somente a tabela de registros ativos — nunca o histórico de cobranças
  ou pagamentos.

### 3.6 Gerenciar Usuários (somente admin)
- Criação, exclusão e administração de usuários e perfis.
- **Backup manual em Excel**: gera um arquivo .zip com uma planilha por tabela
  do banco — mitigação para a ausência de backup automático no plano gratuito
  do Supabase.

---

## 4. Arquitetura e Tecnologias

### 4.1 Stack

| Camada | Tecnologia |
|---|---|
| Interface web | Streamlit 1.58 (Python) |
| Gráficos | ECharts (streamlit-echarts) |
| Dados/processamento | pandas |
| Banco de dados | PostgreSQL (Supabase) via SQLAlchemy 2.0 + psycopg2, Transaction Pooler |
| Exportações | openpyxl (Excel) e reportlab (PDF) |
| Hospedagem | Streamlit Cloud (deploy contínuo a partir do GitHub) |
| Testes | pytest (14 suítes; SQLite em memória nos testes) |

### 4.2 Organização do código (arquitetura em camadas)

```text
APP_Analise_Gal/
├── app.py                  # Roteador: page config, CSS global, login, navbar no topo
├── pages/                  # 6 páginas (conteúdo de cada tela)
├── src/
│   ├── auth/               # Autenticação: usuários, sessão, portão de login
│   ├── charts/             # Specs ECharts (funções puras) + renderização
│   ├── config/             # Configurações, paleta, design tokens (theme.py)
│   ├── data/               # Camada de dados: conexão, consultas, regras de escrita
│   ├── services/           # Exportadores (Excel de cobrança, resumos, backup)
│   ├── ui/                 # Componentes de tela (filtros, métricas, layout, boundary)
│   └── utils/              # Validador de CNPJ
├── tests/                  # 14 suítes pytest
└── docs/                   # Plano de migração Supabase
```

Separação estrita: as páginas não acessam o banco diretamente — consomem a
camada `src/data/`, que por sua vez usa uma única porta de conexão
(`get_connection()`), facilitando manutenção e testes.

### 4.3 Modelo de dados (principais tabelas)

| Tabela | Papel |
|---|---|
| `registros_defeitos` | Base ativa: defeitos ainda não cobrados |
| `historico_defeitos` | Registro permanente e imutável de tudo que foi importado |
| `historico_cobrancas` | Cobranças emitidas (status Pendente) |
| `pagamentos_concluidos` | Cobranças pagas |
| `devolucoes` | Cobranças convertidas em devolução/conserto |
| `tb_divida_dividida` | Metades fornecedor/empresa da cobrança dividida |
| `defeitos_imagens` | Imagens de referência por defeito (bytea) |
| `UserGal` | Usuários e hashes de senha (PBKDF2) |

---

## 5. Segurança e Controle de Acesso

- **Autenticação própria**: senha com hash **PBKDF2** (nunca armazenada em
  claro) + pergunta de segurança para recuperação.
- **Perfis**: usuários comuns visualizam e consultam; somente administradores
  importam dados, editam registros, gerenciam usuários, cadastram imagens e
  geram backup. Páginas restritas nem aparecem na navegação de usuários comuns.
- **Segredos fora do código**: a URL do banco vive em `st.secrets`
  (Streamlit Cloud), não no repositório.
- **Mensagens de erro seguras**: falhas de banco nunca expõem SQL, nomes de
  tabela ou stacktrace ao usuário — são traduzidas para mensagens amigáveis em
  português; o detalhe técnico vai apenas para os logs do servidor.

---

## 6. Regras de Negócio Implementadas

1. **Deduplicação por data de produção** — importações com datas já existentes
   são bloqueadas; evita registros duplicados no histórico.
2. **Threshold de cobrança** — cobrança só é elegível a partir de um valor
   mínimo acumulado (padrão R$ 400, ajustável na tela).
3. **Cobrança individual por fornecedor** — com validação de CNPJ pelo
   algoritmo oficial antes da emissão.
4. **Ciclo de status** — Pendente → Pago (migra para Pagamentos Concluídos) ou
   Devolução (migra para Devoluções); cada transição move o registro de tabela,
   mantendo cada aba com seus próprios totais.
5. **Cobrança dividida** — percentual configurável fornecedor/empresa, gravado
   atomicamente (mesma transação, mesmo código de lançamento).
6. **Histórico imutável** — a tabela de histórico nunca sofre exclusão.

---

## 7. Qualidade, Confiabilidade e Performance

- **Testes automatizados**: 14 suítes pytest cobrindo autenticação, cobranças,
  devoluções, cobrança dividida, histórico, imagens, backup, exportações,
  filtros por faixa, tratamento de erros de banco e componentes de UI.
- **O app nunca "quebra" para o usuário**: toda página é envolvida por um
  *error boundary* (`@page_guard`); qualquer exceção vira uma mensagem clara
  em português, sem tela vermelha do Streamlit.
- **Performance com cache inteligente**: consultas ao banco usam
  `@st.cache_data` com TTL de 60 segundos + invalidação específica no caminho
  de escrita — a tela responde rápido e os dados nunca ficam defasados por
  mais de 1 minuto entre usuários.
- **Concorrência multiusuário**: escritas críticas usam padrões transacionais
  (reivindicação por rowcount, INSERT..SELECT atômico, advisory locks) para
  que dois usuários operando ao mesmo tempo não corrompam nem percam dados.
- **Design system**: paleta centralizada em design tokens (variáveis CSS
  `--ag-*`), garantindo identidade visual consistente em todas as telas e
  preparando o terreno para um futuro tema escuro.

---

## 8. Evolução do Projeto (linha do tempo)

| Fase | Entrega |
|---|---|
| Início | Dashboard de defeitos lendo planilhas Excel locais |
| Jun/2026 | Migração Excel → **SQLite** com sincronização via GitHub |
| 02/07/2026 | **Camada de autenticação** (login, perfis, PBKDF2) |
| 06–07/07/2026 | **Migração para Supabase/PostgreSQL** — elimina condição de corrida, latência de sync e hashes versionados no repositório; tratamento de erros padronizado |
| 09/07/2026 | Página de **Histórico de Defeitos** (registro permanente) |
| 11/07/2026 | **Catálogo de imagens** de defeitos com consulta por oficina |
| 14/07/2026 | **Cobrança Dividida** fornecedor/empresa |
| 15/07/2026 | **Filtro por faixa** de fornecedores com export PDF |
| 16/07/2026 | Padrões de **cache com TTL** e **concorrência multiusuário**; design tokens |
| 24/07/2026 | **Backup manual em Excel** (zip com todas as tabelas) e nova navbar no topo |

A migração para o Supabase foi o marco técnico central: o modelo anterior
(commit do arquivo de banco no GitHub a cada escrita) tinha risco real de
perda silenciosa de dados com dois usuários simultâneos — o PostgreSQL
resolveu isso nativamente com escritas transacionais.

---

## 9. Infraestrutura e Custos

- **Hospedagem**: Streamlit Cloud (plano gratuito) com deploy automático a
  cada push no GitHub.
- **Banco**: Supabase **free-tier** (PostgreSQL gerenciado).
- **Custo atual de operação: R$ 0** — todo o stack roda em planos gratuitos.
- **Mitigação de risco do free-tier**: como o plano gratuito do Supabase não
  oferece backup automático, foi implementado o backup manual em Excel
  (um clique, admin), gerando um zip com todas as tabelas.

**Ponto de atenção para a diretoria**: se o uso crescer (volume de dados,
número de usuários, criticidade), recomenda-se avaliar o upgrade do Supabase
para plano pago, que traz backups automáticos diários e mais capacidade —
hoje a continuidade do dado depende da disciplina do backup manual.

---

## 10. Possíveis Próximos Passos (roadmap sugerido)

1. **Backup automático agendado** (ou upgrade do plano Supabase).
2. **Tema escuro** — passo 2 do trabalho de design tokens já iniciado.
3. **Relatórios gerenciais periódicos** (resumo mensal automático por e-mail).
4. **Supabase Auth** como evolução opcional da autenticação própria.
5. **Indicadores de tendência** (metas de qualidade por fornecedor, alertas).

---

## 11. Sugestão de Roteiro para a Apresentação

1. **Abertura (1 slide)** — o problema: retrabalho sem visibilidade e cobrança manual.
2. **A solução (1 slide)** — o que é o sistema, em uma frase + print do dashboard.
3. **Demonstração do fluxo (3–4 slides)** — importa produção → analisa defeitos
   → emite cobrança com CNPJ validado → acompanha status até Pago/Devolução.
4. **Diferenciais (1 slide)** — histórico imutável, evidência fotográfica,
   cobrança dividida, multiusuário seguro.
5. **Robustez (1 slide)** — testes automatizados, app nunca quebra, dados no
   PostgreSQL com transações.
6. **Custo e riscos (1 slide)** — custo zero hoje; ponto de atenção do backup.
7. **Roadmap (1 slide)** — próximos passos e o que precisa de decisão da diretoria.

---

*Documento gerado a partir da análise do código-fonte em 25/07/2026 (branch `creatimg`).*
