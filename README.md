# Eleição 2026: deputados eleitos e suplentes

`extrair_deputados.py` gera um CSV (separado por `;`, abre direto no Excel) com,
para cada UF:

- **Deputados federais** e **deputados estaduais** (no DF, **distritais**) eleitos;
- os **3 primeiros suplentes de cada partido/federação** (ordenados por votos).

Colunas: UF, cargo, resultado, ordem de suplência, situação, nome completo,
nome de urna, número, partido, federação/coligação, CPF, votos e id TSE.

```bash
python3 extrair_deputados.py                      # todas as UFs
python3 extrair_deputados.py --ufs CE --saida ce.csv
```

Requer Python 3.8+ e acesso a `divulgacandcontas.tse.jus.br` e
`resultados.tse.jus.br`. Rode depois que o TSE concluir a totalização; antes
disso a situação "Eleito"/"Suplente" ainda não existe ou está incompleta.
