"""
bundler_utils.py — funções compartilhadas para editar os arquivos
"Dashboard Grupo Delta v5.4.html" e "index.txt" (formato __bundler).

Uso típico:
    from bundler_utils import unpack, repack, find_matching

    t, c, tp, tp2, te = unpack("Dashboard Grupo Delta v5.4.html")
    # t = texto JS/HTML desempacotado (string grande)
    # c = conteúdo bruto do arquivo (para repack)
    # tp, tp2, te = posições do wrapper <script type="__bundler/template">

    novo_c = repack(t, c, tp, te)
    open("Dashboard Grupo Delta v5.4.html", "w", encoding="utf-8").write(novo_c)
"""
import json
from datetime import date, datetime, timedelta, timezone

# O container roda em UTC (sem TZ configurada). O Luiz fica em João Pessoa/PB,
# horário de Brasília = UTC-3 o ano inteiro (Brasil não usa mais horário de
# verão desde 2019). NUNCA usar datetime.now() puro pra carimbar TAB_METAS —
# já aconteceu de gravar hora errada (3h a mais) por isso. Use sempre
# now_local_str() abaixo.
BRASILIA_OFFSET = timedelta(hours=-3)


def now_local_datahora():
    """Retorna 'DD/MM/AAAA às HH:MM' (sem prefixo) já convertido pro horário de
    Brasília (UTC-3). Usar em qualquer lugar que precise só do texto da data/hora
    — ex: rodapé do sidebar. Para o formato do TAB_METAS ('Atualizado: ...'),
    usar now_local_str() abaixo."""
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc + BRASILIA_OFFSET
    return now_local.strftime('%d/%m/%Y às %H:%M')


def now_local_str():
    """Retorna 'Atualizado: DD/MM/AAAA às HH:MM' já convertido pro horário de
    Brasília (UTC-3), independente do fuso do container que rodar o script."""
    return f'Atualizado: {now_local_datahora()}'


def find_matching(s, start, open_ch, close_ch):
    """Acha a posição do fechamento correspondente (chave/colchete), respeitando
    aspas simples/duplas/backtick e escapes. `start` deve ser o índice do
    caractere de abertura (open_ch)."""
    depth = 0
    i = start
    in_str = None
    while i < len(s):
        c = s[i]
        if in_str:
            if c == '\\':
                i += 2
                continue
            if c == in_str:
                in_str = None
        else:
            if c in ('"', "'", '`'):
                in_str = c
            elif c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def unpack(fname):
    """Desempacota o __bundler/template de um arquivo v5.4.html / index.txt."""
    c = open(fname, encoding='utf-8').read()
    tp = c.find('<script type="__bundler/template">')
    if tp == -1:
        raise ValueError(f"{fname}: não encontrei o wrapper __bundler/template")
    tp2 = tp + len('<script type="__bundler/template">')
    te = c.find('</script>', tp2)
    raw = c[tp2:te].strip().replace('<\\/script>', '</script>')
    return json.loads(raw), c, tp, tp2, te


def repack(t, c, tp, te):
    """Recodifica o texto desempacotado de volta pro wrapper __bundler/template."""
    new_json = json.dumps(t, ensure_ascii=False).replace('</script>', r'<\/script>')
    return c[:tp] + '<script type="__bundler/template">\n' + new_json + '\n' + c[te:]


def extract_js_object(text, var_name, start_from=0):
    """Acha `const NOME=` (ou similar) e retorna (obj_python, brace_start, brace_end)
    do objeto/array JS logo depois do `=`. Faz json.loads no literal."""
    idx = text.find(var_name, start_from)
    if idx == -1:
        raise ValueError(f"variável '{var_name}' não encontrada")
    eq = text.find('=', idx)
    # aceita tanto { quanto [ como abertura
    j = eq + 1
    while text[j] in ' \n\t':
        j += 1
    open_ch = text[j]
    close_ch = '}' if open_ch == '{' else ']'
    brace_end = find_matching(text, j, open_ch, close_ch)
    literal = text[j:brace_end + 1]
    return json.loads(literal), j, brace_end


def check_not_truncated(fname):
    """Levanta erro se o arquivo-fonte parece cortado/incompleto."""
    c = open(fname, encoding='utf-8', errors='replace').read()
    if '</html>' not in c:
        raise ValueError(
            f"ARQUIVO TRUNCADO: '{fname}' não contém '</html>'. "
            f"Provavelmente foi salvo incompleto — peça para o usuário resalvar."
        )
    return c


