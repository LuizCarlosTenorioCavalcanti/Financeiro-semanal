#!/usr/bin/env python3
"""
update_comissoes.py — atualiza o módulo Comissão — Unidades no dashboard
unificado.

USO:
    # 1) Modo consulta (padrão) — só mostra o que mudaria, NÃO grava nada:
    python3 update_comissoes.py "Dashboard_Comissoes_vX.X.html"

    # 2) Modo aplicar — grava nos dois arquivos de produção:
    python3 update_comissoes.py "Dashboard_Comissoes_vX.X.html" --apply

Sempre rode primeiro SEM --apply, mostre o resultado para o Luiz, e só rode
de novo COM --apply depois da confirmação dele (regra do projeto) — a menos
que o diff seja claramente aditivo/mecânico.

CUIDADO ESPECIAL COM ESTE MÓDULO (achado em 28/07/2026): a comparação
depende de estar lendo o arquivo-fonte MAIS RECENTE de verdade. Já aconteceu
de comparar contra uma cópia em cache/desatualizada de uma leitura anterior
e concluir "0 diferenças" quando na verdade havia mudanças reais — o Luiz
corrigiu: "eu sempre tenho que criar um arquivo novo para voce identificar
as diferenças". Sempre reconferir tamanho/mtime do arquivo no dispositivo do
Luiz (device_list_dir) contra o arquivo que foi de fato lido antes de
reportar "sem mudanças".

O que este script faz:
  1. Confere se o arquivo-fonte não está truncado.
  2. Compara `const DADOS` (lista de pagamentos de comissão, sem ID único —
     comparação por CONTEÚDO INTEIRO do registro, multiset) com o que já está
     em produção.
  3. Reporta: registros novos (aditivo), registros removidos (incomum —
     avisar o Luiz; pode ser correção de um registro antigo, aparecendo como
     1 removido + 1 adicionado com os mesmos dados-chave mas campo(s)
     diferente(s) — vale checar manualmente esse caso).
  4. Se --apply: substitui `const DADOS` inteiro pelos do arquivo-fonte nos
     dois arquivos de produção, atualiza TAB_METAS.comissoes + rodapé do
     sidebar + cabeçalho do Daily Briefing, e recalcula o card
     "Comissão — Unidades" do Daily Briefing (fórmula abaixo).

FÓRMULA DO CARD "COMISSÃO — UNIDADES" NO DAILY BRIEFING
(reverse-engineered e validada em 28/07/2026 contra os números já gravados
em produção — período 11 a 17/07/2026, total R$ 95.858,21, 6 registros,
batendo exatamente antes de aplicar qualquer mudança):
  1. Acha o par (periodo_inicio, periodo_fim) MAIS RECENTE presente em DADOS
     (maior periodo_fim — os registros vêm agrupados em períodos semanais).
  2. Filtra os registros desse período exato.
  3. total = soma de valor_pago desses registros; qtd = quantidade deles.
  4. itens = soma de valor_pago agrupado por `empreendimento`, ordem
     decrescente de valor.
"""
import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bundler_utils import (
    unpack, repack, module_bounds, extract_js_object_bounded,
    patch_tab_meta, patch_sidebar_footer, patch_briefing_header, now_local_str,
    find_briefing_card, write_briefing_card, load_source_text,
)

PROD_FILES = [
    "Dashboard Grupo Delta v5.4.html",
    "index.txt",
]

JS_MARKER = '/* ==== Comissões module ==== */'
JS_MARKER_NEXT = '/* ==== Vendas module ==== */'


def pd(s):
    d, m, y = s.split('/')
    return date(int(y), int(m), int(d))


def rec_key(r):
    return json.dumps(r, sort_keys=True, ensure_ascii=False)


def diff_list(prod_list, new_list):
    prod_ct = Counter(rec_key(r) for r in prod_list)
    new_ct = Counter(rec_key(r) for r in new_list)
    added_ct = new_ct - prod_ct
    removed_ct = prod_ct - new_ct
    added = []
    for r in new_list:
        k = rec_key(r)
        if added_ct.get(k, 0) > 0:
            added.append(r)
            added_ct[k] -= 1
    removed = []
    for r in prod_list:
        k = rec_key(r)
        if removed_ct.get(k, 0) > 0:
            removed.append(r)
            removed_ct[k] -= 1
    return added, removed


