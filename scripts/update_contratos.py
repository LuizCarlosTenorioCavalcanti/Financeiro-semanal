#!/usr/bin/env python3
"""
update_contratos.py — atualiza o módulo Contratos no dashboard unificado.

USO:
    # 1) Modo consulta (padrão) — só mostra o que mudaria, NÃO grava nada:
    python3 update_contratos.py "Dashboard Contratos vX.X.html"

    # 2) Modo aplicar — grava nos dois arquivos de produção:
    python3 update_contratos.py "Dashboard Contratos vX.X.html" --apply

Sempre rode primeiro SEM --apply, mostre o resultado para o Luiz, e só rode
de novo COM --apply depois da confirmação dele (regra do projeto).

O que este script faz:
  1. Confere se o arquivo-fonte não está truncado.
  2. Compara `dashboardData.contratos` do arquivo-fonte com o que já está
     em produção, casando registros por (nome, empreendimento, obra_apto).
  3. Separa as mudanças em duas categorias:
       - "bug conhecido": só os campos dias_solicitar_itbi, dias_entregar_cartorio,
         dias_processo_agencia, dias_aguardando_agencia, tempo_total mudaram, e o
         novo valor é absurdo (abs > 1000). Isso vem de data em branco no Sienge,
         não é dado real — o script já neutraliza sozinho (vira null), inclusive
         revertendo situacao_cartorio se ele guinou OK->ATRASADO só por causa disso.
       - "mudança real": qualquer outro campo mudou. Isso É reportado para o Luiz
         confirmar, nunca aplicado sem mostrar antes.
  4. Se --apply: mescla os dados corrigidos nos dois arquivos de produção,
     atualiza extraInfo (reg_ulysses/reg_eunapio), recalcula o card "Contratos —
     Gestão" do Daily Briefing (ver fórmulas abaixo) e atualiza TAB_METAS +
     rodapé do sidebar.

FÓRMULAS DO CARD "CONTRATOS — GESTÃO" NO DAILY BRIEFING
(reverse-engineered e validadas contra os números históricos; a regra dos
campos "_novo" foi corrigida em 24/07/2026 — ver observação abaixo):

  contrato_sienge_total       = conta contratos com data_contrato_sienge preenchida
                                 E data_assinatura vazia (ainda não assinado)
  contrato_sienge_novo        = conta contratos com data_contrato_sienge == HOJE
  assinados_novo              = conta contratos com data_assinatura == HOJE
  assinados_triagem_total     = conta contratos com etapa_itbi == 'TRIAGEM'
  itbi_solicitado_total       = conta contratos com etapa_itbi == 'ITBI SOLICITADO'
  itbi_solicitado_atrasados   = conta contratos com etapa=='ITBI' E situacao_itbi=='ATRASADO'
  cartorio_protocolado_total  = conta contratos com etapa=='CARTÓRIO'
  cartorio_protocolado_atrasados = conta contratos com etapa=='CARTÓRIO' E situacao_cartorio=='ATRASADO'
  cartorio_protocolado_novo   = conta contratos com data_entrada_cartorio == HOJE
  cartorio_registrado_novo    = extraInfo.reg_ulysses + extraInfo.reg_eunapio (vem pronto do arquivo-fonte)
  entregue_agencia_total      = conta contratos com data_entregue_agencia == HOJE
  entregue_agencia_atrasados  = idem, E situacao_agencia == 'ATRASADO'
  credito_liberado            = conta contratos com data_credito == HOJE

  *** REGRA IMPORTANTE (corrigida em 24/07/2026, confirmada pelo Luiz) ***
  Todos os campos "_novo" (e os quase-"_novo" acima, mesmo sem o sufixo:
  entregue_agencia_total/atrasados, credito_liberado) usam SÓ O DIA de hoje
  (extraInfo.today), não uma janela de 2 dias. Isso é diferente do
  `janela_recente` do topo do BRIEFING_DATA (que controla se o CARD inteiro
  aparece em "recente" vs "anterior" — esse sim é uma janela de 2 dias,
  "hoje + dia útil anterior"). São dois conceitos diferentes, não confundir.

  Os totais "_total" (contrato_sienge_total, itbi_solicitado_total,
  cartorio_protocolado_total, assinados_triagem_total) são uma FOTO do estado
  atual, não usam janela nenhuma.

BUG CONHECIDO (dias_* / tempo_total):
  O export do Sienge calcula esses 5 campos contra uma data padrão/época
  quando a data real está em branco, gerando valores tipo 46226 (~126 anos)
  ou negativos grandes tipo -45000. Regra de correção: para cada registro,
  qualquer um desses 5 campos com abs(valor) > 1000 vira null. Se
  situacao_cartorio também virou (ex: OK->ATRASADO) só por causa disso no
  mesmo registro, reverte para o valor antigo também.
"""
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bundler_utils import unpack, repack, find_matching, extract_js_object, check_not_truncated

