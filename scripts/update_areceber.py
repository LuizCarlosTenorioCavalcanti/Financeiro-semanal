#!/usr/bin/env python3
"""
update_areceber.py — atualiza o módulo Financeiro / A Receber no dashboard
unificado. Não existia até 29/07/2026 (a documentação dizia que esse diff
ainda era manual) — criado seguindo o mesmo padrão de update_financeiro.py.

USO:
    python3 update_areceber.py "Dashboard A Receber vX.X.html"            # consulta
    python3 update_areceber.py "Dashboard A Receber vX.X.html" --apply    # grava

Schema: `const RAW` é uma lista achatada (sem ID único), cada registro tem
ano/mes/dia_ini/dia_fim/empresa/empreendimento/apropriacoes/total_geral/
mensal/emprestimo_pj. Um "período" (semana ou mês) agrupa vários registros
(um por empreendimento) que compartilham (ano,mes,dia_ini,dia_fim).

Card 'Financeiro — A Receber' do Daily Briefing: pega o(s) registro(s) do
período mais recente presente (maior tupla (ano,mes,dia_ini,dia_fim)), soma
total_geral = total, conta registros = qtd, quebra por empreendimento (desc)
= itens, e monta 'periodo' como "{dia_ini} a {dia_fim}/{mes:02d}/{ano}"
(confirmado batendo com o valor já gravado em produção: "13 a 17/07/2026").

IMPORTANTE (achado em 29/07/2026): o arquivo-FONTE standalone grava `const
RAW` como literal JS com chaves SEM aspas (`{ano:2024,mes:1,...}`), não JSON
válido — só o `apropriacoes` interno usa chave entre aspas (ex: "1.01.01",
porque não é um identificador válido). `json.loads` direto falha. Já a
produção (depois de desempacotado) sempre tem JSON válido (é gravado por
`json.dumps` no --apply anterior). Por isso este script usa um parser
tolerante (`_load_js_array`, via regex `([{,]\s*)([A-Za-z_]\w*)(\s*:)` pra
adicionar aspas nas chaves antes do `json.loads`) só pro arquivo-FONTE — a
leitura da produção continua usando `extract_js_object_bounded` normal.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bundler_utils import (
    unpack, repack, load_source_text, module_bounds, find_matching,
    extract_js_object_bounded, patch_tab_meta, patch_sidebar_footer, patch_briefing_header, now_local_str,
    find_briefing_card, write_briefing_card,
)


def _load_js_array(text, var_name):
    """Extrai um array JS que pode ter chaves de objeto sem aspas (comum em
    arquivos-fonte editados/exportados à mão) e devolve como lista Python."""
    idx = text.find(var_name)
    if idx == -1:
        raise ValueError(f"'{var_name}' não encontrado no arquivo-fonte")
    eq = text.find('=', idx)
    j = eq + 1
    while text[j] in ' \n\t':
        j += 1
    if text[j] != '[':
        raise ValueError(f"esperava '[' logo após '{var_name} =', achei {text[j]!r}")
    end = find_matching(text, j, '[', ']')
    literal = text[j:end + 1]
    fixed = re.sub(r'([{,]\s*)([A-Za-z_]\w*)(\s*:)', r'\1"\2"\3', literal)
    return json.loads(fixed)

PROD_FILES = [
    "Dashboard Grupo Delta v5.4.html",
    "index.txt",
]

JS_MARKER = '/* ==== A Receber module ==== */'
JS_MARKER_NEXT = '/* ==== Conciliação module ==== */'


def rec_key(r):
    """Chave por conteúdo inteiro do registro (via JSON, já que tem um dict
    aninhado 'apropriacoes' que não é hashable direto)."""
    return json.dumps(r, sort_keys=True, ensure_ascii=False)


def diff_list(prod_list, new_list):
    prod_ct = Counter(rec_key(r) for r in prod_list)
    new_ct = Counter(rec_key(r) for r in new_list)
    added_ct = new_ct - prod_ct
    removed_ct = prod_ct - new_ct
    added = []
    remaining = Counter(added_ct)
    for r in new_list:
        k = rec_key(r)
        if remaining.get(k, 0) > 0:
            added.append(r)
            remaining[k] -= 1
    removed = []
    remaining = Counter(removed_ct)
    for r in prod_list:
        k = rec_key(r)
        if remaining.get(k, 0) > 0:
            removed.append(r)
            remaining[k] -= 1
    return added, removed


def load_new_data(fname):
    t = load_source_text(fname)
    return _load_js_array(t, 'const RAW')


def periodo_key(r):
    return (r.get('ano', 0), r.get('mes', 0), r.get('dia_ini', 0), r.get('dia_fim', 0))


def compute_areceber_briefing_card(raw):
    if not raw:
        return None
    latest_key = max(periodo_key(r) for r in raw)
    recs = [r for r in raw if periodo_key(r) == latest_key]
    ano, mes, dia_ini, dia_fim = latest_key
    total = sum(r.get('total_geral', 0) or 0 for r in recs)
    por_emp = Counter()
    for r in recs:
        por_emp[r.get('empreendimento', '?')] += r.get('total_geral', 0) or 0
    itens = [{'label': k, 'valor': round(v, 2)} for k, v in sorted(por_emp.items(), key=lambda x: -x[1])]
    periodo_str = f"{dia_ini} a {dia_fim}/{mes:02d}/{ano}" if dia_ini != dia_fim else f"{dia_ini}/{mes:02d}/{ano}"
    return {
        'periodo': periodo_str,
        'total': round(total, 2),
        'qtd': len(recs),
        'itens': itens,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source_file', help='arquivo-fonte novo, ex: "Dashboard A Receber v2.3.html"')
    ap.add_argument('--apply', action='store_true', help='grava as mudanças (sem isso, só mostra o diff)')
    args = ap.parse_args()

    new_data = load_new_data(args.source_file)

    t0, c0, tp0, tp02, te0 = unpack(PROD_FILES[0])
    js_lo, js_hi = module_bounds(t0, JS_MARKER, JS_MARKER_NEXT)
    prod_data, _, _ = extract_js_object_bounded(t0, 'const RAW', js_lo, js_hi)

    print("=== DIFF A Receber ===")
    print(f"registros: prod={len(prod_data)} novo={len(new_data)}")
    added, removed = diff_list(prod_data, new_data)
    print(f"adicionados: {len(added)} | removidos: {len(removed)}")

    def resumo_por_empresa(recs, label):
        if not recs:
            return
        tot = sum(r.get('total_geral', 0) or 0 for r in recs)
        print(f"\n{label}: {len(recs)} registro(s), total R$ {tot:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
        por_emp = Counter()
        for r in recs:
            por_emp[r.get('empreendimento', '?')] += r.get('total_geral', 0) or 0
        for emp, v in sorted(por_emp.items(), key=lambda x: -x[1]):
            print(f"    {emp}: R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))

    resumo_por_empresa(added, "NOVOS")
    resumo_por_empresa(removed, "REMOVIDOS (incomum, confirme)")

    if not added and not removed:
        print("\nNenhuma mudança — provavelmente resalvamento sem dado novo.")

    puramente_aditivo = not removed
    print(f"\nPuramente aditivo (sem remoções): {'sim' if puramente_aditivo else 'NÃO — tem remoção, avise o Luiz antes de aplicar'}")

    briefing_card = compute_areceber_briefing_card(new_data)
    if briefing_card:
        print(f"\n=== Card 'Financeiro — A Receber' do Daily Briefing (recalculado) ===")
        print(f"  periodo: {briefing_card['periodo']}  |  total: R$ {briefing_card['total']:,.2f}  |  qtd: {briefing_card['qtd']}".replace(',', 'X').replace('.', ',').replace('X', '.'))
        for it in briefing_card['itens']:
            print(f"    {it['label']}: R$ {it['valor']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))

    if not args.apply:
        print("\n[MODO CONSULTA] Nada foi gravado. Mostre isto ao Luiz; rode de novo com --apply após confirmação.")
        return

    print("\n[APLICANDO...]")
    now_str = now_local_str()
    hoje_str = now_str.split(': ')[1].split(' às ')[0]
    hora_str = now_str.split(' às ')[1]
    for fpath in PROD_FILES:
        t, c, tp, tp2, te = unpack(fpath)
        js_lo, js_hi = module_bounds(t, JS_MARKER, JS_MARKER_NEXT)
        _, brace_start, brace_end = extract_js_object_bounded(t, 'const RAW', js_lo, js_hi)
        new_t = t[:brace_start] + json.dumps(new_data, ensure_ascii=False, separators=(',', ':')) + t[brace_end + 1:]
        new_t = patch_tab_meta(new_t, 'areceber', now_str)
        new_t = patch_sidebar_footer(new_t)
        if briefing_card:
            card_obj, bstart, bend = find_briefing_card(new_t, 'areceber')
            card_obj.update(briefing_card)
            card_obj['data_ref'] = hoje_str
            card_obj['hora'] = hora_str
            new_t = write_briefing_card(new_t, card_obj, bstart, bend)
        new_t = patch_briefing_header(new_t, now_str)
        new_c = repack(new_t, c, tp, te)
        Path(fpath).write_text(new_c, encoding='utf-8')
        print(f"  gravado: {fpath} ({len(new_c)} bytes)")

    print("\nTAB_METAS.areceber atualizado automaticamente.")
    if briefing_card:
        print("Card 'Financeiro — A Receber' do Daily Briefing recalculado e gravado automaticamente.")
    print("Falta só: validar com validate_dashboard.py (8 abas, zero erros) antes de entregar.")


if __name__ == '__main__':
    main()
