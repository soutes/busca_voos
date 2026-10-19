# Guia completo para quem nunca mexeu com programação

Este guia foi escrito para você usar o **busca_voos** sem precisar entender de
computador além do básico (baixar arquivo, dar duplo clique, copiar e colar).
Siga as etapas na ordem. No final você terá:

- um robô que fica de olho nos preços das passagens que você escolher;
- um e-mail automático avisando quando o preço ficar dentro do seu limite;
- um painel no navegador para ver o histórico de preços.

**Importante:** o programa **não compra passagens**. Ele só procura e avisa.
Quando o e-mail chegar, você clica no link e compra no site da companhia.

---

## Antes de começar — o que você vai precisar

| Item | Para quê | Custo |
|---|---|---|
| Um computador com internet | rodar o programa | — |
| Uma conta Gmail nova ou existente | **enviar** os avisos | grátis |
| Um celular | para ativar a verificação em duas etapas do Gmail | — |
| 40 a 60 minutos do seu tempo | instalação e configuração | — |

Se você vai usar no **Windows** (o caso mais comum), siga as etapas 1 a 7.
Se vai usar em um **servidor Linux**, siga a etapas 1 a 3 e depois a seção
"Usando no Linux", lá no fim.

---

## Etapa 1 — Criar o e-mail que vai enviar os avisos

O programa envia os e-mails **de** uma conta Gmail **para** a sua caixa
pessoal. Recomendamos criar um Gmail **só para o programa** (por exemplo
`seunome.buscavoos@gmail.com`): assim, se algo der errado com essa senha, a
sua conta pessoal não fica exposta. Você continua recebendo os alertas no seu
e-mail de sempre, porque ele entra como **destinatário**.

1. Abra o navegador e acesse **accounts.google.com**.
2. Clique em **Criar conta** → **Para uso pessoal**.
3. Preencha nome, data de nascimento e escolha um endereço (ex.:
   `seunome.buscavoos@gmail.com`).
4. Crie uma senha e **anote-a** (essa é a senha da conta, usada raramente — a
   senha que o programa usa é outra, que criaremos na etapa seguinte).
5. Confirme o cadastro informando um celular (o Google pede para verificar).

Pronto. Guarde essa senha da conta num lugar seguro.

---

## Etapa 2 — Criar a "senha de app" do Gmail

O Gmail não aceita que programas externos usem a senha normal da conta. Por
isso o Google tem as **senhas de app**: senhas de 16 letras e números, criadas
só para um programa, que podem ser apagadas a qualquer momento.

Use a senha de app **nunca** a senha da conta.

1. Entre na conta Gmail que você criou (ou que vai usar para enviar).
2. Acesse **myaccount.google.com/security**.
3. Localize **Verificação em duas etapas** e clique em **Ativar**. Siga os
   passos (o Google vai pedir seu celular para enviar um código). Essa etapa é
   obrigatória: sem ela, a opção de senha de app não aparece.
4. Volte ao menu e acesse **myaccount.google.com/apppasswords**.
   - Se a página não abrir, vá em **myaccount.google.com**, digite
     `Senhas de app` na barra de busca do site e clique no resultado.
5. No campo "Nome do app", escreva `busca_voos` e clique em **Criar**.
6. O Google vai mostrar uma senha de **16 caracteres** (ex.:
   `abcd efgh ijkl mnop`). **Copie e guarde-a** — ela só é mostrada uma vez.

Anote essa senha de 16 caracteres sem os espaços:
`abcdefghijklmnop`. Você vai colá-la no programa na etapa 5.

> Se perder a senha, não tem problema: na mesma página você apaga a antiga e
> cria outra em segundos. Contas de empresa ou escola, ou com a "Proteção
> Avançada" do Google, podem não oferecer essa opção — nesse caso, use outra
> conta Gmail pessoal.

---

## Etapa 3 — Baixar o programa

1. Abra **github.com/soutes/busca_voos** no navegador.
2. Clique no botão verde **`<> Code`**.
3. No menu que abre, clique em **Download ZIP**.
4. O navegador vai baixar um arquivo `busca_voos-main.zip` (normalmente na
   pasta **Downloads**).
