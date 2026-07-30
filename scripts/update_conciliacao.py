#!/usr/bin/env python3
"""
update_conciliacao.py — atualiza o módulo Conciliação (RELATORIOS/PENDENCIAS)
no dashboard unificado.

USO:
    # 1) Modo consulta (padrão) — só mostra o que mudaria, NÃO grava nada:
    python3 update_conciliacao.py "Dashboard_Conciliacao_vX.X.html"

    # 2) Modo aplicar — grava nos dois arquivos de produção:
    python3 update_conciliacao.py "Dashboard_Conciliacao_vX.X.html" --apply

Sempre rode primeiro SEM --apply, mostre o resultado para o Luiz, e só rode
de novo COM --apply depois da confirmação dele — a menos que o diff seja
claramente a troca normal do relatório do dia (ver observação abaixo).

O que este script faz:
  1. Confere se o arquivo-fonte não está truncado.
  2. Compara `RELATORIOS` (uma foto do dia por empresa — normalmente é uma
     TROCA COMPLETA a cada rodada: os 3 relatórios de ontem saem, entram os
     3 de hoje, não é uma lista que cresce), `PENDENCIAS` (lista curta de
     observações manuais; pode ganhar ou perder itens conforme problemas são
     resolvidos ou aparecem) e `INVESTIMENTOS` (mesma ideia de RELATORIOS, mas
     pras contas de investimento — campo separado, ADICIONADO em 27/07/2026:
     até então o script não lia nem gravava isso, e ficou 3 dias sem atualizar
     em produção mesmo com o arquivo-fonte já trazendo dado novo, porque
     ninguém tinha percebido que INVESTIMENTOS é uma variável própria, não faz
     parte de RELATORIOS. `INVESTIMENTOS` é OPCIONAL — nem todo arquivo-fonte
     precisa ter, trata como ausente se não encontrar).
  3. Reporta, por empresa: saldo bancário e de investimento (prod vs novo),
     destacando mudanças grandes de saldo (>20%) pra revisão manual — isso já
     aconteceu (saldo mudou de -475mil pra +1,17mi porque um valor não
     conciliado de R$339mil foi corrigido) e é sempre bom o Luiz confirmar
     que a mudança é real antes de aplicar.
  4. Se --apply: substitui RELATORIOS, PENDENCIAS e INVESTIMENTOS (quando
     presente) inteiros pelos do arquivo-fonte nos dois arquivos de produção,
     atualiza o timestamp em TAB_METAS.conciliacao sozinho, e recalcula o card
     "Conciliação — Balanço" do Daily Briefing (regra corrigida em 27/07/2026,
     mesmo motivo do card do Financeiro — ver update_financeiro.py: cada
     script tem que recalcular seu próprio card, nunca fica automático).
     Fórmula do card: período = data_relatorio mais recente entre os
     RELATORIOS; para cada empresa, banco = soma dos saldos das contas em
     RELATORIOS, investido = soma dos saldos das contas em INVESTIMENTOS
     (0 se a empresa não tiver investimento), total = banco + investido.
"""
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bundler_utils import (
    unpack, repack, load_source_text, module_bounds,
    extract_js_object_bounded, patch_tab_meta, patch_sidebar_footer, patch_briefing_header, now_local_str,
    find_briefing_card, write_briefing_card,
)

PROD_FILES = [
    "Dashboard Grupo Delta v5.4.html",
    "index.txt",
]

JS_MARKER = '/* ==== Conciliação module ==== */'
JS_MARKER_NEXT = '/* ==== Comissões module ==== */'

SALDO_ALERTA_PCT = 0.20  # avisa se saldo total de uma empresa mudar mais que isso


def rel_key(r):
    return r.get('arquivo')


def totais(rel):
    saldo = sum(a.get('saldo', 0) for a in rel.get('contas', []))
    nao_conc = sum(a.get('nao_conc', 0) for a in rel.get('contas', []))
    return saldo, nao_conc


def _pd(s):
    d, m, y = s.split('/')
    return date(int(y), int(m), int(d))


def load_investimentos(t_src):
    """INVESTIMENTOS é opcional — nem todo arquivo-fonte traz. Devolve [] se
    não encontrar, em vez de quebrar (mesmo padrão do extraInfo em Contratos)."""
    try:
        inv, _, _ = extract_js_object_bounded(t_src, 'const INVESTIMENTOS', 0, len(t_src))
        return inv
    except ValueError:
        return None


