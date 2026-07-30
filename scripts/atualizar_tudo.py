#!/usr/bin/env python3
"""
atualizar_tudo.py — ponto de entrada único pra atualização do dashboard.
Isso é o que roda quando o Luiz fala "atualiza os dados": acha sozinho quais
dos 6 arquivos-fonte (Contratos, Vendas, Financeiro, A Receber, Conciliação,
Comissões) estão na pasta, roda o diff de cada um, mostra um resumo
consolidado, e só aplica de verdade se for chamado com --apply (e mesmo
assim, avisa quando algum diff tem coisa que merece confirmação manual
antes: remoção de registro, mudança de saldo grande, mudança "real" fora do
bug conhecido).
NOTA (29/07/2026): A Receber ganhou script (`update_areceber.py`) nesta
data. Análise Mensal ainda não tem — se o Luiz mandar fonte nova dela, o
diff continua manual.

USO:
    # 1) Modo consulta (padrão) — mostra o diff de tudo que achar, não grava nada:
    python3 atualizar_tudo.py

    # 2) Modo aplicar — aplica tudo que achar (nos dois arquivos de produção)
    #    e já roda a validação Playwright no final:
    python3 atualizar_tudo.py --apply

    # Pasta específica, se os arquivos-fonte não estiverem na pasta atual:
    python3 atualizar_tudo.py --pasta "/caminho/da/pasta" --apply

Como reconhece cada arquivo (por nome, case-insensitive):
    Contratos    -> nome contém "contratos"
    Vendas       -> nome contém "vendas"
    Financeiro   -> nome contém "financeiro"
    Conciliação  -> nome contém "conciliacao" ou "conciliação"
  (ignora os arquivos de produção "Dashboard Grupo Delta v5.4.html" e
  "index.txt", e qualquer coisa dentro de backup/_to_delete/scripts)

Isso NÃO substitui o julgamento de olhar o diff antes de confirmar — só
elimina o trabalho manual de achar cada arquivo, montar o comando certo pra
cada módulo, e lembrar de todos os passos (TAB_METAS, validação). Sempre
mostre o resumo pro Luiz antes de rodar com --apply, a menos que já tenha
sido combinado que aquele tipo de mudança pode ir direto (ex: Financeiro
puramente aditivo).
"""
import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

PROD_NAMES = {"dashboard grupo delta v5.4.html", "index.txt"}
SKIP_DIRS = {"backup", "backup versoes testes", "_to_delete", "scripts", "skills_backup"}

MODULOS = [
    ("contratos", "contratos", "update_contratos.py"),
    ("vendas", "vendas", "update_vendas.py"),
    ("financeiro", "financeiro", "update_financeiro.py"),
    ("areceber", "receber", "update_areceber.py"),
    ("conciliacao", ("conciliacao", "conciliação"), "update_conciliacao.py"),
    ("comissoes", ("comissoes", "comissões", "comissão"), "update_comissoes.py"),
]


def achar_fonte(pasta, chaves):
    if isinstance(chaves, str):
        chaves = (chaves,)
    candidatos = []
    for f in pasta.iterdir():
        if not f.is_file() or f.suffix.lower() != '.html':
            continue
        if f.name.lower() in PROD_NAMES:
            continue
        nome = f.name.lower()
        if any(k in nome for k in chaves):
            candidatos.append(f)
    if not candidatos:
        return None
    # se tiver mais de um candidato, pega o mais recente (mtime)
    candidatos.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    if len(candidatos) > 1:
        print(f"  aviso: achei {len(candidatos)} arquivos possíveis, usando o mais recente: {candidatos[0].name}")
    return candidatos[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pasta', default='.', help='pasta onde estão os arquivos de produção + fontes novas (padrão: pasta atual)')
    ap.add_argument('--apply', action='store_true', help='aplica de verdade (sem isso, só mostra os diffs)')
    ap.add_argument('--pular-validacao', action='store_true', help='não roda validate_dashboard.py no final do --apply')
    args = ap.parse_args()

    pasta = Path(args.pasta).resolve()
    print(f"Pasta: {pasta}\n")

    encontrados = []
    for label, chaves, script in MODULOS:
        fonte = achar_fonte(pasta, chaves)
        if fonte:
            print(f"[{label}] arquivo-fonte: {fonte.name}")
            encontrados.append((label, fonte, script))
        else:
            print(f"[{label}] nenhum arquivo-fonte novo encontrado, pulando")

    if not encontrados:
        print("\nNenhum arquivo-fonte encontrado na pasta. Nada a fazer.")
        return

    print(f"\n{'='*70}\nRodando diff de cada módulo encontrado...\n{'='*70}")
    resultados = {}
    for label, fonte, script in encontrados:
        print(f"\n----- {label.upper()} -----")
        cmd = [sys.executable, str(SCRIPT_DIR / script), str(fonte)]
        if args.apply:
            cmd.append('--apply')
        r = subprocess.run(cmd, cwd=str(pasta), capture_output=True, text=True)
        print(r.stdout)
        if r.stderr:
            print("STDERR:", r.stderr)
        resultados[label] = r.returncode

    falhas = [k for k, v in resultados.items() if v != 0]
    if falhas:
        print(f"\n*** ATENÇÃO: erro ao processar: {', '.join(falhas)} — não confie na validação abaixo até resolver isso. ***")

    if not args.apply:
        print(f"\n{'='*70}\n[MODO CONSULTA] Nada foi gravado. Mostre os diffs acima pro Luiz antes de rodar com --apply.\n{'='*70}")
        return

    if args.pular_validacao:
        print("\n(validação pulada por --pular-validacao)")
        return

    print(f"\n{'='*70}\nValidando os arquivos de produção (Playwright, 8 abas)...\n{'='*70}")
    r = subprocess.run([sys.executable, str(SCRIPT_DIR / 'validate_dashboard.py')], cwd=str(pasta),
                        capture_output=True, text=True)
    print(r.stdout)
    if r.stderr:
        print("STDERR:", r.stderr)
    if r.returncode != 0:
        print("\n*** VALIDAÇÃO FALHOU — NÃO entregar antes de investigar. ***")
    else:
        print("\nTudo aplicado e validado. Pronto pra entregar (zip + SendUserFile + device_commit_files).")


if __name__ == '__main__':
    main()
