# iFaceMatch — Release Coordinator

Coordenador de compilação, testes e distribuição do iFaceMatch Customer Hosted.

Este repositório **não contém o código dos componentes**, chaves privadas, licenças de clientes ou artefatos biométricos. Usa commits imutáveis de quatro repositórios e executa builds em diretórios temporários.

> **Aviso:** este repositório está público no GitHub. Mantenha segredos, chaves de assinatura, pacotes comerciais e dados de clientes fora do Git.

## Início rápido

```bash
git clone git@github.com:jefersonMarques/ifacematch.git /opt/iFaceMatch/ifacematch
cd /opt/iFaceMatch/ifacematch
make doctor
make bootstrap
make test
make build
```

Para gerar a correção comercial **0.1.11**, é necessário possuir o arquivo **0.1.10 assinado**, com SHA-256 previamente conhecido, e a chave Ed25519 já utilizada pela distribuição:

```bash
make release-base
make release VERSION=0.1.11
make release-verify VERSION=0.1.11
```

O coordenador localiza automaticamente a release-base assinada `0.1.10` no inventário local (incluindo `~/.config/ifacematch/release-0.1.10.path`) e verifica seu SHA-256 antes de iniciar a compilação. Se o arquivo estiver em um local não convencional, use `BASE_ARCHIVE=/caminho/absoluto/arquivo.tar.gz` como exceção. Nunca é necessário informar o caminho em cada execução.

O comando `make release` assina o pacote local, sem modificar serviços.

## Publicar a release no GitHub

```bash
cd /opt/iFaceMatch/ifacematch
git pull --ff-only
gh auth status || gh auth login
make publish VERSION=0.1.11
```

O publicador verifica o pacote, a tag, o repositório público e os commits antes de criar a release v0.1.11. Não sobrescreve tags nem assets já publicados; baixa os arquivos publicados para validar seus hashes.

## Atualizar o piloto via GitHub (na VPS como root)

```bash
curl --fail --location --silent --show-error \
  --output /root/ifacematch-update.sh \
  https://github.com/jefersonMarques/ifacematch/releases/download/v0.1.11/ifacematch-update.sh
bash -n /root/ifacematch-update.sh
bash /root/ifacematch-update.sh --check
```

Após confirmar backup e janela de manutenção:

```bash
bash /root/ifacematch-update.sh 0.1.11
```

O updater é exclusivo do host piloto srv855672. Confere SHA-256 e assinatura Ed25519, atualiza somente o Console e tenta restaurar a unidade anterior se o smoke test falhar. O comando --check pode criar cache de download, mas não reinicia serviços. O make deploy genérico permanece bloqueado até homologação de um atualizador multi-versão.


Consulte [o fluxo de releases](docs/release-process.md) e execute `make help` para os comandos disponíveis.
