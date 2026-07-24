# Instruções para o Assistente — Dashboard Grupo Delta

Este documento existe para que qualquer conta/sessão do Claude que abrir esta pasta consiga continuar o trabalho exatamente como vinha sendo feito, mesmo trocando de usuário, computador ou reiniciando a memória. Leia isto antes de mexer em qualquer arquivo `Dashboard Grupo Delta v5.4.html` ou `index.txt`.

## Contexto geral

Luiz Carlos é supervisor administrativo no Grupo Delta Construtora (João Pessoa/PB). Este projeto mantém um dashboard financeiro único em HTML, reunindo **8 módulos** em abas: Daily Briefing, Financeiro A Pagar, Financeiro A Receber, Financeiro Global Mensal (Análise Mensal), Contratos, Conciliação Bancária, Comissão e Vendas.

> O módulo "Descontos nas Unidades" que existia nas versões antigas (v3.1–v4.x) foi **descontinuado** e não faz mais parte do dashboard atual — não procurar `Dashboard_Descontos_*.html` nem reintroduzir essa aba sem pedido explícito do Luiz.

## Arquivos principais

- **`Dashboard Grupo Delta v5.4.html`** — versão OFICIAL de produção atual.
- **`index.txt`** — mesma versão oficial, mantido em sincronia byte-a-byte com o v5.4.html (é o arquivo publicado/acessado pelos usuários finais).
- **`Dashboard Grupo Delta v5.3.html`** e anteriores — OBSOLETOS. Nunca editar; servem só de histórico/backup.

Todo trabalho de dados e correções acontece em **v5.4.html e index.txt em paralelo** (sempre os dois, nessa ordem ou junto — qualquer edição feita em um precisa ser replicada identicamente no outro antes de considerar a tarefa concluída).

### Módulos atuais e arquivos-fonte

| id (interno) | Aba / sublabel | Ícone | Arquivo-fonte | Versão atual embutida |
|---|---|---|---|---|
| `briefing` | Daily Briefing / Resumo do Dia | ⚡ | não tem arquivo-fonte próprio — é montado a partir dos dados dos outros módulos já embutidos no próprio v5.4 | v1.1 |
| `financeiro` | Financeiro / A Pagar | ↓ | `Dashboard Financeiro v3.2.html` | v3.2 |
| `areceber` | Financeiro / A Receber | ↑ | `Dashboard A Receber v2.3.html` | v2.3 |
| `analisemensal` | Financeiro / Global Mensal | $ | `Dashboard Analise Mensal v2.1.html` | v2.1 |
| `contratos` | Contratos / Gestão | ≡ | `Dashboard Contratos v3.4.X.html` | v3.4.1 |
| `conciliacao` | Conciliação / Balanço | ⇌ | `Dashboard_Conciliacao_v2.3.html` | v2.3 |
| `comissoes` | Comissão / Unidades | % | `Dashboard_Comissoes_v1.2.html` | v1.2 |
| `vendas` | Vendas / Unidades | ⌂ | `Dashboard_Vendas_v1.X.html` | v1.1 |

Cada um desses arquivos-fonte é standalone (a maioria também no formato `__bundler`, ver abaixo) e o Luiz substitui na pasta quando tem dados novos. **Antes de confiar num nome de versão, confira sempre o `TAB_METAS` de dentro do v5.4.html — é a fonte de verdade, não esta tabela** (esta tabela é só um retrato do momento da última atualização deste documento).

## Fluxo padrão: "atualiza os dados"

**Regra combinada com o usuário**: sempre que ele pedir "atualiza os dados", **primeiro liste todos os módulos com data/hora de cada arquivo-fonte, compare com o que já está no v5.4, e aguarde confirmação explícita antes de aplicar qualquer coisa.** Nunca aplique direto sem esse passo. Exceção já validada: se o Luiz mandar o arquivo junto com um pedido direto tipo "verifica e atualiza"/"ATUALIZAR", o diff mecânico (bug conhecido, merge simples) pode ser aplicado no mesmo turno — mas qualquer coisa que não seja mecânica (mudança real de dado, valor ambíguo de fonte, campo que não bate) ainda precisa ser listada e esperar confirmação antes de aplicar.

### Checklist obrigatório (não pular nenhum item — item 6 já foi esquecido uma vez)