def load_source_text(fname):
    """Lê um arquivo-fonte de módulo (pode vir empacotado __bundler ou HTML puro
    — os exports variam) e devolve o texto já desempacotado, pronto pra buscar
    variáveis JS dentro. Sempre confere truncamento primeiro."""
    check_not_truncated(fname)
    raw = open(fname, encoding='utf-8').read()
    if '<script type="__bundler/template">' in raw:
        t, _, _, _, _ = unpack(fname)
        return t
    return raw


def module_bounds(t, js_marker, js_marker_next):
    """Acha os limites (start, end) do bloco JS de um módulo, usando os
    comentários '/* ==== X module ==== */' como marcadores. Uso obrigatório
    antes de qualquer find() dentro de um módulo específico — o texto
    desempacotado é um arquivo gigante e vários módulos reusam nomes de
    variável/id (ex: Comissões e Vendas), então uma busca sem limites pode
    achar a ocorrência errada. Ver INSTRUCOES_ASSISTENTE.md."""
    start = t.find(js_marker)
    if start == -1:
        raise ValueError(f"marcador de módulo não encontrado: {js_marker!r}")
    end = t.find(js_marker_next)
    if end == -1:
        raise ValueError(f"marcador de módulo (fim) não encontrado: {js_marker_next!r}")
    if end <= start:
        raise ValueError(f"limites de módulo inválidos: start={start} end={end}")
    return start, end


def extract_js_object_bounded(text, var_name, lo, hi):
    """Igual extract_js_object, mas exige que a variável seja encontrada
    DENTRO de [lo, hi) — evita casar com a variável de mesmo nome de outro
    módulo (ex: 'const DATA' existe em Financeiro E em Vendas)."""
    idx = text.find(var_name, lo, hi)
    if idx == -1 or not (lo <= idx < hi):
        raise ValueError(f"'{var_name}' não encontrado dentro dos limites do módulo ({lo}, {hi})")
    eq = text.find('=', idx)
    j = eq + 1
    while text[j] in ' \n\t':
        j += 1
    open_ch = text[j]
    close_ch = '}' if open_ch == '{' else ']'
    brace_end = find_matching(text, j, open_ch, close_ch)
    assert lo <= j < hi, "posição da variável saiu dos limites do módulo (bug)"
    literal = text[j:brace_end + 1]
    return json.loads(literal), j, brace_end


def patch_tab_meta(t, tab_key, new_data_str):
    """Atualiza só o campo `data:'Atualizado: ...'` da entrada TAB_METAS[tab_key],
    sem precisar saber o valor antigo (usa regex, não string literal exata —
    o valor antigo muda toda hora). Mantém version/prog intactos.

    IMPORTANTE: a busca é limitada ao bloco `TAB_METAS = { ... }` (achado via
    find_matching, não uma busca livre no arquivo inteiro) — o mesmo texto
    'KEY', label:... aparece em outro lugar do arquivo (o array de config das
    abas do menu), e uma regex sem essa fronteira casa com o trecho errado.
    Levanta erro se não achar exatamente 1 ocorrência da chave dentro do bloco.
    """
    import re
    tm_idx = t.find('TAB_METAS')
    if tm_idx == -1:
        raise ValueError("TAB_METAS não encontrado no arquivo")
    eq = t.find('=', tm_idx)
    j = eq + 1
    while t[j] in ' \n\t':
        j += 1
    if t[j] != '{':
        raise ValueError("TAB_METAS: não achei '{' logo após o '='")
    block_end = find_matching(t, j, '{', '}')

    pattern = re.compile(
        r"('" + re.escape(tab_key) + r"'\s*:\s*\{[^}]*?data:')([^']*)(')"
    )
    matches = [m for m in pattern.finditer(t, j, block_end + 1)]
    if len(matches) != 1:
        raise ValueError(f"TAB_METAS['{tab_key}']: esperava 1 ocorrência dentro do bloco, achei {len(matches)}")
    m = matches[0]
    return t[:m.start(2)] + new_data_str + t[m.end(2):]