5. Clique com o **botão direito** no arquivo → **Extrair tudo** → confirme.
   Vai surgir uma pasta com todo o programa.

Dentro dela existem duas subpastas, e você vai usar só a que corresponde ao
seu sistema:

| Pasta | Para quem | Como começar |
|---|---|---|
| `vs_win` | Windows | duplo clique em `INSTALAR.bat` (etapa 4) |
| `vs_linux` | Linux (servidor) | terminal: `bash instalar.sh` (seção "Usando no Linux") |

> Existe também um **guia interativo**: abra o arquivo `GUIA_INSTALACAO.html`
> com duplo clique (ele abre no navegador). Ele tem a mesma lista de etapas em
> formato de lista de verificação, com botões de copiar os comandos — dá para
> marcar cada item conforme termina.

---

## Etapa 4 — Instalar no Windows

### 4.1 Instalar o Python (uma vez)

O programa é escrito em Python, então o computador precisa dele. Se você já
tem, pode pular.

1. Acesse **python.org/downloads** e clique em **Download Python 3.x**.
2. Execute o instalador. Na **primeira tela**, marque a caixa
   **"Add python.exe to PATH"** — sem isso a instalação não funciona depois.
3. Clique em **Install Now** e aguarde terminar.

### 4.2 Instalar o Google Chrome (opcional, mas recomendado)

As fontes LATAM, GOL e Azul usam o Chrome instalado no computador. As outras
fontes funcionam sem ele. Se quiser esses resultados também, instale o Chrome
em **google.com/chrome**.

### 4.3 Rodar o instalador do programa

1. Entre na pasta `vs_win` que você extraiu.
2. Dê **duplo clique em `INSTALAR.bat`** e espere — pode levar alguns
   minutos na primeira vez (baixa um navegador auxiliar de ~150 MB).
3. Quando aparecer a mensagem de que terminou, feche a janela.

Isso cria tudo o que o programa precisa dentro da própria pasta — nada é
instalado em outro lugar do computador.

---

## Etapa 5 — Onde colocar as suas informações (rotas e senha)

Aqui ficam as duas perguntas que o programa precisa que você responda:
**quais rotas monitorar** e **qual é a senha de app**.

### 5.1 As rotas — arquivo `config.yaml`

1. Na pasta `vs_win`, clique com o botão direito em `config.yaml` →
   **Abrir com** → **Bloco de Notas**.
2. Procure a seção `rotas:` e ajuste uma rota de exemplo para a sua. Cada rota
   tem este formato:

```yaml
  - origem: FLN          # aeroporto de saída (3 letras, ex.: FLN = Florianópolis)
    destino: RIO         # aeroporto de chegada (RIO = Rio de Janeiro)
    janela_ida:   { de: 2026-12-25, ate: 2026-12-27 }   # dias possíveis de ida
    janela_volta: { de: 2027-01-04, ate: 2027-01-09 }   # dias possíveis de volta
    preco_maximo: 800    # avisa por e-mail se achar por R$ 800 ou menos
```

3. Na seção `email:`, confira:
   - `de:` o Gmail criado na etapa 1 (quem **envia**);
   - `para:` o seu e-mail pessoal (quem **recebe**).
4. Salve o arquivo e feche o Bloco de Notas.

> Os códigos de aeroporto são os oficiais de 3 letras: FLN (Florianópolis),
> GRU (Guarulhos), GIG (Galeão/Rio), BSB (Brasília), SSA (Salvador),
> POA (Porto Alegre), CWB (Curitiba), entre outros.

### 5.2 A senha de app — duas formas (escolha uma)

**Forma A — pelo painel (mais fácil, mais seguro).** O painel guarda a senha
de forma **criptografada** dentro do banco de dados do próprio computador:

1. Dê duplo clique em `ABRIR_PAINEL.bat` e espere abrir o navegador.
2. Clique na aba **Gestão & configurações**.
3. Em **Notificações por e-mail**, confira os e-mails de envio e de
   recebimento e cole a senha de app (aquela de 16 caracteres) no campo
   **Senha de aplicativo**.