1. Rodar `ls -la --time-style=full-iso *.html` na pasta e comparar mtimes com as datas salvas no `TAB_METAS` do v5.4 atual.
2. **Cuidado com mount desatualizado**: às vezes o acesso à pasta fica "preso" num retrato antigo (mtimes não batem com o que o usuário vê no Explorer, ou um arquivo recém-staged continua voltando com o conteúdo antigo). Se suspeitar disso, avise o usuário — e tente o truque de **copiar o arquivo com outro nome no device_bash e dar stage nessa cópia** (`cp "X.html" "X_fresh.html"` na pasta do usuário, depois `device_stage_files` no `_fresh.html`) — isso força um caminho novo e furou o cache quando um `device_stage_files` repetido no mesmo nome não atualizava.
3. **Verificar se o arquivo-fonte não está truncado/corrompido**: já aconteceu MAIS DE UMA VEZ (Contratos e Conciliação) do arquivo salvo pelo usuário terminar no meio do código, sem fechar `</script></body></html>`. Sempre checar `'</html>' in conteudo` antes de confiar no arquivo.
4. Para cada módulo que parece mais novo, **verificar o conteúdo de verdade** (não só a data): comparar os dados byte a byte / campo a campo entre o arquivo-fonte e o que já está embutido no v5.4. A data/hora exibida na tela é só texto, pode estar errada — não confiar nela isoladamente. **Use os scripts prontos** (`update_contratos.py`, `update_vendas.py` — ver seção própria abaixo) em vez de escrever o diff na mão; eles já embutem as chaves corretas, o bug conhecido dos `dias_*` e as fórmulas do Daily Briefing.
5. Listar para o usuário o que precisa atualizar (mudanças reais, não as de bug conhecido) e aguardar "pode seguir" (ou similar) antes de aplicar qualquer coisa ambígua.
6. **Checar se a mudança afeta o Daily Briefing** — sempre, mesmo que o pedido tenha sido só "atualiza [outro módulo]". Ver seção "Fórmulas do Daily Briefing" abaixo. Isso já foi esquecido uma vez nesta sessão ("erro grande, você não atualizou o daily") — não repetir.
7. Aplicar as atualizações (ver técnica de transplante abaixo, ou rodar o script com `--apply`).
8. Atualizar `TAB_METAS` (data de cada módulo) e o rodapé do sidebar (`vX.X · Atualizado DD/MM/AAAA às HH:MM`, hora de Brasília/sincronização, não a hora do dado em si).
9. Validar: reabrir o JSON (`json.loads`) dos dois arquivos e confirmar que parseia sem erro. Depois, abrir o arquivo num navegador (Playwright) e clicar em **todas as 8 abas** conferindo console sem erros — é o teste que mais pega bug real (pegou 2 regressões nesta sessão). **Importante**: ao testar `index.txt` no Playwright, ele tem extensão `.txt` e o Chromium não executa `<script>` nela — copie para um `.html` temporário antes de abrir (`cp index.txt _check.html`), teste, e apague a cópia depois.
10. Empacotar os dois arquivos num `.zip`, entregar com `SendUserFile`, mandar pro `device_commit_files`, extrair no `device_bash` do lado do usuário e **conferir md5sum** dos arquivos finais contra os que ficaram no workspace — só then considerar a entrega concluída (ver "Entrega de arquivos grandes" abaixo).

## Scripts prontos (evitam reescrever a lógica do zero a cada sessão)

Na pasta tem uma subpasta `scripts/` com:
- `bundler_utils.py` — funções compartilhadas (`unpack`, `repack`, `find_matching`, `extract_js_object`, `check_not_truncated`).
- `update_contratos.py` — diff + merge do módulo Contratos, já com a correção do bug `dias_*`/`tempo_total` e o recálculo do card do Daily Briefing embutidos.
- `update_vendas.py` — diff + merge do módulo Vendas, já checando se o card fixo de Vendas no Daily Briefing precisa recálculo.

