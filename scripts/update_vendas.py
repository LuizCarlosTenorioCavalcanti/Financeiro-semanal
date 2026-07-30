#!/usr/bin/env python3
"""
update_vendas.py — atualiza o módulo Vendas no dashboard unificado.

USO:
    # 1) Modo consulta (padrão) — só mostra o que mudaria, NÃO grava nada:
    python3 update_vendas.py "Dashboard_Vendas_vX.X.html"

    # 2) Modo aplicar — grava nos dois arquivos de produção:
    python3 update_vendas.py "Dashboard_Vendas_vX.X.html" --apply

Sempre rode primeiro SEM --apply, mostre o resultado para o Luiz, e só rode
de novo COM --apply depois da confirmação dele (regra do projeto).

O que este script faz:
  1. Confere se o arquivo-fonte não está truncado.
  2. Compara `DATA.base` (data de referência do arquivo) — se for igual ao que
     já está em produção, avisa que é um resalvamento sem dado novo (já
     aconteceu antes: o Luiz resalva o arquivo mas o `base` não avança, sem
     mudança real nenhuma).
  3. Compara `DATA.units` casando por (e, emp, u, tit), mostra os campos que
     mudaram por unidade (pago, ap, vc, pg, avm, vcm, vcl).
  4. Confere se o card de Vendas do Daily Briefing (período fixo, ver
     BRIEFING_VENDAS_PERIODO abaixo) precisa recálculo, olhando se algum
     pagamento (`pg`) das unidades alteradas cai dentro do período do card.
  5. Se --apply: substitui o DATA inteiro nos dois arquivos de produção,
     atualiza TAB_METAS.vendas e o rodapé do sidebar. Se o card do Daily
     Briefing precisar recálculo, avisa (não aplica sozinho — o período do
     card é fixo e definido manualmente com o Luiz, então pedir confirmação
     antes de mudar).
"""
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bundler_utils import unpack, repack, find_matching, extract_js_object, check_not_truncated, patch_tab_meta, patch_sidebar_footer, patch_briefing_header, now_local_str

PROD_FILES = [
    "Dashboard Grupo Delta v5.4.html",
    "index.txt",
]

# Período fixo do card "Vendas" no Daily Briefing — ajuste aqui se o Luiz pedir
# outra semana. Ver campo "periodo" do card em BRIEFING_DATA para o texto atual.
# Atualizado em 27/07/2026 (a pedido do Luiz): sempre a semana ANTERIOR à semana
# corrente (seg-sex), não uma data fixa esquecida no código — ajustar aqui de
# novo se ele quiser voltar a fixar numa semana específica.
BRIEFING_VENDAS_PERIODO = (date(2026, 7, 20), date(2026, 7, 24))


def key(u):
    return (u['e'], u['emp'], u['u'], u['tit'])


def find_vendas_data(text, start_from=0):
    """`const DATA=` também existe no módulo Financeiro (A Pagar) — não dá pra
    usar a primeira ocorrência. Procura especificamente a que começa com
    {"units": ..., que é a assinatura do objeto DATA do Vendas."""
    idx = start_from
    while True:
        idx = text.find('const DATA', idx)
        if idx == -1:
            raise ValueError("objeto DATA do Vendas não encontrado (esperava 'units' logo no começo)")
        eq = text.find('=', idx)
        j = eq + 1
        while text[j] in ' \n\t':
            j += 1
        if text[j] == '{' and text[j:j + 12].replace(' ', '').startswith('{"units"'):
            return j
        idx = eq + 1


def load_new_source(fname):
    check_not_truncated(fname)
    raw = open(fname, encoding='utf-8').read()
    if '<script type="__bundler/template">' in raw:
        t, _, _, _, _ = unpack(fname)
        search_in = t
    else:
        search_in = raw
    j = find_vendas_data(search_in)
    brace_end = find_matching(search_in, j, '{', '}')
    data = json.loads(search_in[j:brace_end + 1])
    return data


def diff_units(prod_units, new_units):
    prod_by_key = {key(u): u for u in prod_units}
    new_by_key = {key(u): u for u in new_units}

    added = set(new_by_key) - set(prod_by_key)
    removed = set(prod_by_key) - set(new_by_key)

    changed = []
    for k in prod_by_key:
        if k in new_by_key:
            pu, nu = prod_by_key[k], new_by_key[k]
            diffs = {f: (pu.get(f), nu.get(f)) for f in nu if pu.get(f) != nu.get(f)}
            if diffs:
                changed.append((k, diffs))

    return added, removed, changed