PROD_FILES = [
    "Dashboard Grupo Delta v5.4.html",
    "index.txt",
]

DIAS_FIELDS = [
    'dias_solicitar_itbi', 'dias_entregar_cartorio',
    'dias_processo_agencia', 'dias_aguardando_agencia', 'tempo_total',
]
ABSURD_THRESHOLD = 1000


def key(r):
    return (r.get('nome'), r.get('empreendimento'), r.get('obra_apto'))


def pd(s):
    if not s:
        return None
    d, m, y = s.split('/')
    return date(int(y), int(m), int(d))


def load_new_source(fname):
    check_not_truncated(fname)
    raw = open(fname, encoding='utf-8').read()
    # pode vir empacotado (__bundler) ou HTML puro — tenta os dois
    if '<script type="__bundler/template">' in raw:
        t, _, _, _, _ = unpack(fname)
        search_in = t
    else:
        search_in = raw
    dd, _, _ = extract_js_object(search_in, 'dashboardData')
    # extraInfo pode não existir em toda fonte; trata como opcional
    try:
        extra, _, _ = extract_js_object(search_in, 'extraInfo')
    except ValueError:
        extra = None
    return dd, extra


def load_prod_dashboard_data(text):
    dd, brace_start, brace_end = extract_js_object(text, 'dashboardData')
    return dd, brace_start, brace_end


def diff_and_fix(prod_contratos, new_dd):
    prod_by_key = {}
    for r in prod_contratos:
        prod_by_key.setdefault(key(r), []).append(r)

    new_by_key = {}
    for r in new_dd['contratos']:
        new_by_key.setdefault(key(r), []).append(r)

    added = set(new_by_key) - set(prod_by_key)
    removed = set(prod_by_key) - set(new_by_key)

    fixed_contratos = []
    bugfixed_count = 0
    cartorio_reverted = 0
    real_changes = []

    for r in new_dd['contratos']:
        r2 = dict(r)
        k = key(r2)
        old_matches = prod_by_key.get(k)
        old = old_matches[0] if old_matches and len(old_matches) == 1 else None

        touched = False
        for f in DIAS_FIELDS:
            v = r2.get(f)
            if v is not None and abs(v) > ABSURD_THRESHOLD:
                r2[f] = None
                touched = True
        if touched:
            bugfixed_count += 1

        if old is not None:
            diffs = {f: (old.get(f), r2.get(f)) for f in r2 if old.get(f) != r2.get(f)}
            if touched and old.get('situacao_cartorio') != r2.get('situacao_cartorio'):
                r2['situacao_cartorio'] = old['situacao_cartorio']
                cartorio_reverted += 1
                diffs.pop('situacao_cartorio', None)
            # recalcula diffs "reais" (excluindo os 5 campos de dias_* que o bugfix já tratou)
            real_diffs = {f: v for f, v in diffs.items() if f not in DIAS_FIELDS}
            if real_diffs:
                real_changes.append((k, real_diffs))

        fixed_contratos.append(r2)

    return {
        'contratos': fixed_contratos,
        'empreendimentos': new_dd['empreendimentos'],
        'timestamp': new_dd['timestamp'],
    }, {
        'added': added, 'removed': removed,
        'bugfixed_count': bugfixed_count, 'cartorio_reverted': cartorio_reverted,
        'real_changes': real_changes,
    }