Uso (sempre nessa ordem — primeiro sem `--apply`, mostrar pro Luiz, só depois `--apply`):
```bash
cd "pasta do dashboard"
python3 scripts/update_contratos.py "Dashboard Contratos v3.5.html"          # modo consulta
python3 scripts/update_contratos.py "Dashboard Contratos v3.5.html" --apply  # grava

python3 scripts/update_vendas.py "Dashboard_Vendas_v1.2.html"
python3 scripts/update_vendas.py "Dashboard_Vendas_v1.2.html" --apply
```
Depois do `--apply` ainda falta na mão: atualizar `TAB_METAS`/rodapé (os scripts avisam no final), e rodar a validação Playwright (passo 9 do checklist) antes de entregar. Os scripts NÃO existem ainda para os outros módulos (Financeiro, A Receber, Análise Mensal, Conciliação, Comissão) — para esses, o diff ainda é manual; se for fazer um script novo para algum deles, seguir o mesmo padrão (`bundler_utils.py` + diff por chave composta + modo consulta/`--apply`).

## Fórmulas do Daily Briefing — card "Contratos — Gestão"

Reverse-engineered nesta sessão (batem com os números históricos definidos à mão antes). Documentado aqui pra não ter que redescobrir:

- `contrato_sienge_total` = conta contratos com `data_contrato_sienge` preenchida E `data_assinatura` vazia.
- `contrato_sienge_novo` = conta contratos com `data_contrato_sienge` == HOJE.
- `assinados_novo` = conta contratos com `data_assinatura` == HOJE.
- `assinados_triagem_total` = conta contratos com `etapa_itbi == 'TRIAGEM'`.
- `itbi_solicitado_total` = conta contratos com `etapa_itbi == 'ITBI SOLICITADO'`.
- `itbi_solicitado_atrasados` = conta contratos com `etapa=='ITBI' E situacao_itbi=='ATRASADO'`.
- `cartorio_protocolado_total` = conta contratos com `etapa=='CARTÓRIO'`.
- `cartorio_protocolado_atrasados` = conta contratos com `etapa=='CARTÓRIO' E situacao_cartorio=='ATRASADO'`.
- `cartorio_protocolado_novo` = conta contratos com `data_entrada_cartorio` == HOJE.
- `cartorio_registrado_novo` = `extraInfo.reg_ulysses + extraInfo.reg_eunapio` (vem pronto do arquivo-fonte — se parecer estranho/inconsistente com o resto dos dados, perguntar ao Luiz antes de aplicar, já aconteceu esse valor cair pra 0 sem nenhuma mudança correspondente nos contratos de cartório).
- `entregue_agencia_total` / `entregue_agencia_atrasados` = conta contratos com `data_entregue_agencia` == HOJE (o "_atrasados" soma `situacao_agencia=='ATRASADO'`).
- `credito_liberado` = conta contratos com `data_credito` == HOJE.

**Regra importante (corrigida em 24/07/2026, confirmada pelo Luiz)**: todos os campos acima marcados "== HOJE" usam **só o dia da atualização** (`extraInfo.today`), não uma janela de 2 dias. Isso é diferente do `janela_recente` do topo do `BRIEFING_DATA` (que controla se o CARD inteiro aparece na seção "recente" vs "anterior" do Daily — esse sim é uma janela de 2 dias, "hoje + dia útil anterior"). São dois conceitos diferentes, não confundir: um decide o que aparece DENTRO do card (sempre só hoje), o outro decide se o card aparece na seção de cima ou de baixo do Daily (2 dias).

Os campos "_total" (`contrato_sienge_total`, `itbi_solicitado_total`, `cartorio_protocolado_total`, `assinados_triagem_total`) são uma FOTO do estado atual — não usam janela nenhuma, contam tudo que está naquele estado agora.

## Bug conhecido: `dias_*` / `tempo_total` absurdos (módulo Contratos)

O export do Sienge calcula `dias_solicitar_itbi`, `dias_entregar_cartorio`, `dias_processo_agencia`, `dias_aguardando_agencia` e `tempo_total` contra uma data padrão/época quando a data real está em branco, gerando valores tipo `46226` (~126 anos) ou negativos grandes tipo `-45000`. **Regra de correção**: para cada registro, qualquer um desses 5 campos com `abs(valor) > 1000` vira `null`. Se `situacao_cartorio` também virou (ex: `OK`→`ATRASADO`) só por causa disso no mesmo registro, reverter para o valor antigo também. O script `update_contratos.py` já faz isso sozinho.

