# Assistente de pesca (Windows)

## Modo automatico (experimental)

Use **Python 3.12 de 64 bits**. No terminal aberto nesta pasta, prepare o ambiente uma vez:

```bat
py -3.12 -m venv .venv-auto
.venv-auto\Scripts\python.exe -m pip install -r requirements-auto.txt
```

Se voce ja tem `.venv-auto`, basta atualizar os arquivos do programa e instalar as dependencias com o segundo comando. Nao apague seu ambiente existente.

### Inicio rapido e executavel

O programa abre um painel flutuante com estado atual, barra detectada, OCR carregando/pronto, FPS medido, bloco dentro/fora da zona e entradas de mouse/T. Os botoes Iniciar, Pausar e Encerrar complementam F8/Esc. Iniciar tenta focar o Roblox e posiciona o ponteiro numa area do jogo para nao clicar no proprio painel. Coloque o painel fora da barra e do aviso Collect; o local inicial fica no canto esquerdo. Perda de foco continua pausando. O contador de coletas registra o desaparecimento do aviso apos T, nao confirma inventario ou identifica o item.

Ao atualizar, copie todos os arquivos Python, incluindo **hub.py**, **cycle.py**, **vision_text.py** e **telemetry.py**, para a mesma pasta de fishing_auto.py. Preserve `.venv-auto`. Para atualizar um EXE ja gerado, feche o app e execute gerar_exe.bat novamente. O novo executavel usa o painel sem janela de console. Se houver **icone.ico** junto do script, o icone sera incluido automaticamente. A interface e a integracao com o jogo ainda precisam de validacao no Windows.

A versao atual aceita `--auto-start`: inicia em tres segundos e tenta focar a janela de titulo Roblox. Deixe o jogo aberto, a vara equipada e o ponteiro no local usado para pescar. Perda de foco pausa; F8 retoma e Esc encerra. Execute `iniciar_auto.bat` com dois cliques para usar o ambiente `.venv-auto` existente. O primeiro lancamento nao espera a inicializacao do OCR, que ocorre em paralelo. A coleta continua dependendo do OCR.

Para gerar o executavel **no Windows**, execute `gerar_exe.bat`. Ele instala PyInstaller no ambiente separado e empacota os modelos do OCR e o runtime ONNX. O resultado esperado e `dist\PescaAuto\PescaAuto.exe`: mantenha toda a pasta PescaAuto junto. Use um atalho para abrir com um clique; o executavel inicia automaticamente. Foi escolhido o formato de pasta para evitar a extracao de um executavel unico a cada abertura. O painel mostra estado e erros durante a execucao. A geracao e execucao do EXE ainda precisam de validacao no Windows; nao foram executadas neste ambiente Linux.

O controlador usa por padrao ate 90 capturas por segundo, suavizacao da velocidade baseada no tempo e antecipacao limitada do movimento da zona. A frequencia real depende do PC. Compare no jogo; precisao superior ainda nao foi medida. Se oscilar, teste `--lookahead 0.06`; para restaurar a frequencia anterior, use `--fps 60`. Esses parametros tambem podem ser passados ao executavel.

Para iniciar manualmente, execute `.venv-auto\Scripts\python.exe fishing_auto.py`.
Nao precisa selecionar a barra. Deixe o Roblox em foco com a vara equipada e o ponteiro onde o jogo recebe o clique; F8 inicia/pausa e Esc encerra. O programa captura a area da janela em foco cujo titulo contem Roblox, procura a barra de borda branca com bloco branco e zona verde/amarela e controla o clique. Reconhece a palavra inglesa Collect por OCR para segurar T; solta quando o aviso desaparece. O nome e a aparencia do peixe nao sao usados.

A busca da barra e a coleta ainda precisam de validacao no Windows/Roblox. O primeiro minigame pode ser perdido enquanto a barra e localizada. Mantenha a interface em ingles. Perda de foco pausa e solta os controles. Nao ha garantia de reconhecimento em outras cores, escalas ou layouts. Nao requer Tesseract separado.

### Coleta, pulo periodico e diagnostico