def patch_sidebar_footer(t, date_hora_str=None):
    """Atualiza o rodapé do perfil no menu lateral: 'vX.X · Atualizado DD/MM/AAAA
    às HH:MM' (embaixo do nome do Luiz). É um texto LITERAL fixo no JS, não vem
    de nenhuma variável — por isso é fácil esquecer de atualizar (já aconteceu:
    ficou parado em "24/07/2026 às 16:11" por 3 dias enquanto vários módulos
    foram atualizados). REGRA: rodar isso em TODO --apply, de QUALQUER script,
    não só quando o módulo em si muda de versão — é o "quando mexi na última
    vez em qualquer coisa", não o carimbo de um módulo específico (esse é o
    TAB_METAS, ver patch_tab_meta). Preserva o texto de versão (vX.X) como já
    estiver gravado, só troca a data/hora. `date_hora_str` no formato
    'DD/MM/AAAA às HH:MM' (sem prefixo) — se omitido, usa now_local_datahora()."""
    import re
    if date_hora_str is None:
        date_hora_str = now_local_datahora()
    pattern = re.compile(r"(v[\d.]+ · Atualizado )\d{2}/\d{2}/\d{4} às \d{2}:\d{2}")
    matches = list(pattern.finditer(t))
    if len(matches) != 1:
        raise ValueError(f"rodapé do sidebar: esperava 1 ocorrência, achei {len(matches)}")
    m = matches[0]
    return t[:m.start()] + m.group(1) + date_hora_str + t[m.end():]


DAILY_BRIEFING_MARKER = '/* ==== Daily Briefing module ==== */'


def _pd_briefing(s):
    """Parseia 'DD/MM/AAAA' -> date. Usado só pela lógica de janela_recente."""
    d, m, y = s.split('/')
    return date(int(y), int(m), int(d))


def business_day_before(d):
    """Retorna o dia útil anterior a `d` (pula sábado/domingo). NÃO considera
    feriados — não há calendário de feriados disponível, só fins de semana."""
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:  # 5=sábado, 6=domingo
        prev -= timedelta(days=1)
    return prev


def patch_janela_recente(t, hoje):
    """Recalcula a janela 'recente' do Daily Briefing (achado em 28/07/2026,
    a pedido do Luiz: "Atualização Recente... estão com datas atrasadas,
    seguir as datas do dia hoje e util anterior" + "comissoes esta atualizado
    hoje, esta com atualização anterior"). Duas coisas estavam travadas:
      1. O TEXTO `BRIEFING_DATA.janela_recente` ('DD/MM (hoje) e DD/MM (dia
         útil anterior)') é um literal que nenhum script nunca recalculava —
         ficava preso na data de quando alguém escreveu à mão da última vez.
      2. Os cards dentro de `BRIEFING_DATA.recente`/`anterior` nunca eram
         RECLASSIFICADOS: um card cujo `data_ref` passou a cair dentro da
         janela (ex: atualizado hoje) podia continuar preso no array
         'anterior' se já estivesse lá antes — a comparação data_ref vs
         janela só valia na hora em que alguém tinha organizado os arrays
         manualmente, nunca era reconferida depois.
    Esta função resolve os dois: recalcula o texto E move cada card pro
    array certo (recente = data_ref igual a hoje OU ao dia útil anterior;
    todo o resto vai pra anterior), preservando a ordem relativa dentro de
    cada grupo. Chamada de dentro de patch_briefing_header — não precisa
    chamar separado.
    `hoje`: objeto date (não string) representando "hoje" pro cálculo."""
    dia_ant = business_day_before(hoje)
    janela_str = f"{hoje.strftime('%d/%m')} (hoje) e {dia_ant.strftime('%d/%m')} (dia útil anterior)"

    marker = t.find(DAILY_BRIEFING_MARKER)
    if marker == -1:
        raise ValueError("marcador do módulo Daily Briefing não encontrado")
    idx = t.find('const BRIEFING_DATA', marker)
    if idx == -1:
        raise ValueError("BRIEFING_DATA não encontrado")
    eq = t.find('=', idx)
    j = eq + 1
    while t[j] in ' \n\t':
        j += 1
    if t[j] != '{':
        raise ValueError("BRIEFING_DATA: não achei '{' logo após o '='")
    brace_end = find_matching(t, j, '{', '}')
    briefing = json.loads(t[j:brace_end + 1])

    briefing['janela_recente'] = janela_str

    todos = list(briefing.get('recente', [])) + list(briefing.get('anterior', []))
    janela_dias = {hoje, dia_ant}
    nova_recente, nova_anterior = [], []
    for card in todos:
        dr = card.get('data_ref')
        card_date = None
        if dr:
            try:
                card_date = _pd_briefing(dr)
            except Exception:
                card_date = None
        if card_date in janela_dias:
            nova_recente.append(card)
        else:
            nova_anterior.append(card)
    briefing['recente'] = nova_recente
    briefing['anterior'] = nova_anterior

    new_json = json.dumps(briefing, ensure_ascii=False, separators=(',', ':'))
    return t[:j] + new_json + t[brace_end + 1:]


