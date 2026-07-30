#!/usr/bin/env python3
"""
update_financeiro.py — atualiza o módulo Financeiro (A Pagar / Pago) no
dashboard unificado.

USO:
    # 1) Modo consulta (padrão) — só mostra o que mudaria, NÃO grava nada:
    python3 update_financeiro.py "Dashboard Financeiro vX.X.html"

    # 2) Modo aplicar — grava nos dois arquivos de produção:
    python3 update_financeiro.py "Dashboard Financeiro vX.X.html" --apply

Sempre rode primeiro SEM --apply, mostre o resultado para o Luiz, e só rode
de novo COM --apply depois da confirmação dele (regra do projeto) — a menos
que o diff seja claramente aditivo/mecânico (só registros novos, nenhum
removido ou alterado), caso em que já foi combinado que pode aplicar direto.

O que este script faz:
  1. Confere se o arquivo-fonte não está truncado.
  2. Compara `DATA.pagar` e `DATA.pago` do arquivo-fonte com o que já está
     em produção. Como esses registros não têm um campo de ID único, a
     comparação é feita por CONTEÚDO INTEIRO do registro (multiset — dois
     registros idênticos em todos os campos contam como "o mesmo").
  3. Reporta: quantos registros novos (aditivo), quantos sumiram (remoção,
     incomum — avisar o Luiz), e o valor total dos novos por empresa.
  4. Se --apply: substitui DATA.pagar e DATA.pago inteiros pelos do arquivo-
     fonte nos dois arquivos de produção, atualiza o timestamp em
     TAB_METAS.financeiro sozinho, e recalcula o card "Financeiro — A Pagar"
     do Daily Briefing (regra corrigida em 27/07/2026: o Luiz percebeu que o
     card ficava travado no "período" antigo mesmo com o módulo já atualizado
     — o card não é escrito automaticamente, cada script tem que recalcular o
     seu). Fórmula do card (reverse-engineered a partir do que já estava
     gravado, validada batendo com os números antigos antes de aplicar):
     pega a DATA MAIS RECENTE presente em DATA.pago (não é uma janela, é só
     "o último dia que teve pagamento"), soma "Apropriação Financeira" desse
     dia (= total), conta os registros desse dia (= qtd), e quebra por
     Empreendimento (não por Empresa) em ordem decrescente de valor (= itens).
"""
import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bundler_utils import (
    unpack, repack, load_source_text, module_bounds,
    extract_js_object_bounded, patch_tab_meta, patch_sidebar_footer, patch_briefing_header, now_local_str,
    find_briefing_card, write_briefing_card,
)


def _pd(s):
    d, m, y = s.split('/')
    return date(int(y), int(m), int(d))


def compute_financeiro_briefing_card(pago):
    """Card 'Financeiro — A Pagar' do Daily Briefing: dia mais recente presente
    em DATA.pago, total/qtd desse dia, quebra por Empreendimento (desc)."""
    datas = sorted({r.get('Data') for r in pago if r.get('Data')}, key=_pd)
    if not datas:
        return None
    ultima_data = datas[-1]
    recs = [r for r in pago if r.get('Data') == ultima_data]
    total = sum(r.get('Apropriação Financeira', 0) or 0 for r in recs)
    por_emp = Counter()
    for r in recs:
        por_emp[r.get('Empreendimento', '?')] += r.get('Apropriação Financeira', 0) or 0
    itens = [{'label': k, 'valor': round(v, 2)} for k, v in sorted(por_emp.items(), key=lambda x: -x[1])]
    return {
        'periodo': ultima_data,
        'total': round(total, 2),
        'qtd': len(recs),
        'itens': itens,
    }

PROD_FILES = [
    "Dashboard Grupo Delta v5.4.html",
    "index.txt",
]

JS_MARKER = '/* ==== Financeiro module ==== */'
JS_MARKER_NEXT = '/* ==== A Receber module ==== */'


def rec_key(r):
    """Chave por conteúdo inteiro do registro — não há ID único nesses dados."""
    return tuple(sorted(r.items()))


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