Depois que a barra some, o programa espera ate 12 segundos pelo aviso de coleta antes de preparar outro lancamento. O OCR procura primeiro na area central e, se necessario, amplia a busca; reconhece pequenas variacoes de leitura de Collect. Ao coletar, mantem T pressionado durante falhas curtas do OCR. So registra uma coleta depois de pelo menos tres leituras distintas sem o aviso, cobrindo 1,5 segundo. Isso confirma o desaparecimento do aviso, nao a entrada do item no inventario. Coleta que exceda 45 segundos ou OCR desatualizado por muito tempo pausa com motivo no hub.

O pulo periodico usa Espaco e vem ativado com intervalo de **120 segundos**. Altere o campo "Pular a cada (s)" no hub e confirme com Enter, ou use `--jump-interval 180` no terminal. `0` desativa. O pulo e adiado ate o intervalo entre pescas, sem barra ou coleta em andamento; nao envia teclas com o app pausado ou sem foco no Roblox. Isso tenta manter atividade, mas nao garante que o servidor deixara de desconectar por inatividade e nao impede desconexoes de rede. Nao faz reconexao automatica. Um aviso de desconexao reconhecido pelo OCR pausa a automacao; reconecte e use Iniciar.

Se nao aparecer minigame por 45 segundos depois do lancamento, uma leitura recente sem Collect permite uma nova tentativa apos uma pequena espera. Pescas sem aviso de coleta e tentativas sem barra entram no contador **Sem confirmacao**, separado de coletas detectadas. Esse contador nao prova que um item foi perdido.

O registro de estados, tentativas, pulos e erros fica em `%LOCALAPPDATA%\PescaAuto\pesca.log`, com rotacao para limitar o tamanho. Nao grava capturas de tela nem o texto completo reconhecido. Para analisar uma falha, anote o horario e consulte esse arquivo. As mudancas foram testadas em cenarios simulados; comportamento prolongado, pulos e coleta precisam ser confirmados no jogo.

Os testes de temporizacao e reconhecimento de texto podem ser executados sem o jogo:

```bat
py -3.12 -m unittest discover -s tests -v
```

## Modo com selecao manual

No PowerShell, nesta pasta:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe fishing.py --observe
```

Deixe o minigame visível antes de iniciar. Na captura de tela, selecione **somente a barra inteira**, incluindo as bordas, e pressione Enter. Uma janela mostrará as detecções: branco para o bloco e magenta para a zona. Primeiro confira se ambas acompanham os objetos corretamente.

Para controlar o mouse, encerre a observação e execute:

```powershell
.\.venv\Scripts\python.exe fishing.py
```

Depois da seleção, volte ao Roblox e coloque o ponteiro no local onde o jogo recebe o clique. **F8** alterna entre iniciar e pausar; **Esc** encerra. Inicie somente com o jogo em foco. Ao pausar, perder a detecção ou encerrar, o programa solta o botão. O programa não muda o foco nem move o ponteiro.

Segurar faz o bloco subir; soltar faz descer. O controlador estima a velocidade para antecipar a frenagem. Se oscilar demais, experimente `--lookahead 0.04`; se reagir tarde, `--lookahead 0.12`. Padrão: 0.08 segundos. `--fps 60` limita a frequência de captura. Não altere resolução ou posição da janela durante uma sessão.

Esta versão usa as cores das imagens fornecidas: bloco branco e zona verde/amarela. Ela precisa ser calibrada e validada no seu PC; não foi testada no Roblox neste ambiente. Use onde a automação é permitida, sem tentar contornar bloqueios do jogo.

Para lançar a vara com um clique rápido e repetir entre pescas, execute `fishing.py --auto-cast`. Selecione a região com a barra visível, depois pause e volte ao jogo. F8 ativa o controle: se o minigame já estiver visível, controla o bloco; caso contrário, lança uma vez e aguarda. Após dois segundos sem detectar o minigame, aguarda mais três segundos e lança novamente. Se a vara não lançar ou houver uma tela de resultado impedindo a próxima pesca, pause com F8 e resolva manualmente. Não há repetição de cliques enquanto espera uma fisgada. Perdas prolongadas de detecção podem ser confundidas com o fim da pesca.