def patch_briefing_header(t, now_str=None):
    """Atualiza os lugares que mostram 'quando o Daily Briefing foi atualizado
    pela última vez': o badge do topo da própria aba Daily Briefing
    (TAB_METAS['briefing'].data — igual a de qualquer outra aba), a linha
    'Consolidado em ...' (BRIEFING_DATA.gerado_em, dentro do módulo), e (desde
    28/07/2026) a janela 'recente'/'anterior' inteira — ver patch_janela_recente
    acima. Achado em 27/07/2026: NENHUM script nunca tocava nesses campos — só
    o card individual de cada módulo (contratos/vendas/financeiro/conciliacao)
    era atualizado, mas o cabeçalho geral do Daily ficava travado (ficou preso
    em "24/07/2026 às 09:52" por 3 dias, mesmo com cards mudando todo dia). O
    Luiz percebeu: "sempre que algum modulo do daily tiver alteração, tem que
    colocar a data e hora da atualização mais recente". REGRA: rodar isso em
    TODO --apply de QUALQUER script que atualiza um card do Daily Briefing —
    mesmo padrão do patch_sidebar_footer (é "quando mexi na última vez em
    qualquer coisa do Daily", não o carimbo de um card específico).
    `now_str` no formato 'Atualizado: DD/MM/AAAA às HH:MM' — se omitido, usa
    now_local_str()."""
    import re
    if now_str is None:
        now_str = now_local_str()
    date_hora_str = now_str.split('Atualizado: ')[-1]
    hoje_str = date_hora_str.split(' às ')[0]
    hoje = _pd_briefing(hoje_str)

    # 1) TAB_METAS['briefing'].data — mesmo padrão do patch_tab_meta, ancorado
    # dentro do bloco TAB_METAS pra não colidir com outro uso do texto.
    t = patch_tab_meta(t, 'briefing', now_str)

    # 2) BRIEFING_DATA.gerado_em — ancorado no marcador do módulo Daily Briefing.
    marker = t.find(DAILY_BRIEFING_MARKER)
    if marker == -1:
        raise ValueError("marcador do módulo Daily Briefing não encontrado")
    pattern = re.compile(r'("gerado_em"\s*:\s*")([^"]*)(")')
    m = pattern.search(t, marker)
    if not m:
        raise ValueError("BRIEFING_DATA.gerado_em não encontrado — não deixe isso passar em silêncio")
    t = t[:m.start(2)] + date_hora_str + t[m.end(2):]

    # 3) janela_recente (texto) + reclassificação recente/anterior dos cards.
    t = patch_janela_recente(t, hoje)
    return t


def find_briefing_card(t, card_id):
    """Acha o objeto de um card dentro de BRIEFING_DATA (seções 'recente' ou
    'anterior') pelo `id` (ex: 'financeiro', 'conciliacao', 'contratos', 'vendas')
    e devolve (card_obj, bstart, bend) pra editar e regravar com write_briefing_card.
    A busca é ANCORADA no marcador do módulo Daily Briefing (não busca livre no
    arquivo inteiro) — regra geral do projeto pra não colidir com outro uso do
    mesmo texto em outro lugar do arquivo (ver module_bounds/extract_js_object_bounded).
    REGRA DO PROJETO (corrigida em 27/07/2026, achado pelo Luiz: "o daily de
    todos os modulos tem que sempre mostrar a ultima atualização"): TODO script
    de update que tem um card correspondente no Daily Briefing (financeiro,
    conciliacao, contratos, vendas, ...) tem que recalcular e regravar esse card
    a cada --apply, usando os dados que acabou de aplicar — nunca deixar o card
    congelado num snapshot antigo enquanto o módulo em si já foi atualizado."""
    import re
    marker = t.find(DAILY_BRIEFING_MARKER)
    if marker == -1:
        raise ValueError("marcador do módulo Daily Briefing não encontrado")
    pattern = re.compile(r'"id"\s*:\s*"' + re.escape(card_id) + r'"')
    m = pattern.search(t, marker)
    if not m:
        raise ValueError(f"card '{card_id}' não encontrado dentro do BRIEFING_DATA — não deixe isso passar em silêncio")
    bstart = t.rfind('{', 0, m.start())
    bend = find_matching(t, bstart, '{', '}')
    card_obj = json.loads(t[bstart:bend + 1])
    return card_obj, bstart, bend


def write_briefing_card(t, card_obj, bstart, bend):
    """Regrava o card editado (ver find_briefing_card) de volta no texto, sempre
    em JSON compacto (separators sem espaço) pra bater com o resto do arquivo —
    ver a armadilha documentada no INSTRUCOES_ASSISTENTE.md sobre json.dumps sem
    `separators=` deixar o trecho com espaço depois de um --apply."""
    new_json = json.dumps(card_obj, ensure_ascii=False, separators=(',', ':'))
    return t[:bstart] + new_json + t[bend + 1:]
