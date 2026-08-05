# -*- coding: utf-8 -*-
"""
Análise de performance de fornecedores.

Portado do app "Central de Performance" (APP_PERFOR) para dentro do Gal como a
página `pages/7_Performance.py`. O pacote é autocontido de propósito: domínio,
dados, serviços e apresentação próprios, sem depender de `src/data/processor.py`.

Por que um pacote separado e não uma extensão do DataProcessor
──────────────────────────────────────────────────────────────
As duas análises respondem perguntas diferentes sobre a MESMA base:

  • `src/data/processor.py` (Análise de defeitos) agrega LINHA A LINHA — cada
    registro é uma ocorrência de remonte. É o certo para contar defeitos,
    custo e minutos.
  • Este pacote agrega por ORDEM MESTRE. O `REAL CORTADO` se repete em toda
    linha de defeito da mesma OM, então somá-lo linha a linha infla o total e
    torna impossível calcular o índice de defeitos. Aqui a ordem é consolidada
    uma única vez por (fornecedor, ordem mestre) — ver `domain/calculations.py`.

Misturar as duas agregações no mesmo objeto tornaria fácil somar a coluna errada
sem erro nenhum, só número torto. Daí a separação.

A fonte é `historico_defeitos` (o histórico PERMANENTE), lida por
`src.data.historico_defeitos.load_historico` e convertida por
`data/dataset_builder.py`.

Atenção a quem for mexer: NÃO trocar por `registros_defeitos` /
`load_data_from_disk`. Aquela é a base ativa, da qual `cobranca_history.py`
APAGA os registros de cada fornecedor cobrado — usá-la faria a performance
melhorar sozinha à medida que os piores fornecedores fossem cobrados. O
raciocínio completo está no topo de `pages/7_Performance.py`.
"""