## Entrega de arquivos grandes (v5.4.html/index.txt, ~9 MB)

`device_commit_files` estoura timeout em arquivos desse tamanho (mesmo com retry). Fluxo validado que sempre funcionou nesta sessão:
1. Zipar os dois arquivos (`zip -j update.zip "Dashboard Grupo Delta v5.4.html" index.txt`) — cai pra ~1,9 MB por causa da repetição no texto escapado.
2. `SendUserFile` no zip.
3. `device_commit_files` do zip (pequeno, não estoura).
4. No `device_bash`, na pasta do usuário: `mkdir pasta_extract && unzip -o update.zip -d pasta_extract`, depois um Python com `shutil.copyfileobj(open(src,'rb'), open(dest,'wb'))` para regravar os arquivos finais **sem apagar** (o `device_bash` não pode deletar arquivo — `unzip -o` direto em cima do arquivo existente falha com "Operation not permitted"; `copyfileobj` trunca e regrava sem precisar de unlink).
5. Conferir `md5sum` dos arquivos finais contra os do workspace.
6. Mover o zip/pasta temporária para uma `_to_delete/` (criada na pasta do usuário) — `device_bash` não deleta arquivo nenhum, só `mv`.

## Formato técnico do arquivo (`__bundler`)

O `v5.4.html`/`index.txt` guardam o documento inteiro como uma STRING JSON dentro de `<script type="__bundler/template">...</script>`. **Isso explica por que o arquivo inteiro (não só os literais de dados) aparece com `\n` e `\"` literais em vez de quebra de linha/aspas reais** — é um efeito colateral direto desse empacotamento, não uma particularidade de cada módulo. Para editar:

```python
import json
def unpack(fname):
    c = open(fname, encoding='utf-8').read()
    tp = c.find('<script type="__bundler/template">')
    tp2 = tp + len('<script type="__bundler/template">')
    te = c.find('</script>', tp2)
    raw = c[tp2:te].strip().replace('<\\/script>', '</script>')
    return json.loads(raw), c, tp, tp2, te
```

Para salvar de volta:
```python
new_json = json.dumps(new_t, ensure_ascii=False).replace('</script>', r'<\/script>')
new_c = c[:tp] + '<script type="__bundler/template">\n' + new_json + '\n' + c[te:]
```

Se preferir fazer uma edição pontual sem desempacotar o JSON inteiro (útil em arquivo grande, ~9 MB), dá para operar direto na string bruta do arquivo, contanto que: (a) os pontos de âncora usados em `.find()` sejam substrings ASCII sem aspas nem quebra de linha (ex: `'tab-vendas'`, `'gd-v53-css'` — nunca um trecho com `"` ou `\n` reais, porque no arquivo eles aparecem escapados); e (b) qualquer conteúdo novo inserido (HTML/CSS/JS com quebras de linha e aspas) seja escapado antes com `json.dumps(texto, ensure_ascii=False)[1:-1]`, replicando a mesma convenção do resto do arquivo.

Alguns arquivos-fonte individuais (Financeiro, A Receber, Contratos) TAMBÉM usam esse mesmo formato `__bundler` — precisam ser desempacotados do mesmo jeito antes de extrair os dados. Outros (Conciliação, Análise Mensal, Comissões, Vendas) são HTML puro, sem esse empacotamento.

## Técnica de transplante seguro ("back-to-front")

Ao substituir múltiplos blocos de dados no mesmo arquivo, **sempre calcular todas as posições de corte a partir do texto ORIGINAL intacto**, nunca fazer `.replace()` sequenciais numa string que já foi alterada (os offsets mudam). Usar um parser de profundidade de chaves/colchetes (`find_matching_brace`) que respeita strings (aspas simples, duplas, backtick, escapes) para extrair literais JS que não são JSON válido (chaves sem aspas, aspas simples).

## Estrutura de cada módulo dentro do arquivo unificado

Cada módulo vive dentro de um comentário marcador, ex: `/* ==== Contratos module ==== */`, envolvido por uma IIFE:
```js
(function(){
  ... código do módulo ...
  window._mount_NOMEDOMODULO = function(){ ... };
})();
```
O sistema de abas chama `window._mount_NOMEDOMODULO()` quando o usuário clica na aba (mount preguiçoso/lazy). O HTML do módulo fica envolto em `<div id="tab-NOME" class="tab-panel" data-mounted="false"><div class="tab-panel-inner" id="inner-NOME">...</div></div>`, e o CSS é escopado com prefixo `#tab-NOME`.