4. Clique em **Salvar configurações**.
5. Clique no **botão de teste de e-mail** e veja se a mensagem chega na sua
   caixa pessoal. Chegou? Está tudo funcionando.

**Forma B — pelo arquivo `.env`.** Se preferir editar o arquivo diretamente:

1. Botão direito em `.env` → **Abrir com** → **Bloco de Notas**.
2. Na linha `SMTP_SENHA=`, cole a senha de app logo depois do `=`
   (sem espaços): `SMTP_SENHA=abcdefghijklmnop`.
3. Salve e feche.
4. Para testar, dê duplo clique em `ABRIR_PAINEL.bat` → aba
   **Gestão & configurações** → botão de teste de e-mail.

---

## Etapa 6 — O primeiro teste

1. Duplo clique em `RODAR_CICLO.bat` → `--sem-email`
   *(ou apenas `RODAR_CICLO.bat`)*.

   > Dica de leigo: para passar esse parâmetro, abra o PowerShell na pasta
   > (clique na barra de endereço da pasta, digite `powershell`, Enter) e
   > digite `.\RODAR_CICLO.bat --sem-email`. Sem `--sem-email` ele já pode
   > enviar e-mail de verdade se achar preço dentro do limite.

2. Espere alguns minutos. A janela mostra cada fonte sendo consultada e os
   preços encontrados.
3. Duplo clique em `ABRIR_PAINEL.bat` para ver o painel com o resultado.

Se der qualquer mensagem de erro, veja a tabela "Problemas comuns" no fim
deste guia.

---

## Etapa 7 — Usar no dia a dia (Windows)

| Arquivo (duplo clique) | O que faz |
|---|---|
| `RODAR_CICLO.bat` | faz **uma busca agora** e fecha |
| `RODAR_DAEMON.bat` | fica **buscando de hora em hora** — deixe essa janela aberta |
| `ABRIR_PAINEL.bat` | abre o painel no navegador (histórico de preços, alertas) |
| `atualizar.bat` | prepara atualizações futuras do programa |

### Como funciona a periodicidade

O arquivo `config.yaml` tem a seção `agenda:`, com `intervalo_minutos` — de
quantas em quantas horas o programa repete a busca (o padrão é a cada 8
horas). O app tem limites próprios para evitar bloqueio dos sites: não
pergunte mais rápido que isso.

### Deixar rodando sozinho ao ligar o computador (opcional)

1. Aperte a tecla **Windows**, digite **Agendador de Tarefas** e abra.
2. À direita, **Criar Tarefa Básica**.
3. Nome: `busca_voos`. Disparador: **Ao fazer logon**.
4. Ação: **Iniciar um programa** → aponte para o `RODAR_DAEMON.bat`
   da pasta do programa.
5. Pronto: ao ligar o computador, o monitor começa sozinho (a janela fica
   aberta minimizada; fechá-la encerra o monitor).

---

## Usando no Linux (servidor 24/7)

Esta seção é para quem tem um servidor Linux (ex.: uma VPS alugada) e quer o
programa rodando 24 horas por dia, sem computador ligado em casa. O jeito
mais amigável de usar um servidor é pelo **terminal** (uma janela preta de
comandos) via SSH.

### L1. Preparar o servidor (uma vez)

