# iFaceMatch — Manual operacional de build, release e atualização

**Documento:** RUNBOOK-RELEASE-001  
**Versão do documento:** 1.0  
**Data de referência:** 12/11/2026  
**Responsáveis:** Engenharia (build/assinatura), Release Manager (publicação), Operações (implantação)  
**Escopo validado:** Customer Hosted, Ubuntu 24.04 AMD64, release `0.1.11` do Console.  
**Estado:** Procedimento `0.1.11` executado em produção e validado; **não é ainda um mecanismo genérico para versões futuras**.

> **LEIA ANTES DE EXECUTAR:** o repositório `jefersonMarques/ifacematch` é público. Não adicione nele chaves privadas, dados pessoais de clientes, IPs/credenciais de produção, licenças, backups nem segredos. O download da release é público; a autorização de uso é controlada por licença.

## Sumário

1. [Visão geral e responsabilidades](#1-visão-geral-e-responsabilidades)
2. [Preparação do ambiente de build](#2-preparação-do-ambiente-de-build)
3. [Testes e binários de desenvolvimento](#3-testes-e-binários-de-desenvolvimento)
4. [Gerar e assinar a release comercial](#4-gerar-e-assinar-a-release-comercial)
5. [Publicar no GitHub Releases](#5-publicar-no-github-releases)
6. [Atualizar a VPS do cliente](#6-atualizar-a-vps-do-cliente)
7. [Homologar e encerrar a implantação](#7-homologar-e-encerrar-a-implantação)
8. [Rollback e recuperação](#8-rollback-e-recuperação)
9. [Diagnóstico de erros comuns](#9-diagnóstico-de-erros-comuns)
10. [Regras para versões futuras](#10-regras-para-versões-futuras)
11. [Checklist e evidências](#11-checklist-e-evidências)

## 1. Visão geral e responsabilidades

Fluxo:

~~~text
Repositórios dos componentes (commits fixados)
                 |
                 v
FACTORYAPPS / equipe de build
make bootstrap -> make test -> make release -> make release-verify
                 |
                 v
GitHub Releases — pacote assinado, SHA256SUMS e atualizador
                 |
                 v
VPS Customer Hosted
download -> SHA-256 -> Ed25519 -> staging -> troca do Console
                 |
                 v
Health checks -> login real -> aprovação ou rollback
~~~

| Papel | Responsabilidade | Ambiente |
|---|---|---|
| Desenvolvimento | Revisar código, aprovar commits, manter testes e `versions.lock.json` | Repositórios de componentes |
| Operador de build | Compilar, testar e assinar com a chave autorizada | WSL/Ubuntu autorizado |
| Release Manager | Autorizar e executar a publicação imutável por política | GitHub Releases |
| Operações | Confirmar backup, executar atualização e registrar evidências | VPS do cliente |
| Homologação | Validar API, login, biometria necessária e resultado de negócio | Aplicação e VPS |

**Separação importante:** `make release` cria pacote local; `make publish` publica no GitHub; instalar na VPS é outra operação. Nenhum deles deve ser confundido com aprovação de produção.

### Onde fica cada componente

| Componente | Local |
|---|---|
| Coordenador | `/opt/iFaceMatch/ifacematch` |
| Server | `/opt/iFaceMatch/ifacematch-server` |
| Console | `/opt/iFaceMatch/ifacematch-console` |
| Admin/Central e ferramentas de release | `/opt/iFaceMatch/ifacematch-admin` |
| Site/Portal | `/opt/iFaceMatch/ifacematch-site` |
| Controle de revisões | `versions.lock.json` no coordenador |
| Binários de desenvolvimento | `dist/build/` |
| Releases comerciais locais | `dist/releases/<version>/` |
| Distribuição pública | [GitHub Releases](https://github.com/jefersonMarques/ifacematch/releases) |
| Releases instaladas na VPS | `/opt/ifacematch/releases/<version>/` |

## 2. Preparação do ambiente de build

A execução de referência utiliza WSL Ubuntu 24.04 na FACTORYAPPS. São necessários `git`, Go, `python3`, `make`, `tar`, `sha256sum`, `bash` e acesso aos repositórios privados. Para publicar também são necessários `gh`, autenticação GitHub e acesso de escrita ao repositório coordenador.

A chave **privada de assinatura Ed25519** deve permanecer exclusivamente na estação de assinatura:

- `~/.config/ifacematch/distribution/distribution.private` (permissão 0600).
- `~/.config/ifacematch/distribution/distribution.public` (permissão 0600 no build atual).
- Identificador de distribuição: `ifm_distribution_prod_v1`.

**Nunca:** executar build comercial como root, copiar a chave privada à VPS, enviar chave para o GitHub ou incluir segredos em logs/chats.

### Preparar e atualizar o coordenador

~~~bash
cd /opt/iFaceMatch/ifacematch

git pull --ff-only

make doctor
make bootstrap
~~~

O `bootstrap` obtém os commits fixados dos quatro repositórios sem sobrescrever os worktrees existentes. O build utiliza snapshots desses commits, não necessariamente o HEAD das pastas locais.

Conferir as revisões aprovadas:

~~~bash
cat versions.lock.json
~~~

**Critério de passagem:** nenhuma referência inválida ou commit fixado ausente. Resolver divergências antes de gerar o pacote. Não alterar o lockfile apenas para contornar uma falha.

## 3. Testes e binários de desenvolvimento

### Executar a suíte integrada

~~~bash
cd /opt/iFaceMatch/ifacematch

make test
~~~

Ela executa os testes do coordenador, `go test ./...` e `go vet ./...` dos componentes relevantes e verificações de sintaxe/empacotamento conforme os commits fixados.

**Critério de passagem:** todos os testes retornam sucesso. Se falharem, interromper o processo e corrigir o componente de origem; não publicar uma release baseada em testes reprovados.

### Gerar binários locais para desenvolvimento (opcional)

~~~bash
make build
~~~

Produz em `dist/build/`:

- `ifacematch-server`
- `ifacematchctl`
- `ifacematch-console`
- `releasecheck`
- `releasepack`
- `releasebundle`

**Atenção:** esses binários **não são uma release comercial assinada**. Não copiá-los para clientes. O destino `dist/build/` é preservado: nova execução do comando é bloqueada quando já existe um build anterior. Não remover esse diretório sem autorização de quem o utiliza.

## 4. Gerar e assinar a release comercial

> A implementação atual de `make release` aceita **somente a transição 0.1.10 → 0.1.11**, trocando apenas o Console e sua proveniência. Usar `VERSION=0.1.12` ou outro número **não cria automaticamente um novo adaptador**.

### Pré-requisitos da 0.1.11

- Testes aprovados.
- Pacote-base comercial `0.1.10` disponível na estação autorizada.
- Chaves de assinatura originais disponíveis; não gerar novas chaves.
- Diretorio `dist/releases/0.1.11/` ainda não existe se o build será realizado pela primeira vez.
- Alterações aprovadas e fixadas em `versions.lock.json`.

Hash conhecido do pacote-base `0.1.10`:

~~~text
e6d0e991694c471c79e4d2e6d02f641b5144ec48d3f4bb9900b4eaca1ba5373e
~~~

Caso o arquivo-base não esteja na máquina, obtê-lo de armazenamento autorizado e colocá-lo em `dist/releases/0.1.10/`; **não baixar uma versão desconhecida e não editar seu conteúdo**. O comando a seguir confirma a descoberta automática e o checksum:

~~~bash
make release-base
~~~

### Compilar e assinar (somente quando ainda não existe o pacote)

~~~bash
make release VERSION=0.1.11
make release-verify VERSION=0.1.11
~~~

O processo executa os testes específicos do Console, monta o pacote completo com os componentes preservados, assina com Ed25519 e verifica que apenas o Console mudou em relação à base.

Arquivos esperados:

~~~text
dist/releases/0.1.11/
├── ifacematch-0.1.11-ubuntu-amd64.tar.gz
├── SHA256SUMS
└── BUILD_DETAILS.txt
~~~

**Critério de passagem:** `[PASS] Signed release verified`, hash SHA-256 correto, e `[PASS] Signed 0.1.11 modifies only the Console and its provenance`.

Hash aprovado da `0.1.11`:

~~~text
4a44480bc5fe340ae1c26405284599560325807ac88c8c0daab8a645df10dc32
~~~

**Não repetir `make release` se o pacote já existe.** O coordenador recusa sobrescrita para preservar a cadeia de evidências. Para confirmar uma versão já gerada, execute somente:

~~~bash
make release-verify VERSION=0.1.11
~~~

## 5. Publicar no GitHub Releases

### Pré-condições

1. Aprovação da release, licença de componentes de terceiros e notas da versão.
2. Arquivo assinado aprovado e verificado no build local.
3. GitHub CLI autenticado na conta de publicação.
4. Commit atual do coordenador igual ao `main` remoto e sem alterações locais rastreadas.
5. Tag `v0.1.11` **ainda não publicada**.

### Publicação da primeira versão aprovada

~~~bash
cd /opt/iFaceMatch/ifacematch

git pull --ff-only

gh auth status || gh auth login

make release-verify VERSION=0.1.11
make publish VERSION=0.1.11
~~~

O publicador valida o hash fixado, a assinatura, o script de atualização, a visibilidade pública e a inexistência de tag/release. Então cria a tag `v0.1.11`, envia os assets e baixa os próprios arquivos publicados para conferir os digests.

**Os três assets da 0.1.11:**

1. `ifacematch-0.1.11-ubuntu-amd64.tar.gz`
2. `SHA256SUMS`
3. `ifacematch-update.sh`

**O que não vai para o GitHub:** chave privada, licença de cliente, banco, dados biométricos, arquivos de ambiente ou credenciais.

**Importante:** não executar `make publish` novamente para uma tag existente. Isso deve retornar bloqueio, não deve substituir a versão. Consultar a release publicada:

~~~bash
gh release view v0.1.11 \
    --repo jefersonMarques/ifacematch
~~~

Link da versão executada: [iFaceMatch v0.1.11](https://github.com/jefersonMarques/ifacematch/releases/tag/v0.1.11).

## 6. Atualizar a VPS do cliente

> **Procedimento validado exclusivamente para a VPS-piloto com hostname `srv855672`, versão instalada `0.1.10` e destino `0.1.11`.** Não utilizar o script atual para novo cliente, outra versão, instalação limpa nem repetir sobre a 0.1.11 ativa.

### 6.1 Conferência prévia — equipe de Operações

Antes de alterar produção:

- Confirmar autorização de implantação e janela de manutenção.
- Ter snapshot/backup externo recuperável **antes** da alteração.
- Verificar espaço em disco, versão atual, unidades e saúde da API.
- Garantir SSH autenticado e acesso root à VPS.
- Não copiar a chave privada de distribuição.

Na VPS, somente leitura:

~~~bash
hostname -s

systemctl is-active ifacematch-console ifacematch-server

systemctl show ifacematch-console \
    -p ExecStart \
    -p FragmentPath \
    -p DropInPaths

curl -fsS http://127.0.0.1:8180/health

df -h /opt/ifacematch /var/tmp
~~~

**Critério de passagem para o piloto:** hostname `srv855672`; ambos os serviços ativos; Console usando `/opt/ifacematch/releases/0.1.10/console/ifacematch-console`; API retornando `{"status":"ok"}`; sem overrides inesperados; backup disponível.

### 6.2 Baixar o atualizador publicado (na VPS)

~~~bash
curl --fail --location --silent --show-error \
    --output /root/ifacematch-update.sh \
    https://github.com/jefersonMarques/ifacematch/releases/download/v0.1.11/ifacematch-update.sh

bash -n /root/ifacematch-update.sh
~~~

O script é um artefato operacional versionado e executado como root. A equipe deve conferi-lo contra o arquivo aprovado no GitHub Release antes da execução. A conexão HTTPS e o `bash -n`, isoladamente, não autenticam sua origem de forma criptográfica.

### 6.3 Baixar e verificar o pacote, sem reiniciar serviços

~~~bash
bash /root/ifacematch-update.sh --check
~~~

Esse comando pode criar um cache local em `/var/cache/ifacematch/releases/0.1.11`, mas **não altera os serviços**. Ele confere o hash aprovado do arquivo baixado.

**Critério de passagem:** `[PASS] Published signed release 0.1.11: SHA-256 verified.`

### 6.4 Aplicar a atualização — operação que modifica produção

**Executar uma única vez, somente após aprovação e backup:**

~~~bash
bash /root/ifacematch-update.sh 0.1.11
~~~

O instalador:

1. Reconfere o SHA-256 do arquivo.
2. Extrai os artefatos em área temporária segura.
3. Verifica a assinatura Ed25519 e a integridade das releases `0.1.10` e `0.1.11` com a chave pública já confiada pela instalação.
4. Confirma que somente os artefatos do Console mudaram.
5. Instala os arquivos assinados em `/opt/ifacematch/releases/0.1.11` e os planos em `/var/lib/ifacematch/unit-plans/0.1.11`.
6. Faz backup da unidade `ifacematch-console.service`.
7. Atualiza apenas o `ExecStart` do Console, recarrega o systemd e reinicia apenas esse serviço.
8. Executa os testes HTTP de login/CSRF e confirma que o Server continua ativo.
9. Em falha após a troca da unidade, tenta restaurar a unidade anterior e reiniciar o Console antigo.

**Critério de passagem:** mensagem `[PASS] Signed Console 0.1.11 active; Server, database and license unchanged.` e registro de `[BACKUP]`.

A chave privada comercial **não** precisa estar na VPS.

## 7. Homologar e encerrar a implantação

Na VPS, confirmar:

~~~bash
systemctl is-active ifacematch-console ifacematch-server

systemctl show ifacematch-console \
    -p ExecStart --value

curl -fsS http://127.0.0.1:8180/health
~~~

Resultado esperado:

- Os dois serviços retornam `active`.
- O Console aponta para `/opt/ifacematch/releases/0.1.11/console/ifacematch-console`.
- A API retorna `{"status":"ok"}`.
- O teste embutido confirma estabilidade do CSRF, rejeição de CSRF inválido e `favicon` sem rotação do nonce.
- Um operador autorizado consegue entrar no Console com as credenciais preexistentes pelo navegador.

**Acesso pelo navegador é uma etapa obrigatória:** saúde HTTP não prova que o fluxo real de autenticação funciona. Para releases com mudança de biometria, a equipe deve acrescentar testes funcionais específicos usando dados autorizados.

Registrar resultado, horários, SHA-256, versão anterior e nova, link da release, hostname **em registro interno**, plano de rollback e responsável. Preservar o backup e a release anterior até encerrar o período de observação.

### Evidência da implantação de 12/11/2026

- Release pública: [v0.1.11](https://github.com/jefersonMarques/ifacematch/releases/tag/v0.1.11).
- Pacote: 87 artefatos, SHA-256 `4a44480bc5fe340ae1c26405284599560325807ac88c8c0daab8a645df10dc32`.
- Atualização do Console: concluída, assinatura validada, smoke CSRF aprovado.
- Server: ativo, `/health` retornou `{"status":"ok"}`.
- Login real: confirmado pelo operador.
- Banco, licença, Server e Core: não foram alterados pelo procedimento.
- Observação: o sucesso não equivale a um ensaio independente de falha/rollback.

## 8. Rollback e recuperação

**Rollback automático:** o script tenta restaurar o backup da unidade systemd se houver erro após a mudança. Isso não substitui um snapshot completo.

**Rollback manual (somente equipe de Operações):** registrar primeiro os sintomas e verificar se o backup representa a release anterior. Não apagar o pacote `0.1.11` nem o diretório da `0.1.10` durante a investigação.

O script registra a localização em `[BACKUP]`, com formato:

~~~text
/etc/ifacematch/console-upgrade-backup-<backup-id>
~~~

Em incidente, definir `BACKUP_DIR` com o caminho real obtido no log e conferir o conteúdo **antes** de qualquer restauração:

~~~bash
BACKUP_DIR="/etc/ifacematch/console-upgrade-backup-<backup-id>"

test -f "$BACKUP_DIR/ifacematch-console.service"

grep -Fqx \
    'ExecStart=/opt/ifacematch/releases/0.1.10/console/ifacematch-console' \
    "$BACKUP_DIR/ifacematch-console.service"
~~~

Apenas após confirmar o backup correto e autorizar o rollback:

~~~bash
cp -a -- \
    "$BACKUP_DIR/ifacematch-console.service" \
    /etc/systemd/system/ifacematch-console.service

systemctl daemon-reload
systemctl restart ifacematch-console

systemctl is-active ifacematch-console ifacematch-server
systemctl show ifacematch-console -p ExecStart --value
curl -fsS http://127.0.0.1:8180/health
~~~

Essa restauração **não** reverte o banco nem modifica licenças; só reativa a unidade anterior do Console. Se houver diferença de configuração, suspeita de corrupção ou ausência de backup confiável, interromper o procedimento e recuperar o snapshot da VPS com a equipe responsável. Não usar rollback manual em versões diferentes sem plano próprio.

## 9. Diagnóstico de erros comuns

| Mensagem ou sintoma | Causa provável | Ação segura |
|---|---|---|
| `Signed 0.1.10 archive not found` | Base assinada ausente na estação | Recuperar o arquivo autorizado e validar SHA; `make release-base` |
| `SIGNING_KEY=MISSING` | Chave privada ausente na estação de assinatura | Executar na estação autorizada; nunca copiar a chave para o cliente |
| `Release output already exists` | Pacote já gerado | Preservar arquivos e executar `make release-verify`; não sobrescrever |
| Teste Go ou staging falhou | Revisão incompatível ou defeito de código | Interromper, corrigir no componente e atualizar o pin após revisão |
| `make publish` bloqueado após publicação | Tag/release existente | Consultar a release; não republicar uma versão já distribuída |
| `gh auth` falhou | CLI sem login/permissão | Autenticar a conta autorizada no GitHub |
| `Cannot download the published release` | Falha de rede, URL ou release ausente | Verificar GitHub Release e conectividade; não instalar um arquivo de outra origem sem verificar |
| `SHA-256 mismatch` | Artefato alterado, incompleto ou não aprovado | Interromper; não alterar checksum para forçar a instalação |
| `Signed target release already exists` | Instalação já aplicada ou staging prévio | Inspecionar release ativa e planos; não executar novamente nem apagar diretórios automaticamente |
| Smoke de login falhou | Regressão do Console/configuração | Examinar logs, confirmar rollback e validar login real |
| `make deploy` bloqueado | Ainda não existe adaptador de deploy multi-versão | Usar somente o procedimento versionado aprovado |

Para diagnóstico na VPS, iniciar por:

~~~bash
systemctl status ifacematch-console --no-pager
systemctl status ifacematch-server --no-pager

journalctl -u ifacematch-console -n 80 --no-pager
~~~

**Não encaminhar logs brutos para repositórios públicos** sem revisar possíveis segredos ou dados pessoais.

## 10. Regras para versões futuras

O fluxo `0.1.11` foi **validado**, mas alguns pontos continuam deliberadamente específicos dessa versão.

**Não basta alterar `VERSION=0.1.12` no Makefile.** Para criar uma próxima release, a engenharia precisa:

1. Definir componentes alterados, migrações necessárias e compatibilidade com a versão instalada.
2. Revisar os commits e atualizar `versions.lock.json` com SHAs imutáveis.
3. Adaptar o builder/assinador, pacote-base e verificações para a nova versão; retirar hipóteses fixadas na `0.1.11`.
4. Atualizar testes, release notes, checksum aprovado pelo publicador e lógica do atualizador.
5. Validar instalação, atualização, falha e rollback **em ambiente equivalente ao cliente**.
6. Aprovar a publicação e somente depois autorizar o rollout por etapas.

Limitações atuais, registradas para evolução:

- `make release` comercial: implementado apenas para `0.1.11`.
- `scripts/publish.py`: hash e versão aprovados fixados para `0.1.11`.
- `ifacematch-update.sh`: script fixado no primeiro host piloto e na transição `0.1.10 → 0.1.11`.
- `make deploy`: continua bloqueado, sem deploy genérico.
- A instalação nova em cliente e a atualização do Server/Core não foram demonstradas por esse procedimento de Console.
- Releases publicadas não devem ser sobrescritas; proteção administrativa de tags/assets e configuração HTTPS devem ser acompanhadas pela operação.

A próxima meta arquitetural é **um único atualizador reutilizável**, com manifest de release assinado, download por versão, seleção de componentes, staging, testes e rollback; somente depois essa seção poderá ser generalizada.

## 11. Checklist e evidências

### Build e assinatura

- [ ] Mudanças aprovadas e commits fixados.
- [ ] `git pull --ff-only` e `make bootstrap` concluídos.
- [ ] `make test` aprovado.
- [ ] Pacote-base assinado e SHA-256 validados.
- [ ] Chaves disponíveis **somente** na estação autorizada.
- [ ] `make release` concluído (ou pacote já existente preservado).
- [ ] `make release-verify` aprovado.
- [ ] Notas e inventário da versão revisados.

### Publicação

- [ ] Autorização para distribuição pública dos artefatos.
- [ ] GitHub CLI autenticado com a conta correta.
- [ ] Versão/tag ainda não existe.
- [ ] `make publish` concluído.
- [ ] Assets publicados rebaixados e hashes confirmados.
- [ ] Link da tag e checksum registrados.

### Implantação e aceite

- [ ] Cliente e versão de origem confirmados.
- [ ] Backup/snapshot restaurável conferido.
- [ ] Equipe e janela de manutenção aprovadas.
- [ ] Atualizador do Release aprovado e validado.
- [ ] `--check` aprovado (sem reinício).
- [ ] Atualização executada uma única vez.
- [ ] Console e Server ativos; `/health` OK.
- [ ] Login real e testes funcionais aprovados.
- [ ] Caminho de backup registrado e preservado.
- [ ] Evidências internas, responsável e data preenchidos.

---

**Referências técnicas:** `Makefile`, `scripts/coordinator.py`, `scripts/publish.py`, `scripts/ifacematch-update.sh`, `versions.lock.json`, [notas da 0.1.11](../release-notes/0.1.11.md), [fluxo de release](release-process.md) e [GitHub Releases](https://github.com/jefersonMarques/ifacematch/releases).
