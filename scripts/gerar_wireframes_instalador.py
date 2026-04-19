#!/usr/bin/env python3
"""
Gera wireframes PNG das 10 telas do instalador GCA (Windows + Ubuntu GUI)
para uso no Tutorial de Instalação. Usa Pillow para desenhar.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import os

OUT = Path("/home/luiz/GCA/docs/wireframes")
OUT.mkdir(parents=True, exist_ok=True)

# Cores GCA
VIOLET = (109, 40, 217)
SLATE_DARK = (30, 41, 59)
SLATE_LIGHT = (148, 163, 184)
WHITE = (255, 255, 255)
GREEN = (5, 150, 105)
AMBER = (217, 119, 6)
LIGHT_GREY = (241, 245, 249)
WINDOW_BG = (250, 250, 252)

W, H = 800, 580

# Fontes do sistema
FONT_DIRS = ["/usr/share/fonts", "/usr/local/share/fonts"]
def find_font(name_keywords, size):
    for dir_ in FONT_DIRS:
        for root, _, files in os.walk(dir_):
            for f in files:
                if any(kw in f.lower() for kw in name_keywords) and f.endswith((".ttf", ".otf")):
                    try:
                        return ImageFont.truetype(os.path.join(root, f), size)
                    except Exception:
                        continue
    return ImageFont.load_default()

FONT_TITLE_BOLD = find_font(["dejavusans-bold", "liberationsans-bold", "freesans-bold"], 22)
FONT_TITLE = find_font(["dejavusans-bold", "liberationsans-bold", "freesans-bold"], 18)
FONT_REGULAR = find_font(["dejavusans.ttf", "liberationsans-regular", "freesans"], 14)
FONT_SMALL = find_font(["dejavusans.ttf", "liberationsans-regular", "freesans"], 11)
FONT_MONO = find_font(["dejavusansmono", "liberationmono"], 12)


def base_window(title: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), WINDOW_BG)
    d = ImageDraw.Draw(img)
    # Title bar
    d.rectangle([0, 0, W, 36], fill=SLATE_DARK)
    d.text((14, 8), "GCA Instalador — " + title, fill=WHITE, font=FONT_TITLE)
    # Window dots Windows
    d.ellipse([W-72, 12, W-58, 26], fill=(220,220,220))
    d.ellipse([W-50, 12, W-36, 26], fill=(220,220,220))
    d.ellipse([W-28, 12, W-14, 26], fill=(220,220,220))
    return img, d


def footer(d: ImageDraw.ImageDraw, *, with_back: bool = True, next_label: str = "Avançar →"):
    # Bottom bar
    d.rectangle([0, H-60, W, H], fill=LIGHT_GREY)
    d.line([(0, H-60), (W, H-60)], fill=SLATE_LIGHT, width=1)
    if with_back:
        d.rectangle([18, H-44, 110, H-16], outline=SLATE_DARK, width=1, fill=WHITE)
        d.text((38, H-37), "← Voltar", fill=SLATE_DARK, font=FONT_REGULAR)
    d.rectangle([W-180, H-44, W-90, H-16], outline=VIOLET, width=2, fill=VIOLET)
    d.text((W-168, H-37), next_label, fill=WHITE, font=FONT_REGULAR)
    d.rectangle([W-78, H-44, W-18, H-16], outline=SLATE_DARK, width=1, fill=WHITE)
    d.text((W-65, H-37), "Cancelar", fill=SLATE_DARK, font=FONT_REGULAR)


def render_step1_welcome():
    img, d = base_window("Bem-vindo")
    d.text((40, 80), "Bem-vindo ao Assistente de Instalação do GCA", fill=SLATE_DARK, font=FONT_TITLE_BOLD)
    d.text((40, 130), "Você está prestes a instalar a Gestão de Codificação", fill=SLATE_DARK, font=FONT_REGULAR)
    d.text((40, 152), "Assistida em sua máquina.", fill=SLATE_DARK, font=FONT_REGULAR)
    d.text((40, 200), "Este assistente vai conduzi-lo por 10 etapas:", fill=SLATE_DARK, font=FONT_REGULAR)
    steps = ["1. Aceite do contrato (EULA)",
             "2. Chave de ativação",
             "3. Verificação de pré-requisitos (Docker)",
             "4. Pasta de instalação",
             "5. Porta e domínio",
             "6. Administrador inicial",
             "7. Provedor de IA",
             "8. Resumo da instalação",
             "9. Instalação propriamente dita",
             "10. Conclusão"]
    for i, s in enumerate(steps):
        d.text((60, 235 + i*22), s, fill=SLATE_DARK, font=FONT_REGULAR)
    d.text((40, 470), "Clique em \"Avançar\" para começar.", fill=VIOLET, font=FONT_REGULAR)
    footer(d, with_back=False)
    img.save(OUT / "01_boas_vindas.png")


def render_step2_eula():
    img, d = base_window("Aceite do contrato (EULA)")
    d.text((40, 60), "Contrato de Licença de Uso", fill=SLATE_DARK, font=FONT_TITLE_BOLD)
    d.text((40, 95), "Leia atentamente antes de continuar.", fill=SLATE_LIGHT, font=FONT_SMALL)
    # Caixa do EULA
    d.rectangle([40, 120, W-40, 420], outline=SLATE_LIGHT, width=1, fill=WHITE)
    eula = [
        "1. Este software é fornecido sob licença comercial pelo titular",
        "   da chave de ativação. Engenharia reversa é proibida.",
        "",
        "2. O cliente é responsável por: backups regulares, segurança",
        "   da chave mestra (GCA_MASTER_KEY), credenciais de provedores",
        "   de IA configurados na instância.",
        "",
        "3. O GCA não compartilha dados entre instâncias de clientes.",
        "   Cada instância é soberana sobre seus próprios dados.",
        "",
        "4. Atualizações do GCA são entregues via release versionada",
        "   e respeitam o contrato de preservação de dados (MVP 7).",
        "",
        "5. Suporte é prestado conforme contrato comercial separado."
    ]
    for i, line in enumerate(eula):
        d.text((52, 132 + i*16), line, fill=SLATE_DARK, font=FONT_SMALL)
    # Checkbox
    d.rectangle([40, 440, 56, 456], outline=SLATE_DARK, width=1, fill=WHITE)
    d.text((46, 442), "✓", fill=VIOLET, font=FONT_REGULAR)
    d.text((68, 440), "Li e aceito os termos do contrato de licença.", fill=SLATE_DARK, font=FONT_REGULAR)
    footer(d)
    img.save(OUT / "02_eula.png")


def render_step3_license():
    img, d = base_window("Chave de Ativação")
    d.text((40, 60), "Insira sua chave de ativação", fill=SLATE_DARK, font=FONT_TITLE_BOLD)
    d.text((40, 95), "Você recebeu a chave por e-mail no momento da contratação.", fill=SLATE_LIGHT, font=FONT_SMALL)
    d.text((40, 150), "Chave:", fill=SLATE_DARK, font=FONT_REGULAR)
    d.rectangle([40, 175, W-40, 210], outline=SLATE_LIGHT, width=2, fill=WHITE)
    d.text((52, 184), "GCA-PROD-XXXXX-XXXXX-XXXXX-XXXXX", fill=SLATE_LIGHT, font=FONT_MONO)
    d.text((40, 230), "A chave determina:", fill=SLATE_DARK, font=FONT_REGULAR)
    bullets = [
        "• A validade da licença (data de expiração).",
        "• O número máximo de projetos simultâneos.",
        "• O número máximo de usuários ativos.",
        "• O nível de suporte contratado."
    ]
    for i, b in enumerate(bullets):
        d.text((60, 260 + i*22), b, fill=SLATE_DARK, font=FONT_REGULAR)
    # Status
    d.rectangle([40, 380, W-40, 420], fill=(245, 250, 245), outline=GREEN, width=1)
    d.text((52, 392), "✓ Chave válida — válida até 2027-04-19, até 50 projetos.", fill=GREEN, font=FONT_REGULAR)
    footer(d, next_label="Validar e avançar →")
    img.save(OUT / "03_chave_ativacao.png")


def render_step4_prereq():
    img, d = base_window("Pré-requisitos")
    d.text((40, 60), "Verificação de pré-requisitos do sistema", fill=SLATE_DARK, font=FONT_TITLE_BOLD)
    d.text((40, 95), "O GCA depende dos itens abaixo. Tudo verificado automaticamente.", fill=SLATE_LIGHT, font=FONT_SMALL)
    items = [
        ("Sistema operacional", "Windows 10/11 64-bit (build 19045+)", True),
        ("Memória RAM", "Mínimo 8 GB (16 GB recomendado)", True),
        ("Espaço em disco", "Mínimo 30 GB livres", True),
        ("Docker Desktop", "Versão 4.30 ou superior, com WSL2 ativado", True),
        ("Acesso à Internet", "Para baixar imagens do GCA Registry", True),
        ("Permissão de Administrador", "Necessária para registrar serviço", True),
    ]
    for i, (label, desc, ok) in enumerate(items):
        y = 140 + i*48
        # Checkmark / X
        if ok:
            d.ellipse([46, y+4, 70, y+28], fill=GREEN)
            d.text((52, y+6), "✓", fill=WHITE, font=FONT_TITLE)
        else:
            d.ellipse([46, y+4, 70, y+28], fill=(220, 50, 50))
            d.text((54, y+6), "X", fill=WHITE, font=FONT_TITLE)
        d.text((85, y), label, fill=SLATE_DARK, font=FONT_REGULAR)
        d.text((85, y+20), desc, fill=SLATE_LIGHT, font=FONT_SMALL)
    footer(d)
    img.save(OUT / "04_prerequisitos.png")


def render_step5_path():
    img, d = base_window("Pasta de instalação")
    d.text((40, 60), "Onde instalar o GCA", fill=SLATE_DARK, font=FONT_TITLE_BOLD)
    d.text((40, 95), "Escolha a pasta de destino. Containers e dados ficam aqui.", fill=SLATE_LIGHT, font=FONT_SMALL)
    d.text((40, 160), "Pasta:", fill=SLATE_DARK, font=FONT_REGULAR)
    d.rectangle([40, 185, W-180, 220], outline=SLATE_LIGHT, width=2, fill=WHITE)
    d.text((52, 194), "C:\\Program Files\\GCA", fill=SLATE_DARK, font=FONT_MONO)
    d.rectangle([W-170, 185, W-40, 220], outline=SLATE_DARK, width=1, fill=LIGHT_GREY)
    d.text((W-145, 194), "Procurar...", fill=SLATE_DARK, font=FONT_REGULAR)
    d.text((40, 270), "Espaço necessário: ~25 GB", fill=SLATE_DARK, font=FONT_REGULAR)
    d.text((40, 295), "Espaço disponível em C:: 312 GB", fill=GREEN, font=FONT_REGULAR)
    d.text((40, 350), "Volumes Docker (separados da pasta acima):", fill=SLATE_DARK, font=FONT_REGULAR)
    vols = [
        "• gca-postgres-data — banco de dados PostgreSQL",
        "• gca-uploads-storage — uploads e anexos de tickets",
        "• gca-backups — backups por projeto (DT-063)"
    ]
    for i, v in enumerate(vols):
        d.text((60, 380 + i*22), v, fill=SLATE_LIGHT, font=FONT_REGULAR)
    footer(d)
    img.save(OUT / "05_pasta_instalacao.png")


def render_step6_network():
    img, d = base_window("Porta e domínio")
    d.text((40, 60), "Configuração de rede", fill=SLATE_DARK, font=FONT_TITLE_BOLD)
    d.text((40, 95), "Em qual endereço a instância do GCA será acessada?", fill=SLATE_LIGHT, font=FONT_SMALL)

    d.text((40, 150), "Domínio (opcional, para HTTPS):", fill=SLATE_DARK, font=FONT_REGULAR)
    d.rectangle([40, 175, W-40, 210], outline=SLATE_LIGHT, width=2, fill=WHITE)
    d.text((52, 184), "gca.empresa.com.br", fill=SLATE_DARK, font=FONT_MONO)

    d.text((40, 240), "Porta HTTP do frontend:", fill=SLATE_DARK, font=FONT_REGULAR)
    d.rectangle([40, 265, 200, 295], outline=SLATE_LIGHT, width=2, fill=WHITE)
    d.text((52, 272), "5173", fill=SLATE_DARK, font=FONT_MONO)

    d.text((220, 240), "Porta API:", fill=SLATE_DARK, font=FONT_REGULAR)
    d.rectangle([220, 265, 380, 295], outline=SLATE_LIGHT, width=2, fill=WHITE)
    d.text((232, 272), "8000", fill=SLATE_DARK, font=FONT_MONO)

    d.text((40, 330), "Porta PostgreSQL (interna):", fill=SLATE_DARK, font=FONT_REGULAR)
    d.rectangle([40, 355, 200, 385], outline=SLATE_LIGHT, width=2, fill=WHITE)
    d.text((52, 362), "5432", fill=SLATE_DARK, font=FONT_MONO)

    d.text((40, 420), "Recomendamos um proxy reverso (nginx, Caddy, Cloudflare Tunnel)", fill=AMBER, font=FONT_SMALL)
    d.text((40, 435), "para expor o GCA com HTTPS válido em produção.", fill=AMBER, font=FONT_SMALL)
    footer(d)
    img.save(OUT / "06_rede_porta.png")


def render_step7_admin():
    img, d = base_window("Administrador inicial")
    d.text((40, 60), "Crie o primeiro Administrador", fill=SLATE_DARK, font=FONT_TITLE_BOLD)
    d.text((40, 95), "Esse usuário poderá criar outros admins depois.", fill=SLATE_LIGHT, font=FONT_SMALL)

    d.text((40, 150), "Nome completo:", fill=SLATE_DARK, font=FONT_REGULAR)
    d.rectangle([40, 175, W-40, 210], outline=SLATE_LIGHT, width=2, fill=WHITE)
    d.text((52, 184), "Luiz Carlos Pielak", fill=SLATE_DARK, font=FONT_REGULAR)

    d.text((40, 230), "E-mail:", fill=SLATE_DARK, font=FONT_REGULAR)
    d.rectangle([40, 255, W-40, 290], outline=SLATE_LIGHT, width=2, fill=WHITE)
    d.text((52, 264), "admin@empresa.com.br", fill=SLATE_DARK, font=FONT_REGULAR)

    d.text((40, 310), "Senha (mínimo 10 caracteres, 1 maiúscula, 1 número, 1 especial):",
           fill=SLATE_DARK, font=FONT_REGULAR)
    d.rectangle([40, 335, W-40, 370], outline=SLATE_LIGHT, width=2, fill=WHITE)
    d.text((52, 344), "•••••••••••••", fill=SLATE_DARK, font=FONT_REGULAR)

    d.text((40, 390), "Confirmar senha:", fill=SLATE_DARK, font=FONT_REGULAR)
    d.rectangle([40, 415, W-40, 450], outline=SLATE_LIGHT, width=2, fill=WHITE)
    d.text((52, 424), "•••••••••••••", fill=SLATE_DARK, font=FONT_REGULAR)

    d.rectangle([40, 460, W-40, 495], fill=(255, 250, 240), outline=AMBER, width=1)
    d.text((52, 470), "ⓘ Esta senha é gravada apenas como bcrypt hash.", fill=SLATE_DARK, font=FONT_SMALL)
    footer(d)
    img.save(OUT / "07_admin_inicial.png")


def render_step8_ai():
    img, d = base_window("Provedor de IA")
    d.text((40, 60), "Provedor de IA padrão da instância", fill=SLATE_DARK, font=FONT_TITLE_BOLD)
    d.text((40, 95), "Pode ser alterado depois em /admin (Settings) e por projeto.", fill=SLATE_LIGHT, font=FONT_SMALL)

    d.text((40, 145), "Provedor:", fill=SLATE_DARK, font=FONT_REGULAR)
    d.rectangle([40, 170, W-40, 205], outline=SLATE_LIGHT, width=2, fill=WHITE)
    d.text((52, 178), "Anthropic (Claude)        ▼", fill=SLATE_DARK, font=FONT_REGULAR)

    providers = [
        ("Anthropic (Claude)", "Recomendado — alta criticidade. ~US$ 0,008/operação OCG."),
        ("OpenAI (GPT-4)", "Premium. ~US$ 0,012/operação."),
        ("Google (Gemini)", "Custo médio. Bom para textos longos."),
        ("DeepSeek", "Baixo custo. Adequado para baixa criticidade."),
        ("Ollama (local)", "Gratuito. Requer hardware com GPU para qualidade decente."),
    ]
    for i, (name, desc) in enumerate(providers):
        y = 230 + i*38
        d.text((52, y), "○ " + name, fill=SLATE_DARK, font=FONT_REGULAR)
        d.text((68, y+18), desc, fill=SLATE_LIGHT, font=FONT_SMALL)

    d.text((40, 460), "Chave de API:", fill=SLATE_DARK, font=FONT_REGULAR)
    d.rectangle([40, 485, W-40, 520], outline=SLATE_LIGHT, width=2, fill=WHITE)
    d.text((52, 494), "sk-ant-•••••••••••••••••••••••••", fill=SLATE_DARK, font=FONT_MONO)
    footer(d)
    img.save(OUT / "08_provedor_ia.png")


def render_step9_summary():
    img, d = base_window("Resumo")
    d.text((40, 60), "Pronto para instalar", fill=SLATE_DARK, font=FONT_TITLE_BOLD)
    d.text((40, 95), "Confira o que será aplicado e clique em \"Instalar\".", fill=SLATE_LIGHT, font=FONT_SMALL)

    summary = [
        ("Pasta de instalação", "C:\\Program Files\\GCA"),
        ("Domínio configurado", "gca.empresa.com.br"),
        ("Porta frontend", "5173"),
        ("Porta API", "8000"),
        ("Administrador inicial", "Luiz Carlos Pielak (admin@empresa.com.br)"),
        ("Provedor de IA", "Anthropic (Claude)"),
        ("Imagens Docker a baixar", "gca-backend:1.0, gca-frontend:1.0, postgres:15"),
        ("Volumes Docker", "gca-postgres-data, gca-uploads-storage, gca-backups"),
        ("Tempo estimado", "~6 minutos (depende da rede)"),
    ]
    for i, (k, v) in enumerate(summary):
        y = 140 + i*36
        d.text((52, y), k + ":", fill=SLATE_LIGHT, font=FONT_REGULAR)
        d.text((300, y), v, fill=SLATE_DARK, font=FONT_REGULAR)
    footer(d, next_label="Instalar")
    img.save(OUT / "09_resumo.png")


def render_step10_install():
    img, d = base_window("Instalando")
    d.text((40, 60), "Instalando o GCA...", fill=SLATE_DARK, font=FONT_TITLE_BOLD)
    d.text((40, 95), "Não feche esta janela. Você pode minimizar.", fill=SLATE_LIGHT, font=FONT_SMALL)

    # Progress bar
    d.rectangle([40, 150, W-40, 180], outline=SLATE_LIGHT, width=1, fill=WHITE)
    d.rectangle([42, 152, 480, 178], fill=VIOLET)
    d.text((W//2 - 20, 158), "62%", fill=WHITE, font=FONT_REGULAR)

    d.text((40, 200), "Etapa atual:", fill=SLATE_DARK, font=FONT_REGULAR)
    d.text((40, 224), "Baixando imagem gca-backend:1.0 (45 / 72 MB)", fill=VIOLET, font=FONT_REGULAR)

    log_lines = [
        "[ ✓ ] Validando chave de ativação",
        "[ ✓ ] Verificando Docker Desktop",
        "[ ✓ ] Criando volumes nomeados (gca-postgres-data, gca-uploads-storage, gca-backups)",
        "[ ✓ ] Configurando .env com porta 5173, API 8000, domínio gca.empresa.com.br",
        "[ ✓ ] Salvando Admin inicial criptografado (bcrypt + sal único)",
        "[ ✓ ] Salvando provedor IA Anthropic (api_key cripto Fernet)",
        "[ → ] Baixando imagem gca-backend:1.0 (45 / 72 MB)",
        "[   ] Baixando imagem gca-frontend:1.0",
        "[   ] Baixando imagem postgres:15-alpine",
        "[   ] Subindo containers via docker compose up -d",
        "[   ] Aguardando health check do backend",
        "[   ] Aplicando migrations do banco",
        "[   ] Bootstrap do primeiro Admin no banco",
    ]
    for i, line in enumerate(log_lines):
        d.text((52, 270 + i*18), line, fill=SLATE_DARK, font=FONT_MONO)
    footer(d, with_back=False, next_label="Aguarde...")
    img.save(OUT / "10_instalando.png")


def render_step11_done():
    img, d = base_window("Instalação concluída")
    d.text((40, 80), "✓  Instalação concluída com sucesso!", fill=GREEN, font=FONT_TITLE_BOLD)
    d.text((40, 130), "O GCA está rodando e pronto para uso.", fill=SLATE_DARK, font=FONT_REGULAR)

    d.rectangle([40, 180, W-40, 290], fill=(245, 250, 245), outline=GREEN, width=1)
    d.text((52, 198), "Próximos passos:", fill=SLATE_DARK, font=FONT_REGULAR)
    d.text((52, 226), "1. Acesse https://gca.empresa.com.br no navegador.", fill=SLATE_DARK, font=FONT_REGULAR)
    d.text((52, 248), "2. Faça login com admin@empresa.com.br + senha definida.", fill=SLATE_DARK, font=FONT_REGULAR)
    d.text((52, 270), "3. Aprove a primeira solicitação de projeto em /admin/projects.", fill=SLATE_DARK, font=FONT_REGULAR)

    d.rectangle([40, 320, W-40, 410], fill=(255, 250, 240), outline=AMBER, width=1)
    d.text((52, 338), "Operação:", fill=SLATE_DARK, font=FONT_REGULAR)
    d.text((52, 362), "• Backup diário automático às 12:00 (horário do servidor).", fill=SLATE_DARK, font=FONT_SMALL)
    d.text((52, 380), "• Upgrade futuro: scripts/upgrade.sh (ver Tutorial cap. 4).", fill=SLATE_DARK, font=FONT_SMALL)
    d.text((52, 396), "• Monitoramento: /api/v1/metrics/health para LB, /metrics/prometheus para scrape.", fill=SLATE_DARK, font=FONT_SMALL)

    # Checkbox
    d.rectangle([40, 430, 56, 446], outline=SLATE_DARK, width=1, fill=WHITE)
    d.text((46, 432), "✓", fill=VIOLET, font=FONT_REGULAR)
    d.text((68, 430), "Abrir o GCA agora no navegador", fill=SLATE_DARK, font=FONT_REGULAR)
    footer(d, with_back=False, next_label="Concluir")
    img.save(OUT / "11_conclusao.png")


def main():
    render_step1_welcome()
    render_step2_eula()
    render_step3_license()
    render_step4_prereq()
    render_step5_path()
    render_step6_network()
    render_step7_admin()
    render_step8_ai()
    render_step9_summary()
    render_step10_install()
    render_step11_done()
    print(f"✓ 11 wireframes gerados em {OUT}")


if __name__ == "__main__":
    main()