def week_touches_period(unit, lo, hi):
    for p in unit.get('pg', []):
        try:
            y, m, d = map(int, p[0].split('-'))
            if lo <= date(y, m, d) <= hi:
                return True
        except Exception:
            continue
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source_file', help='arquivo-fonte novo, ex: "Dashboard_Vendas_v1.2.html"')
    ap.add_argument('--apply', action='store_true', help='grava as mudanças (sem isso, só mostra o diff)')
    args = ap.parse_args()

    new_data = load_new_source(args.source_file)

    t0, c0, tp0, tp02, te0 = unpack(PROD_FILES[0])
    j0 = find_vendas_data(t0)
    brace_end0 = find_matching(t0, j0, '{', '}')
    prod_data = json.loads(t0[j0:brace_end0 + 1])

    print(f"=== DIFF Vendas ===")
    print(f"base: prod={prod_data.get('base')}  novo={new_data.get('base')}")
    if prod_data.get('base') == new_data.get('base'):
        print("MESMA DATA-BASE — provavelmente resalvamento sem dado novo (já aconteceu antes).")
        print("Confira o conteúdo mesmo assim antes de descartar.")

    added, removed, changed = diff_units(prod_data['units'], new_data['units'])
    print(f"unidades: prod={len(prod_data['units'])} novo={len(new_data['units'])}")
    print(f"adicionadas: {len(added)} | removidas: {len(removed)} | alteradas: {len(changed)}")

    for k, diffs in changed:
        print(f"\n  UNIDADE {k}:")
        for f, (old, new) in diffs.items():
            print(f"    {f}: {old!r} -> {new!r}")

    # KPIs agregados (mesma fórmula do renderCards() do próprio Vendas)
    def kpis(units):
        pago = sum(u.get('pago', 0) for u in units)
        vc = sum(u.get('vc', 0) for u in units)
        n_atraso = sum(1 for u in units if u.get('vc', 0) > 0.005)
        return pago, vc, n_atraso

    pago, vc, n_atraso = kpis(new_data['units'])
    print(f"\nKPIs (novo arquivo): Valor Pago={pago:.2f} | Em Atraso={vc:.2f} | Unidades em Atraso={n_atraso}")

    # Checa se o card fixo do Daily Briefing precisa recálculo
    lo, hi = BRIEFING_VENDAS_PERIODO
    touched_keys = {k for k, _ in changed} | added
    affects_briefing = False
    for k in touched_keys:
        u = next((u for u in new_data['units'] if key(u) == k), None)
        if u and week_touches_period(u, lo, hi):
            affects_briefing = True
            break
    print(f"\nCard fixo do Daily Briefing (período {lo.strftime('%d/%m')}-{hi.strftime('%d/%m/%Y')}): "
          + ("PODE TER MUDADO — recalcule o total/itens antes de fechar." if affects_briefing
             else "sem impacto (nenhuma unidade alterada tem pagamento nesse período)."))

    if not args.apply:
        print("\n[MODO CONSULTA] Nada foi gravado. Mostre isto ao Luiz; rode de novo com --apply após confirmação.")
        return

    print("\n[APLICANDO...]")
    now_str = now_local_str()
    for fpath in PROD_FILES:
        t, c, tp, tp2, te = unpack(fpath)
        brace_start = find_vendas_data(t)
        brace_end = find_matching(t, brace_start, '{', '}')
        new_t = t[:brace_start] + json.dumps(new_data, ensure_ascii=False, separators=(',', ':')) + t[brace_end + 1:]
        new_t = patch_tab_meta(new_t, 'vendas', now_str)
        new_t = patch_sidebar_footer(new_t)
        new_t = patch_briefing_header(new_t, now_str)
        new_c = repack(new_t, c, tp, te)
        Path(fpath).write_text(new_c, encoding='utf-8')
        print(f"  gravado: {fpath} ({len(new_c)} bytes)")

    print("\nTAB_METAS.vendas atualizado automaticamente.")
    if affects_briefing:
        print("RECALCULAR o card fixo do Daily Briefing (total/itens do período) — isso o script NÃO faz sozinho.")
    print("Falta só: validar com validate_dashboard.py (8 abas, zero erros) antes de entregar.")


if __name__ == '__main__':
    main()
