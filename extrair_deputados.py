#!/usr/bin/env python3
"""Extrai deputados federais, estaduais e distritais eleitos em 2026 e os
3 primeiros suplentes (por partido/federação, em cada UF), com nome completo,
partido, UF, CPF e cargo.

Fontes (TSE):
  - divulgacandcontas.tse.jus.br  -> lista de candidatos e ficha (CPF, nome completo)
  - resultados.tse.jus.br         -> votação e situação de totalização

Uso:
  python3 extrair_deputados.py                 # todas as UFs
  python3 extrair_deputados.py --ufs CE SP     # apenas algumas UFs
  python3 extrair_deputados.py --suplentes 3 --saida deputados_2026.csv

Só usa a biblioteca padrão do Python 3.8+.
"""
import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ANO = 2026
DIVULGA = "https://divulgacandcontas.tse.jus.br/divulga/rest/v1"
RESULTADOS = "https://resultados.tse.jus.br/oficial"
# Id da eleição geral federal 2026 no DivulgaCandContas (da URL da ficha do candidato).
ELEICAO_DIVULGA_PADRAO = "20322002026"

UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
       "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
       "SE", "SP", "TO"]
DEP_FEDERAL, DEP_ESTADUAL, DEP_DISTRITAL = 6, 7, 8


def get_json(url, tentativas=4):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if i == tentativas - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if i == tentativas - 1:
                raise
        time.sleep(2 ** (i + 1))


def eleicao_divulga(padrao):
    """Descobre o id da eleição ordinária de 2026; cai no padrão se não achar."""
    try:
        dados = get_json(f"{DIVULGA}/eleicao/ordinarias") or []
        for e in dados:
            if int(e.get("ano", 0)) == ANO and "federal" in (e.get("nomeEleicao") or e.get("descricaoEleicao") or "").lower():
                return str(e["id"])
    except Exception as exc:  # noqa: BLE001
        print(f"aviso: não consegui listar eleições ({exc}); usando {padrao}", file=sys.stderr)
    return padrao


def codigos_resultados():
    """Códigos das eleições de 1º turno de 2026 no site de resultados."""
    cfg = get_json(f"{RESULTADOS}/comum/config/ele-c.json") or {}
    codigos = []
    for pleito in cfg.get("pl", []):
        for e in pleito.get("e", []):
            if str(ANO) in (e.get("nm", "") + pleito.get("dt", "")) and str(e.get("t", "1")) == "1":
                codigos.append(str(e["cd"]))
    return codigos


def votacao(uf, cargo, codigos):
    """Retorna {sqcand: {...}} com votos e situação de totalização."""
    for cd in codigos:
        url = (f"{RESULTADOS}/ele{ANO}/{cd}/dados-simplificados/{uf.lower()}/"
               f"{uf.lower()}-c{cargo:04d}-e{int(cd):06d}-r.json")
        dados = get_json(url)
        if dados and dados.get("cand"):
            return {str(c.get("sqcand")): c for c in dados["cand"]}, dados.get("dt", ""), dados.get("ht", "")
    return {}, "", ""


def listar_candidatos(uf, eleicao, cargo):
    dados = get_json(f"{DIVULGA}/candidatura/listar/{ANO}/{uf}/{eleicao}/{cargo}/candidatos") or {}
    return dados.get("candidatos", [])


def ficha(uf, eleicao, cand_id):
    return get_json(f"{DIVULGA}/candidatura/buscar/{ANO}/{uf}/{eleicao}/candidato/{cand_id}") or {}


def votos(v):
    try:
        return int(str(v.get("vap", "0")).replace(".", ""))
    except ValueError:
        return 0