Registro de um módulo novo precisa tocar em **todos** estes pontos (não só o HTML/CSS/JS do módulo em si):
- array `TABS` (ordem = ordem visual no sidebar)
- objeto `TAB_METAS` (version/data/prog)
- objeto `GD_COLOR_OFFSETS`
- string `SEL` dentro de `gd-topfix-js` (para o badge "N filtros ativos" funcionar no container de filtros do módulo)
- regra CSS `position:relative` do container de filtros (mesma lista de seletores do `SEL` acima)

### Armadilhas já identificadas e corrigidas (NÃO repetir)

1. **Colisão de nomes entre módulos**: `toggleTree`, `toggleInvDetail` e funções parecidas existem duplicadas em módulos diferentes (Conciliação e Contratos), cada uma isolada na própria IIFE. Atributos `onclick="..."` no HTML executam em escopo GLOBAL, então uma função só local não é enxergada — é preciso expor com sufixo, ex: `window.toggleTree_conciliacao = toggleTree;` e trocar o `onclick` correspondente para `onclick="toggleTree_conciliacao(this)"`. Isso vale tanto para o call-site fixo quanto para os gerados dinamicamente dentro de `render()`/templates de string — **verificar TODAS as ocorrências de `onclick="nomeFuncao("`, não só uma.**
2. **Exposição de funções fora do escopo (`window.x = x`) precisa estar DENTRO da IIFE que define `x`**, antes do `})();` de fechamento — nunca depois. Colocar depois causa `ReferenceError: x is not defined` na hora do load.
3. **Bloco de módulo duplicado/órfão**: já aconteceu do Conciliação existir DUAS vezes no arquivo — uma cópia órfã (script solto, sem IIFE, com `render()` incondicional, que é a que edições ingênuas por `.find()` acabavam sempre encontrando) e a cópia de verdade (dentro do padrão IIFE + `_mount_conciliacao`). Sempre conferir `t.count('const NOMEDAVARIAVEL')` — se aparecer mais de 1, investigar duplicidade antes de aplicar qualquer dado.
4. **CSS de módulo precisa ser escopado**: ao trazer um `<style>` novo de um arquivo-fonte standalone, ele vem com seletores globais (`:root`, `*`, `html`, `body`, `.classe`, `header` etc.). Isso PRECISA ser transformado: `:root`/`html`/`body` viram `#tab-NOMEDOMODULO{...}` (sem espaço), e qualquer outro seletor recebe o prefixo `#tab-NOMEDOMODULO ` (com espaço, seletor descendente) — inclusive dentro de blocos `@media`. Nunca copiar um `<style>` de arquivo-fonte direto sem essa transformação, ou o CSS vaza pro dashboard inteiro. **Além disso, se o `<style>` fonte redefine variáveis de tema (`--blue-900`...`--blue-50` etc.) dentro de um `:root` local, DROPAR essas redefinições** (manter só cores realmente específicas do módulo, tipo `--gold`) — senão o módulo não acompanha a troca de tema (`html[data-gdt="tN"]`) do resto do dashboard.
5. **Trocar só o `<script>` de um módulo não é suficiente quando o HTML/CSS também mudou**: o Análise Mensal tem HTML estático (ex: `<option>` de filtro) e `<style>` PRÓPRIOS, fora do bloco `<script>`. Se o arquivo-fonte mudou o corpo HTML (novo filtro, novo texto) ou cor, é preciso trocar também esse trecho de HTML/CSS, não só os dados JS.
6. **Bugs que já existiam no PRÓPRIO arquivo-fonte** (não são erro de transplante): função chamada mas nunca definida (ex: `fmtM` no lugar de `fmtK`), inconsistência de acentuação nos dados (ex: campo "Definição" com "COMISSOES" e "COMISSÕES" como valores diferentes pro filtro, causando duplicidade visual). Ao encontrar algo assim, INVESTIGAR se é bug de transplante ou bug pré-existente no arquivo-fonte antes de "corrigir" — e perguntar ao usuário como prefere tratar (normalizar no dashboard vs. corrigir na origem).
7. **Arquivo-fonte truncado**: verificar sempre `'</html>' in conteudo` antes de confiar em qualquer arquivo-fonte. Já aconteceu mais de uma vez (Contratos, Conciliação).
8. **Mount do sandbox pode ficar desatualizado** (mtime/conteúdo velho mesmo com arquivo já salvo pelo usuário). Se o usuário mostrar print com data/hora diferente do que você está vendo, ACREDITE no usuário, avise que seu acesso está desatualizado, e tente reler.
9. **Colisão de `id` de elemento entre módulos** (descoberto na integração do Comissão/Vendas — os dois foram gerados a partir do mesmo template e reusam os MESMOS ids genéricos: `cardVendaTotal`, `fEmpresa`, `chartLinha`, `treeRoot`, `btnLimpar` etc.). `getElementById` sempre resolve para o PRIMEIRO elemento com aquele id no documento — então o JS do módulo mais novo silenciosamente escreve dentro dos elementos (ocultos) do módulo mais antigo, e o próprio módulo novo fica com os campos travados em "—", sem nenhum erro no console. **Antes de inserir um módulo novo, listar TODOS os ids `id="..."` do HTML+JS do arquivo-fonte e grepar cada um contra o v5.4.html já existente; renomear qualquer um que já exista com um prefixo curto do módulo (ex: `vnd`, `cms`).** Atenção especial a **ids montados por concatenação de string em JS** (ex: `'cardVenda'+k`, `'mw-'+key`) — uma renomeação por regex `\bid\b` estático não pega esse padrão; é preciso caçar manualmente cada `getElementById(` e cada string-base usada em concatenação.

