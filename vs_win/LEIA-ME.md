# busca_voos no Windows — comece aqui

Monitor de passagens aéreas: procura as rotas/datas que você definir em
`config.yaml`, em várias fontes, e te manda um e-mail quando o preço cair.
Tem também um painel local com o histórico de preços.

## 1. Instalar (uma vez só)

**Duplo clique em `INSTALAR.bat`** e espere — pode levar alguns minutos.
Ele cria o ambiente Python isolado na pasta `.venv`, instala o app e o painel,
baixa o navegador usado pelo Skyscanner/Trip.com (~150 MB) e cria o
`config.yaml`, o `.env` e o banco vazio.

Antes disso você precisa do **Python 3.10 ou mais novo** instalado
(https://www.python.org/downloads/), marcando a caixa
**"Add python.exe to PATH"** durante a instalação.

## 2. Configurar

Abra o **`config.yaml`** no Bloco de Notas e ajuste:

- `rotas:` — `origem`/`destino` com código de aeroporto (ex.: `FLN` → `RIO`),
  as janelas de data e o `preco_maximo` que dispara o alerta;
- `email.de` — a conta que **envia**;
- `email.para` — quem **recebe**.

Para receber e-mail, abra o **`.env`** e preencha `SMTP_SENHA=` com uma
**senha de app** do Gmail (https://myaccount.google.com/apppasswords) — a senha
normal da conta não funciona aqui. Sem isso o app só registra no log.

## 3. Usar

| Arquivo (duplo clique) | O que faz |
|---|---|
| `RODAR_CICLO.bat` | faz uma busca agora e sai |
| `RODAR_DAEMON.bat` | fica buscando a cada hora — deixe a janela aberta |
| `ABRIR_PAINEL.bat` | abre o painel no navegador (histórico, preços, alertas) |

Para um teste sem enviar e-mail: `RODAR_CICLO.bat --sem-email`.

## 4. Deixar rodando sozinho (opcional)

1. Abra o **Agendador de Tarefas** → *Criar Tarefa Básica*.
2. Disparador: **Ao fazer logon**.
3. Ação: *Iniciar um programa* → aponte para `RODAR_DAEMON.bat` desta pasta.
4. Marque *Executar somente quando o usuário estiver conectado*.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `Nao encontrei Python 3.10 ou mais novo` | instale do python.org marcando "Add python.exe to PATH" |
| `O pip nao esta funcionando` | no instalador do Python escolha **Repair** |
| Fonte não traz preço nenhum | Google/Skyscanner bloqueiam por IP: tente mais tarde ou use `navegador: { canal: chrome }` no config |
| `google_flights: nenhum resultado parseado` | o site mudou o layout — veja a tabela do `README.md` |
| Painel diz "Banco ... nao existe ainda" | rode `RODAR_CICLO.bat --sem-email` uma vez |
| Painel não abre / porta em uso | feche a outra janela do painel, ou `ABRIR_PAINEL.bat --porta 8788` |
| E-mail não chega | confira `SMTP_SENHA` no `.env` e `email.de`/`email.para` no config; teste com `email-teste` |

O `README.md` (nesta pasta) tem a referência completa de configuração e a
lista de fontes. Dúvidas de scraping/bloqueio estão na seção **Bloqueios** dele.