def selecionar(uf, cargo, eleicao, codigos, n_suplentes):
    candidatos = listar_candidatos(uf, eleicao, cargo)
    resultado, dt, ht = votacao(uf, cargo, codigos)
    eleitos, suplentes_por_grupo = [], {}
    for c in candidatos:
        r = resultado.get(str(c.get("id")), {})
        situacao = r.get("st") or c.get("descricaoTotalizacao") or ""
        s = situacao.lower()
        item = {"cand": c, "situacao": situacao, "votos": votos(r) if r else None,
                "grupo": r.get("cc") or (c.get("partido") or {}).get("sigla", "")}
        if s.startswith("eleito"):
            eleitos.append(item)
        elif s.startswith("suplente"):
            suplentes_por_grupo.setdefault(item["grupo"], []).append(item)
    selecionados = [(it, "Eleito", None) for it in eleitos]
    for grupo, lista in suplentes_por_grupo.items():
        lista.sort(key=lambda it: -(it["votos"] or 0))
        for pos, it in enumerate(lista[:n_suplentes], 1):
            selecionados.append((it, "Suplente", pos))
    atualizado = f"{dt} {ht}".strip()
    return selecionados, len(candidatos), atualizado


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ufs", nargs="*", default=UFS)
    ap.add_argument("--suplentes", type=int, default=3)
    ap.add_argument("--eleicao", default=None, help="id da eleição no DivulgaCandContas")
    ap.add_argument("--saida", default=f"deputados_eleitos_suplentes_{ANO}.csv")
    ap.add_argument("--threads", type=int, default=8)
    args = ap.parse_args()

    eleicao = args.eleicao or eleicao_divulga(ELEICAO_DIVULGA_PADRAO)
    codigos = codigos_resultados()
    print(f"eleição DivulgaCandContas={eleicao}; códigos de resultados={codigos}", file=sys.stderr)

    tarefas = []
    for uf in [u.upper() for u in args.ufs]:
        cargos = [DEP_FEDERAL, DEP_DISTRITAL if uf == "DF" else DEP_ESTADUAL]
        for cargo in cargos:
            sel, total, atualizado = selecionar(uf, cargo, eleicao, codigos, args.suplentes)
            n_el = sum(1 for _, t, _ in sel if t == "Eleito")
            print(f"{uf} cargo {cargo}: {total} candidatos, {n_el} eleitos, "
                  f"{len(sel) - n_el} suplentes (totalização: {atualizado or 'n/d'})", file=sys.stderr)
            tarefas += [(uf, it, tipo, pos) for it, tipo, pos in sel]

    def montar(t):
        uf, it, tipo, pos = t
        c = it["cand"]
        f = ficha(uf, eleicao, c["id"])
        partido = f.get("partido") or c.get("partido") or {}
        return {
            "uf": uf,
            "cargo": (f.get("cargo") or c.get("cargo") or {}).get("nome", ""),
            "resultado": tipo,
            "ordem_suplencia": pos or "",
            "situacao_totalizacao": it["situacao"],
            "nome_completo": f.get("nomeCompleto") or c.get("nomeCompleto", ""),
            "nome_urna": f.get("nomeUrna") or c.get("nomeUrna", ""),
            "numero": f.get("numero") or c.get("numero", ""),
            "partido_sigla": partido.get("sigla", ""),
            "partido_nome": partido.get("nome", ""),
            "partido_federacao_coligacao": it["grupo"],
            "cpf": f.get("cpf", ""),
            "votos": it["votos"] if it["votos"] is not None else "",
            "id_candidato_tse": c["id"],
        }

    with ThreadPoolExecutor(args.threads) as ex:
        linhas = list(ex.map(montar, tarefas))

    ordem = {"Eleito": 0, "Suplente": 1}
    linhas.sort(key=lambda l: (l["uf"], l["cargo"], ordem[l["resultado"]],
                               l["partido_federacao_coligacao"], str(l["ordem_suplencia"]),
                               -(l["votos"] or 0)))
    with open(args.saida, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()) if linhas else ["uf"], delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    print(f"{len(linhas)} linhas gravadas em {args.saida}", file=sys.stderr)


if __name__ == "__main__":
    main()