Conecte ao servidor pelo terminal (no Windows, o próprio PowerShell faz isso:
`ssh seu_usuario@endereco-do-servidor`) e rode:

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
```

### L2. Baixar e instalar o programa

```bash
cd ~
wget https://github.com/soutes/busca_voos/archive/refs/heads/main.zip -O busca_voos.zip
unzip busca_voos.zip
mv busca_voos-main busca_voos
cd busca_voos/vs_linux
bash instalar.sh
```

O `instalar.sh` cria tudo: ambiente Python, dependências, navegador auxiliar,
`config.yaml`, `.env` e o banco vazio. Ele **não sobrescreve** nada que já
exista, então pode rodar de novo sem medo.

### L3. Configurar rotas e senha

Edite os dois arquivos com o editor `nano` (salva com **Ctrl+O**, Enter; sai
com **Ctrl+X**):

```bash
nano config.yaml   # rotas, e-mail de/para (igual à etapa 5.1 acima)
nano .env          # SMTP_SENHA= a senha de app de 16 caracteres (etapa 5.2, forma B)
```

### L4. Testar

```bash
.venv/bin/busca-voos uma --sem-email    # um ciclo, sem enviar e-mail
.venv/bin/busca-voos email-teste        # valida o Gmail (deve dizer que enviou)
```

### L5. Deixar rodando 24/7 (serviço do sistema)

```bash
bash instalar_servico.sh --painel
```

Esse script cria dois serviços que **ligam sozinhos quando o servidor
reinicia** e se recuperam sozinhos se caírem:

| Serviço | O que faz | Comando de acompanhamento |
|---|---|---|
| `busca-voos` | busca de hora em hora | `journalctl -u busca-voos -f` |
| `busca-voos-painel` | painel web na porta 8787 | (nada — veja L6) |

Para ver o estado: `sudo systemctl status busca-voos`.
Para reiniciar depois de trocar o config: `sudo systemctl restart busca-voos`.
Para desligar tudo: `bash instalar_servico.sh --parar`.

### L6. Abrir o painel no seu computador (túnel SSH)

O painel do servidor só aceita acesso local, por segurança. No **seu**
computador (Windows), abra o PowerShell e rode:

```powershell
ssh -L 8787:127.0.0.1:8787 seu_usuario@endereco-do-servidor
```

Mantenha essa janela aberta e acesse **http://127.0.0.1:8787** no navegador.
Enquanto o túnel estiver aberto, o painel funciona como se estivesse no seu
computador. Fechou a janela? Basta rodar o comando de novo.

### L7. Mudando de servidor ou reinstalando

O histórico e as configurações vivem em quatro arquivos dentro da pasta do
programa: `config.yaml`, `.env`, `dados.sqlite3` (histórico) e `.segredo.key`
(chave que decifra a senha salva pelo painel). Se for trocar de servidor,
copie esses quatro arquivos para a nova pasta com o comando `scp` **antes** de
rodar `instalar.sh` — assim o histórico e o e-mail continuam funcionando.
Nunca compartilhe nem publique esses arquivos: eles contêm seus segredos.

---

## Problemas comuns

| O que aconteceu | Provável causa | O que fazer |
|---|---|---|
| "Não encontrei o Python" na instalação | Python sem a caixa PATH marcada | desinstale, reinstale marcando **"Add python.exe to PATH"**, rode o `INSTALAR.bat` de novo |
| E-mail não chega | senha de app errada/ausente | refaça a etapa 5.2; teste pelo botão do painel |
| E-mail não chega (2) | e-mail na caixa de spam | procure por `busca_voos` no spam e marque como confiável |
| Nenhum preço aparece no painel | fontes bloquearam o IP momentaneamente | espere um ciclo; o app pula a fonte bloqueada e continua com as outras |
| "Banco não existe ainda" no painel | nenhum ciclo rodou ainda | rode `RODAR_CICLO.bat` uma vez antes de abrir o painel |
| Muda o computador/servidor | — | veja a etapa L7 (copiar os 4 arquivos de estado) |

---

## Resumo de segurança (importante)

1. **Use senha de app, nunca a senha da conta Gmail.** Se vazar, apague-a na
   página de senhas de app e crie outra.
2. Os arquivos `.env`, `.segredo.key` e `dados.sqlite3` contêm segredos e
   histórico pessoal. Não envie por WhatsApp/e-mail, não publique na internet.
3. Se um dia você escreveu uma senha dentro de algum arquivo de código,
   **revogue** a senha de app correspondente na conta Google.
4. O painel não tem senha: no Windows ele só responde ao próprio computador; no
   servidor só pelo túnel SSH da etapa L6.

---

## E depois?

- Quer adicionar ou mudar rotas? Edite o `config.yaml` (etapa 5.1) e, no
  Linux, rode `sudo systemctl restart busca-voos` para valer na hora; no
  Windows, reinicie o `RODAR_DAEMON.bat`.
- Quer detalhes técnicos (todas as opções, fontes, limites)? O `README.md`
  desta pasta é a referência completa.
