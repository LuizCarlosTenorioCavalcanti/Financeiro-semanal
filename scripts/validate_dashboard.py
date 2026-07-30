#!/usr/bin/env python3
"""
validate_dashboard.py — validação padrão pós-atualização dos dois arquivos
de produção ("Dashboard Grupo Delta v5.4.html" e "index.txt"): abre cada um
num Chromium headless, clica nas 8 abas e reporta qualquer erro de JS/console.

USO:
    python3 validate_dashboard.py
    python3 validate_dashboard.py --senha deltabi   # senha do gate do index.txt

Sempre rodar isso depois de qualquer --apply, ANTES de entregar pro Luiz.
Saída "0 erros" nos dois arquivos = ok pra entregar. Qualquer ERRO listado =
NÃO entregar, investigar antes.

Detalhes técnicos (documentados aqui pra não redescobrir toda vez):
  - precisa de cache-busting (?v=timestamp) + --disk-cache-dir isolado por
    execução, senão o Chromium pode servir conteúdo file:// em cache de uma
    validação anterior.
  - index.txt precisa ser copiado pra um arquivo terminado em .html antes —
    o Chromium não executa <script> em conteúdo servido como .txt.
  - index.txt tem uma tela de senha (#gd-pwd / #gd-btn) na frente do app;
    o v5.4.html não tem. A senha atual é 'deltabi' (se mudar, avise).
"""
import argparse
import asyncio
import shutil
import sys
import time
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("ERRO: playwright não instalado. `pip install playwright --break-system-packages` "
          "e `playwright install chromium` (ou configure PLAYWRIGHT_BROWSERS_PATH).")
    sys.exit(1)

PROD_FILES = [
    ("Dashboard Grupo Delta v5.4.html", False),
    ("index.txt", True),
]

TABS = ['briefing', 'financeiro', 'areceber', 'analisemensal',
        'contratos', 'conciliacao', 'comissoes', 'vendas']


async def validate_file(path, is_index, senha):
    errors = []
    test_path = path
    if is_index:
        test_path = str(Path(path).with_suffix('')) + '_validate_tmp.html'
        shutil.copyfile(path, test_path)

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=[f'--disk-cache-dir=/tmp/pwcache_{int(time.time()*1000)}'])
        page = await browser.new_page()
        page.on('pageerror', lambda e: errors.append(f"[pageerror] {e}"))
        page.on('console', lambda m: errors.append(f"[console.{m.type}] {m.text}") if m.type == 'error' else None)

        url = f"file://{Path(test_path).resolve()}?v={int(time.time()*1000)}"
        await page.goto(url)
        await page.wait_for_timeout(1200)

        if is_index:
            pwd = page.locator('#gd-pwd')
            if await pwd.count() > 0:
                await pwd.fill(senha)
                await page.click('#gd-btn')
                await page.wait_for_timeout(1800)

        for tab in TABS:
            btn = page.locator(f"[onclick*=\"_gdSwitch('{tab}')\"]").first
            if await btn.count() > 0:
                await btn.click(timeout=3000)
                await page.wait_for_timeout(700)  # dá tempo de mount + animação de contagem
            else:
                errors.append(f"botão da aba '{tab}' não encontrado")

        await browser.close()

    if is_index:
        Path(test_path).unlink(missing_ok=True)

    return errors


async def main_async(senha):
    all_ok = True
    for fname, is_index in PROD_FILES:
        if not Path(fname).exists():
            print(f"=== {fname} === ARQUIVO NÃO ENCONTRADO no diretório atual, pulando.")
            all_ok = False
            continue
        errors = await validate_file(fname, is_index, senha)
        print(f"\n=== {fname} ===")
        if errors:
            all_ok = False
            for e in errors[:30]:
                print("  ERRO:", e)
        else:
            print("  0 erros")
    print(f"\n{'TUDO OK — pode entregar.' if all_ok else 'TEM ERRO — NÃO entregar antes de investigar.'}")
    return 0 if all_ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--senha', default='deltabi', help="senha do gate do index.txt (padrão: deltabi)")
    args = ap.parse_args()
    sys.exit(asyncio.run(main_async(args.senha)))


if __name__ == '__main__':
    main()
