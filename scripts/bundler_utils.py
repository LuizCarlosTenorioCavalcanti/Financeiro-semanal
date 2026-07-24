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
