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

O comando `make release` **não publica nem instala nada**. As operações remotas estão bloqueadas até existir um adaptador de publicação e implantação homologado.

Consulte [o fluxo de releases](docs/release-process.md) e execute `make help` para os comandos disponíveis.