def compute_conciliacao_briefing_card(rel, inv):
    """Card 'Conciliação — Balanço' do Daily Briefing: período = data_relatorio
    mais recente em RELATORIOS; por empresa, banco (soma RELATORIOS.contas.saldo)
    + investido (soma INVESTIMENTOS.contas.saldo, 0 se a empresa não tiver)."""
    if not rel:
        return None
    datas = sorted({r.get('data_relatorio') for r in rel if r.get('data_relatorio')}, key=_pd)
    periodo = datas[-1] if datas else None
    inv_by_emp = {}
    for i in (inv or []):
        inv_by_emp[i.get('empresa')] = sum(c.get('saldo', 0) for c in i.get('contas', []))
    empresas = []
    for r in rel:  # preserva a ordem de RELATORIOS (convenção já usada no card)
        emp = r.get('empresa')
        if any(e['nome'] == emp for e in empresas):
            continue
        banco = sum(c.get('saldo', 0) for c in r.get('contas', []))
        investido = inv_by_emp.get(emp, 0)
        empresas.append({'nome': emp, 'banco': round(banco, 2), 'investido': round(investido, 2), 'total': round(banco + investido, 2)})
    return {'periodo': periodo, 'empresas': empresas}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source_file', help='arquivo-fonte novo, ex: "Dashboard_Conciliacao_v2.4.html"')
    ap.add_argument('--apply', action='store_true', help='grava as mudanças (sem isso, só mostra o diff)')
    args = ap.parse_args()

    t_src = load_source_text(args.source_file)
    new_rel, _, _ = extract_js_object_bounded(t_src, 'const RELATORIOS', 0, len(t_src))
    new_pend, _, _ = extract_js_object_bounded(t_src, 'const PENDENCIAS', 0, len(t_src))
    new_inv = load_investimentos(t_src)

    t0, c0, tp0, tp02, te0 = unpack(PROD_FILES[0])
    js_lo, js_hi = module_bounds(t0, JS_MARKER, JS_MARKER_NEXT)
    prod_rel, _, _ = extract_js_object_bounded(t0, 'const RELATORIOS', js_lo, js_hi)
    prod_pend, _, _ = extract_js_object_bounded(t0, 'const PENDENCIAS', js_lo, js_hi)
    try:
        prod_inv, _, _ = extract_js_object_bounded(t0, 'const INVESTIMENTOS', js_lo, js_hi)
    except ValueError:
        prod_inv = None

    print("=== DIFF Conciliação ===")
    prod_by_arquivo = {rel_key(r): r for r in prod_rel}
    new_by_arquivo = {rel_key(r): r for r in new_rel}
    print(f"RELATORIOS: prod={len(prod_rel)} novo={len(new_rel)}")
    print(f"  arquivos novos: {sorted(set(new_by_arquivo) - set(prod_by_arquivo))}")
    print(f"  arquivos que saíram: {sorted(set(prod_by_arquivo) - set(new_by_arquivo))}")

    print("\nPor empresa (saldo total / não conciliado):")
    empresas = sorted(set(r.get('empresa') for r in prod_rel) | set(r.get('empresa') for r in new_rel))
    alertas = []
    for emp in empresas:
        rp = next((r for r in prod_rel if r.get('empresa') == emp), None)
        rn = next((r for r in new_rel if r.get('empresa') == emp), None)
        sp, ncp = totais(rp) if rp else (None, None)
        sn, ncn = totais(rn) if rn else (None, None)
        def fmtv(v):
            return '—' if v is None else ('R$ ' + f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))
        print(f"  {emp}: saldo {fmtv(sp)} -> {fmtv(sn)}  |  não concil. {fmtv(ncp)} -> {fmtv(ncn)}"
              + (f"  (data: {rp.get('data_relatorio')} -> {rn.get('data_relatorio')})" if rp and rn else ""))
        if sp is not None and sn is not None and sp != 0:
            variacao = abs(sn - sp) / abs(sp)
            if variacao > SALDO_ALERTA_PCT:
                alertas.append(f"{emp}: saldo variou {variacao*100:.0f}% ({fmtv(sp)} -> {fmtv(sn)}) — CONFIRME antes de aplicar")

    print(f"\nPENDENCIAS: prod={len(prod_pend)} novo={len(new_pend)}")
    prod_pend_set = {json.dumps(p, sort_keys=True, ensure_ascii=False) for p in prod_pend}
    new_pend_set = {json.dumps(p, sort_keys=True, ensure_ascii=False) for p in new_pend}
    added_pend = [p for p in new_pend if json.dumps(p, sort_keys=True, ensure_ascii=False) not in prod_pend_set]
    removed_pend = [p for p in prod_pend if json.dumps(p, sort_keys=True, ensure_ascii=False) not in new_pend_set]
    if added_pend:
        print("  NOVAS pendências:")
        for p in added_pend:
            print(f"    - {p.get('empresa')} / {p.get('conta_busca')}: {p.get('comentario', '')[:80]}")
    if removed_pend:
        print("  Pendências RESOLVIDAS (saíram da lista):")
        for p in removed_pend:
            print(f"    - {p.get('empresa')} / {p.get('conta_busca')}: {p.get('comentario', '')[:80]}")
    if not added_pend and not removed_pend:
        print("  sem mudança")

    if new_inv is None:
        print("\nINVESTIMENTOS: não encontrado no arquivo-fonte (campo opcional) — não vou mexer no que já está em produção.")
    else:
        print(f"\nINVESTIMENTOS: prod={'—' if prod_inv is None else len(prod_inv)} novo={len(new_inv)}")
        for i in new_inv:
            emp = i.get('empresa')
            ip = next((x for x in (prod_inv or []) if x.get('empresa') == emp), None)
            sp = sum(c.get('saldo', 0) for c in ip.get('contas', [])) if ip else None
            sn = sum(c.get('saldo', 0) for c in i.get('contas', []))
            def fmtv(v):
                return '—' if v is None else ('R$ ' + f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))
            print(f"  {emp}: investido {fmtv(sp)} -> {fmtv(sn)}"
                  + (f"  (data: {ip.get('data_relatorio')} -> {i.get('data_relatorio')})" if ip else ""))
            # ALERTA (achado em 30/07/2026: faltava aqui — só o saldo bancário
            # de RELATORIOS era checado contra SALDO_ALERTA_PCT, nunca o
            # investido; um caso real de INVESTIMENTOS variando -96%/+360% no
            # MESMO dia passou batido até o Luiz confirmar manualmente).
            if sp is not None and sn is not None and sp != 0:
                variacao = abs(sn - sp) / abs(sp)
                if variacao > SALDO_ALERTA_PCT:
                    alertas.append(f"{emp} (investido): variou {variacao*100:.0f}% ({fmtv(sp)} -> {fmtv(sn)}) — CONFIRME antes de aplicar")

    if alertas:
        print("\n*** ALERTAS (variação grande de saldo/investido) ***")
        for a in alertas:
            print(f"  - {a}")

    briefing_card = compute_conciliacao_briefing_card(new_rel, new_inv if new_inv is not None else prod_inv)
    if briefing_card:
        print(f"\n=== Card 'Conciliação — Balanço' do Daily Briefing (recalculado) ===")
        print(f"  periodo: {briefing_card['periodo']}")
        for e in briefing_card['empresas']:
            print(f"    {e['nome']}: banco R$ {e['banco']:,.2f} + investido R$ {e['investido']:,.2f} = R$ {e['total']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))

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

        _, rj, rend = extract_js_object_bounded(t, 'const RELATORIOS', js_lo, js_hi)
        new_t = t[:rj] + json.dumps(new_rel, ensure_ascii=False, separators=(',', ':')) + t[rend + 1:]

        js_lo2, js_hi2 = module_bounds(new_t, JS_MARKER, JS_MARKER_NEXT)
        _, pj, pend = extract_js_object_bounded(new_t, 'const PENDENCIAS', js_lo2, js_hi2)
        new_t2 = new_t[:pj] + json.dumps(new_pend, ensure_ascii=False, separators=(',', ':')) + new_t[pend + 1:]

        if new_inv is not None:
            js_lo3, js_hi3 = module_bounds(new_t2, JS_MARKER, JS_MARKER_NEXT)
            _, ij, iend = extract_js_object_bounded(new_t2, 'const INVESTIMENTOS', js_lo3, js_hi3)
            new_t2 = new_t2[:ij] + json.dumps(new_inv, ensure_ascii=False, separators=(',', ':')) + new_t2[iend + 1:]

        new_t2 = patch_tab_meta(new_t2, 'conciliacao', now_str)
        new_t2 = patch_sidebar_footer(new_t2)
        if briefing_card:
            card_obj, bstart, bend = find_briefing_card(new_t2, 'conciliacao')
            card_obj.update(briefing_card)
            card_obj['data_ref'] = hoje_str
            card_obj['hora'] = hora_str
            new_t2 = write_briefing_card(new_t2, card_obj, bstart, bend)
        new_t2 = patch_briefing_header(new_t2, now_str)
        new_c = repack(new_t2, c, tp, te)
        Path(fpath).write_text(new_c, encoding='utf-8')
        print(f"  gravado: {fpath} ({len(new_c)} bytes)")

    print("\nTAB_METAS.conciliacao atualizado automaticamente.")
    if briefing_card:
        print("Card 'Conciliação — Balanço' do Daily Briefing recalculado e gravado automaticamente.")
    print("Falta só: validar com validate_dashboard.py (8 abas, zero erros) antes de entregar.")


if __name__ == '__main__':
    main()