def compute_briefing_card(contratos, today_str):
    today = pd(today_str)

    def is_today(s):
        return pd(s) == today

    return dict(
        contrato_sienge_novo=sum(1 for r in contratos if is_today(r.get('data_contrato_sienge'))),
        contrato_sienge_total=sum(1 for r in contratos if r.get('data_contrato_sienge') and not r.get('data_assinatura')),
        assinados_novo=sum(1 for r in contratos if is_today(r.get('data_assinatura'))),
        assinados_triagem_total=sum(1 for r in contratos if r.get('etapa_itbi') == 'TRIAGEM'),
        itbi_solicitado_total=sum(1 for r in contratos if r.get('etapa_itbi') == 'ITBI SOLICITADO'),
        itbi_solicitado_atrasados=sum(1 for r in contratos if r.get('etapa') == 'ITBI' and r.get('situacao_itbi') == 'ATRASADO'),
        cartorio_protocolado_novo=sum(1 for r in contratos if is_today(r.get('data_entrada_cartorio'))),
        cartorio_protocolado_total=sum(1 for r in contratos if r.get('etapa') == 'CARTÓRIO'),
        cartorio_protocolado_atrasados=sum(1 for r in contratos if r.get('etapa') == 'CARTÓRIO' and r.get('situacao_cartorio') == 'ATRASADO'),
        entregue_agencia_total=sum(1 for r in contratos if is_today(r.get('data_entregue_agencia'))),
        entregue_agencia_atrasados=sum(1 for r in contratos if is_today(r.get('data_entregue_agencia')) and r.get('situacao_agencia') == 'ATRASADO'),
        credito_liberado=sum(1 for r in contratos if is_today(r.get('data_credito'))),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source_file', help='arquivo-fonte novo, ex: "Dashboard Contratos v3.5.html"')
    ap.add_argument('--apply', action='store_true', help='grava as mudanças (sem isso, só mostra o diff)')
    args = ap.parse_args()

    new_dd, new_extra = load_new_source(args.source_file)

    # usa o primeiro arquivo de produção como referência para o diff
    t0, c0, tp0, tp02, te0 = unpack(PROD_FILES[0])
    prod_dd, _, _ = load_prod_dashboard_data(t0)

    fixed_dd, report = diff_and_fix(prod_dd['contratos'], new_dd)

    print(f"=== DIFF Contratos ===")
    print(f"registros: prod={len(prod_dd['contratos'])} novo={len(new_dd['contratos'])}")
    print(f"adicionados: {len(report['added'])} | removidos: {len(report['removed'])}")
    print(f"corrigidos pelo bug dias_*/tempo_total: {report['bugfixed_count']} "
          f"(dos quais {report['cartorio_reverted']} tiveram situacao_cartorio revertida)")
    print(f"mudanças REAIS (não-bug): {len(report['real_changes'])}")
    for k, diffs in report['real_changes']:
        print(f"\n  {k}:")
        for f, (old, new) in diffs.items():
            print(f"    {f}: {old!r} -> {new!r}")

    if new_extra:
        old_extra_txt = None
        idx = t0.find('const extraInfo')
        if idx != -1:
            eq = t0.find('=', idx)
            brace_start = t0.find('{', eq)
            brace_end = find_matching(t0, brace_start, '{', '}')
            old_extra = json.loads(t0[brace_start:brace_end + 1])
            reg_old = old_extra.get('reg_ulysses', 0) + old_extra.get('reg_eunapio', 0)
            reg_new = new_extra.get('reg_ulysses', 0) + new_extra.get('reg_eunapio', 0)
            print(f"\ncartorio_registrado_novo (extraInfo): {reg_old} -> {reg_new}"
                  + ("  <-- MUDOU, confirme com o Luiz se bate com a realidade" if reg_old != reg_new else ""))

    today_str = (new_extra or {}).get('today') or datetime.now().strftime('%d/%m/%Y')
    card = compute_briefing_card(fixed_dd['contratos'], today_str)
    print(f"\n=== Card 'Contratos — Gestão' do Daily Briefing (recalculado, hoje={today_str}) ===")
    for k, v in card.items():
        print(f"  {k}: {v}")

    if not args.apply:
        print("\n[MODO CONSULTA] Nada foi gravado. Mostre isto ao Luiz; rode de novo com --apply após confirmação.")
        return

    print("\n[APLICANDO...]")
    for fpath in PROD_FILES:
        t, c, tp, tp2, te = unpack(fpath)
        dd, brace_start, brace_end = load_prod_dashboard_data(t)
        new_t = t[:brace_start] + json.dumps(fixed_dd, ensure_ascii=False) + t[brace_end + 1:]

        if new_extra:
            idx = new_t.find('const extraInfo')
            eq = new_t.find('=', idx)
            bstart = new_t.find('{', eq)
            bend = find_matching(new_t, bstart, '{', '}')
            new_t = new_t[:bstart] + json.dumps(new_extra, ensure_ascii=False) + new_t[bend + 1:]

        # atualiza o card do Daily Briefing (procura pelo id contratos dentro de BRIEFING_DATA)
        bidx = new_t.find('"id": "contratos"')
        if bidx != -1:
            bstart = new_t.rfind('{', 0, bidx)
            bend = find_matching(new_t, bstart, '{', '}')
            card_obj = json.loads(new_t[bstart:bend + 1])
            card_obj.update(card)
            new_t = new_t[:bstart] + json.dumps(card_obj, ensure_ascii=False) + new_t[bend + 1:]

        new_c = repack(new_t, c, tp, te)
        Path(fpath).write_text(new_c, encoding='utf-8')
        print(f"  gravado: {fpath} ({len(new_c)} bytes)")

    print("\nLembre de: atualizar TAB_METAS.contratos e o rodapé do sidebar (versão/hora),")
    print("depois validar com Playwright (8 abas, zero erros) antes de entregar.")


if __name__ == '__main__':
    main()