## Convenções de exibição

- `TAB_METAS` (dentro do JS do v5.4) guarda `version`, `data` (data/hora do PRÓPRIO módulo, refletindo o dado real) e `prog` (texto da programação de atualização) de cada aba.
- Rodapé do sidebar (`vX.X · Atualizado DD/MM/AAAA às HH:MM`) reflete a hora de SINCRONIZAÇÃO do arquivo unificado (agora, quando a IA aplica a atualização), não a data do dado em si — são conceitos diferentes, não confundir.
- Hora usada sempre em horário de Brasília: `TZ=America/Sao_Paulo date "+%d/%m/%Y às %H:%M"`.
- Título/data/versão de cada aba vêm SEMPRE do `TAB_METAS`/info-bar compartilhado — não duplicar um `<header><h1>...</h1></header>` próprio dentro do corpo do módulo (remover se o arquivo-fonte trouxer um).
- Cor do módulo: escolher um `iconColor`/`iconBg` (RGBA com alpha ~0.13) que não repita as cores já usadas pelos outros módulos no `TABS`, e um símbolo (`icon`, um único caractere/emoji) que faça sentido temático (ex: `⌂` para Vendas de imóveis, `%` para Comissão).

## Programações de atualização combinadas (editar aqui se mudar)

- Daily Briefing: atualizado a cada nova rodada de dados dos outros módulos
- Financeiro A Pagar/Pago: Seg-Ter-Qua-Sex (14h PGT) - Qui (16h PGT + Programação semanal)
- A Receber: Terças-feiras às 10h
- Global Mensal: Parcial quartas-feiras às 10h - Final após fechamento do mês
- Contratos: diariamente às 14h e 18h
- Conciliação: diariamente às 14h
- Comissão: segundas-feiras às 10h
- Vendas: quintas-feiras às 10h

## Preferências de estilo de trabalho do Luiz

- Respostas curtas e diretas, sem floreio.
- Sempre listar as etapas na aba "Progresso" (task list) antes de agir em qualquer tarefa com múltiplos passos, e ir marcando conforme avança — ele acompanha por ali, não precisa narrar tudo em texto.
- Antes de aplicar atualização de dados, sempre listar o que foi encontrado e esperar confirmação (nunca aplicar direto).
- Prefere que decisões de normalização/edição de dados (não só bug técnico) sejam perguntadas antes de aplicar.
- A pasta no computador do Luiz às vezes desconecta durante a sessão — se acontecer, avisar e seguir com o arquivo anexado diretamente no chat para não perder tempo, mas voltar a ler/gravar pela pasta assim que ela reconectar.