def load_new_data(fname):
    t = load_source_text(fname)
    lo, hi = 0, len(t)
    # arquivo-fonte standalone: só tem 1 módulo, não precisa de marcador —
    # mas usa a mesma função bounded pra reaproveitar a validação de bounds.
    data, _, _ = extract_js_object_bounded(t, 'const DATA', lo, hi)
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source_file', help='arquivo-fonte novo, ex: "Dashboard Financeiro v3.3.html"')
    ap.add_argument('--apply', action='store_true', help='grava as mudanças (sem isso, só mostra o diff)')
    args = ap.parse_args()

    new_data = load_new_data(args.source_file)
    if 'pagar' not in new_data or 'pago' not in new_data:
        raise ValueError(f"esperava chaves 'pagar'/'pago' em DATA, achei: {list(new_data.keys())}")

    t0, c0, tp0, tp02, te0 = unpack(PROD_FILES[0])
    js_lo, js_hi = module_bounds(t0, JS_MARKER, JS_MARKER_NEXT)
    prod_data, _, _ = extract_js_object_bounded(t0, 'const DATA', js_lo, js_hi)

    print("=== DIFF Financeiro ===")
    print(f"pagar: prod={len(prod_data['pagar'])} novo={len(new_data['pagar'])}")
    added_pagar, removed_pagar = diff_list(prod_data['pagar'], new_data['pagar'])
    print(f"  adicionados: {len(added_pagar)} | removidos: {len(removed_pagar)}")

    print(f"pago:  prod={len(prod_data['pago'])} novo={len(new_data['pago'])}")
    added_pago, removed_pago = diff_list(prod_data['pago'], new_data['pago'])
    print(f"  adicionados: {len(added_pago)} | removidos: {len(removed_pago)}")

    def resumo_por_empresa(recs, label):
        if not recs:
            return
        tot = sum(r.get('Apropriação Financeira', 0) or 0 for r in recs)
        print(f"\n{label}: {len(recs)} registro(s), total R$ {tot:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
        por_emp = Counter()
        for r in recs:
            por_emp[r.get('Empresa', '?')] += r.get('Apropriação Financeira', 0) or 0
        for emp, v in sorted(por_emp.items(), key=lambda x: -x[1]):
            print(f"    {emp}: R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
        datas = sorted(set(r.get('Data') for r in recs if r.get('Data')))
        if datas:
            print(f"    data(s): {', '.join(datas)}")

    resumo_por_empresa(added_pagar, "NOVOS em 'pagar'")
    resumo_por_empresa(removed_pagar, "REMOVIDOS de 'pagar' (incomum, confirme)")
    resumo_por_empresa(added_pago, "NOVOS em 'pago'")
    resumo_por_empresa(removed_pago, "REMOVIDOS de 'pago' (incomum, confirme)")

    if not (added_pagar or removed_pagar or added_pago or removed_pago):
        print("\nNenhuma mudança — provavelmente resalvamento sem dado novo.")

    puramente_aditivo = not removed_pagar and not removed_pago
    print(f"\nPuramente aditivo (sem remoções): {'sim' if puramente_aditivo else 'NÃO — tem remoção, avise o Luiz antes de aplicar'}")

    briefing_card = compute_financeiro_briefing_card(new_data['pago'])
    if briefing_card:
        print(f"\n=== Card 'Financeiro — A Pagar' do Daily Briefing (recalculado) ===")
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
        _, brace_start, brace_end = extract_js_object_bounded(t, 'const DATA', js_lo, js_hi)
        new_t = t[:brace_start] + json.dumps(new_data, ensure_ascii=False, separators=(',', ':')) + t[brace_end + 1:]
        new_t = patch_tab_meta(new_t, 'financeiro', now_str)
        new_t = patch_sidebar_footer(new_t)
        if briefing_card:
            card_obj, bstart, bend = find_briefing_card(new_t, 'financeiro')
            card_obj.update(briefing_card)
            card_obj['data_ref'] = hoje_str
            card_obj['hora'] = hora_str
            new_t = write_briefing_card(new_t, card_obj, bstart, bend)
        new_t = patch_briefing_header(new_t, now_str)
        new_c = repack(new_t, c, tp, te)
        Path(fpath).write_text(new_c, encoding='utf-8')
        print(f"  gravado: {fpath} ({len(new_c)} bytes)")

    print("\nTAB_METAS.financeiro atualizado automaticamente.")
    if briefing_card:
        print("Card 'Financeiro — A Pagar' do Daily Briefing recalculado e gravado automaticamente.")
    print("Falta só: validar com validate_dashboard.py (8 abas, zero erros) antes de entregar.")


if __name__ == '__main__':
    main()