def compute_comissoes_briefing_card(dados):
    """Card 'Comissão — Unidades': período (periodo_inicio,periodo_fim) mais
    recente presente em DADOS, total/qtd desse período, itens por
    empreendimento (desc)."""
    periodos = sorted(
        {(r['periodo_inicio'], r['periodo_fim']) for r in dados if r.get('periodo_fim')},
        key=lambda p: pd(p[1])
    )
    if not periodos:
        return None
    lo, hi = periodos[-1]
    recs = [r for r in dados if r.get('periodo_inicio') == lo and r.get('periodo_fim') == hi]
    total = sum(r.get('valor_pago', 0) or 0 for r in recs)
    por_emp = Counter()
    for r in recs:
        por_emp[r.get('empreendimento', '?')] += r.get('valor_pago', 0) or 0
    itens = [{'label': k, 'valor': round(v, 2)} for k, v in sorted(por_emp.items(), key=lambda x: -x[1])]
    return {
        'periodo': f'{lo} a {hi}',
        'total': round(total, 2),
        'qtd': len(recs),
        'itens': itens,
    }


def load_new_data(fname):
    t = load_source_text(fname)
    data, _, _ = extract_js_object_bounded(t, 'const DADOS', 0, len(t))
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source_file', help='arquivo-fonte novo, ex: "Dashboard_Comissoes_v1.2.html"')
    ap.add_argument('--apply', action='store_true', help='grava as mudanças (sem isso, só mostra o diff)')
    args = ap.parse_args()

    new_data = load_new_data(args.source_file)

    t0, c0, tp0, tp02, te0 = unpack(PROD_FILES[0])
    js_lo, js_hi = module_bounds(t0, JS_MARKER, JS_MARKER_NEXT)
    prod_data, _, _ = extract_js_object_bounded(t0, 'const DADOS', js_lo, js_hi)

    print("=== DIFF Comissões ===")
    print(f"registros: prod={len(prod_data)} novo={len(new_data)}")
    added, removed = diff_list(prod_data, new_data)
    print(f"adicionados: {len(added)} | removidos: {len(removed)}")

    def resumo(recs, label):
        if not recs:
            return
        tot = sum(r.get('valor_pago', 0) or 0 for r in recs)
        print(f"\n{label}: {len(recs)} registro(s), total R$ {tot:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
        for r in recs:
            print(f"    {r.get('data_pagamento')} | {r.get('empreendimento')} | {r.get('credor_imobiliaria')} | R$ {r.get('valor_pago'):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))

    resumo(added, "NOVOS/ALTERADOS")
    resumo(removed, "REMOVIDOS (confirme — pode ser versão antiga de um registro corrigido)")

    if not (added or removed):
        print("\nNenhuma mudança — provavelmente resalvamento sem dado novo (ou arquivo-fonte lido está desatualizado — reconfira com device_list_dir).")

    puramente_aditivo = not removed
    print(f"\nPuramente aditivo (sem remoções): {'sim' if puramente_aditivo else 'NÃO — tem remoção, avise o Luiz antes de aplicar'}")

    briefing_card = compute_comissoes_briefing_card(new_data)
    if briefing_card:
        print(f"\n=== Card 'Comissão — Unidades' do Daily Briefing (recalculado) ===")
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
        _, brace_start, brace_end = extract_js_object_bounded(t, 'const DADOS', js_lo, js_hi)
        new_t = t[:brace_start] + json.dumps(new_data, ensure_ascii=False, separators=(',', ':')) + t[brace_end + 1:]
        new_t = patch_tab_meta(new_t, 'comissoes', now_str)
        new_t = patch_sidebar_footer(new_t)
        if briefing_card:
            card_obj, bstart, bend = find_briefing_card(new_t, 'comissoes')
            card_obj.update(briefing_card)
            card_obj['data_ref'] = hoje_str
            card_obj['hora'] = hora_str
            new_t = write_briefing_card(new_t, card_obj, bstart, bend)
        new_t = patch_briefing_header(new_t, now_str)
        new_c = repack(new_t, c, tp, te)
        Path(fpath).write_text(new_c, encoding='utf-8')
        print(f"  gravado: {fpath} ({len(new_c)} bytes)")

    print("\nTAB_METAS.comissoes atualizado automaticamente.")
    if briefing_card:
        print("Card 'Comissão — Unidades' do Daily Briefing recalculado e gravado automaticamente.")
    print("Falta só: validar com validate_dashboard.py (8 abas, zero erros) antes de entregar.")


if __name__ == '__main__':
    main()
