# GCA — Instalador e empacotamento de produção

Este diretório contém todos os artefatos para empacotar o GCA como
aplicação instalável (Windows + Ubuntu), com as 7 camadas de proteção
anti-engenharia-reversa documentadas em `docs/ANTI_REVERSE_ENGINEERING.md`.

## Estrutura

```
installer/
├── Dockerfile.backend.production    # Multi-stage com Cython compile + PyArmor BCC
├── Dockerfile.frontend.production   # Multi-stage com javascript-obfuscator + nginx
├── build_production_images.sh       # Build + tag + assina manifest + push
├── integrity_check.py               # Camada 6: SHA-256 check no startup
├── install.sh                       # Instalador Ubuntu (10 etapas interativas)
├── EULA.txt                         # Contrato de licença
├── windows/
│   ├── gca-installer.iss            # Script Inno Setup (10 telas)
│   └── install.ps1                  # Executor PowerShell chamado pelo Inno Setup
└── debian/
    ├── control                      # Metadados .deb
    ├── postinst                     # Pós-instalação apt
    ├── prerm                        # Pré-remoção (preserva volumes)
    ├── gca.service                  # Serviço systemd
    └── build_deb.sh                 # Monta o .deb
```

## Fluxo completo de distribuição

### 1. Build das imagens protegidas

```bash
# No servidor de build (Linux com Docker + poetry):
cd installer
./build_production_images.sh --version 1.0.0 --push
```

Isso:
1. Compila backend (.py → .so via Cython).
2. Obfusca frontend (javascript-obfuscator).
3. Gera manifest SHA-256 dos .so.
4. Assina manifest com chave privada (se disponível).
5. Re-empacota backend com manifest + pubkey.
6. Push para `registry.gca-produto.com` (com `--push`).

### 2. Empacotar instalador Windows

```bash
# No Windows com Inno Setup instalado:
cd installer\windows
iscc gca-installer.iss
# Saída: GCA-Setup-1.0.0.exe
```

Distribuir o `.exe` para clientes Windows.

### 3. Empacotar .deb Ubuntu

```bash
# No Linux:
cd installer/debian
./build_deb.sh
# Saída: gca_1.0.0_amd64.deb
```

Distribuir o `.deb` para clientes Ubuntu.

## Instalação no cliente final

### Windows

1. Cliente recebe `GCA-Setup-1.0.0.exe` + chave de ativação.
2. Dá duplo clique. O assistente guia 10 telas.
3. Ao final, `install.ps1` é executado automaticamente com os parâmetros coletados.

### Ubuntu (via .deb)

```bash
sudo dpkg -i gca_1.0.0_amd64.deb
sudo apt-get install -f
sudo /opt/gca/scripts/install.sh
```

### Ubuntu (direto)

```bash
wget https://registry.gca-produto.com/downloads/install.sh
chmod +x install.sh
sudo ./install.sh
```

## Segurança — resumo das 7 camadas

1. **Cython compile** — Python vira binário `.so` ilegível.
2. **PyArmor BCC** — wrapper adicional em módulos sensíveis.
3. **Imagens multi-stage** — sem toolchain na imagem final.
4. **Registry privado autenticado** — tokens rotacionáveis.
5. **Obfuscator JavaScript** — frontend ilegível.
6. **Integrity check no startup** — SHA-256 contra manifest assinado.
7. **Licença JWT** — expiração + claims; sem JWT válido não sobe.

Detalhes completos e limitações honestas em `docs/ANTI_REVERSE_ENGINEERING.md`.

## Operação pós-instalação

Ver capítulos 7 e 8 do `docs/GCA_Tutorial_Instalacao_v1.docx` (Operação e Troubleshooting).

---

Autor: Luiz Carlos Pielak
Versão: 1.0.0 — 2026-04-19
