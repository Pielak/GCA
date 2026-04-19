; GCA — Script Inno Setup para Windows
; Gera GCA-Setup-1.0.exe com fluxo assistido em 10 telas + conclusão.
;
; Compilar no Windows com Inno Setup 6.2+:
;   iscc gca-installer.iss
;
; Pré-requisito: Docker Desktop instalado no cliente. O instalador
; verifica via tentativa de executar `docker version`.

#define MyAppName "GCA"
#define MyAppFullName "Gestão de Codificação Assistida"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Luiz Carlos Pielak"
#define MyAppURL "https://gca-produto.com"

[Setup]
AppId={{A3F7E2D4-6C8A-4B3F-9D2E-8F1A7B5C6D4E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\GCA
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=EULA.txt
OutputDir=.
OutputBaseFilename=GCA-Setup-{#MyAppVersion}
SetupIconFile=gca-icon.ico
WizardStyle=modern
WizardSizePercent=120
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\gca-icon.ico
UninstallDisplayName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}.0

[Languages]
Name: "brazilian"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
; Script install.sh portado para Windows via install.ps1
Source: "install.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "docker-compose.yml.template"; DestDir: "{app}"; Flags: ignoreversion
Source: "EULA.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "gca-icon.ico"; DestDir: "{app}"; Flags: ignoreversion
; Scripts auxiliares
Source: "..\..\scripts\upgrade.sh"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\..\scripts\backup.sh"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\..\scripts\restore.sh"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\..\scripts\health-check.sh"; DestDir: "{app}\scripts"; Flags: ignoreversion

[Icons]
Name: "{group}\Abrir GCA no navegador"; Filename: "http://localhost:{code:GetFrontPort}"
Name: "{group}\Parar GCA"; Filename: "powershell.exe"; \
      Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\stop.ps1"""; \
      WorkingDir: "{app}"
Name: "{group}\Reiniciar GCA"; Filename: "powershell.exe"; \
      Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\restart.ps1"""; \
      WorkingDir: "{app}"
Name: "{group}\Uninstall"; Filename: "{uninstallexe}"

[Code]
// ═══════════════════════════════════════════════════════════════════
// Variáveis globais — captadas ao longo do wizard
// ═══════════════════════════════════════════════════════════════════
var
    LicensePage: TInputQueryWizardPage;
    PrereqPage: TOutputMsgMemoWizardPage;
    NetworkPage: TInputQueryWizardPage;
    AdminPage: TInputQueryWizardPage;
    LLMPage: TInputOptionWizardPage;
    LLMKeyPage: TInputQueryWizardPage;
    SummaryPage: TOutputMsgMemoWizardPage;

    // Valores
    GCALicense: string;
    GCADomain: string;
    GCAPortFront: string;
    GCAPortAPI: string;
    AdminName: string;
    AdminEmail: string;
    AdminPassword: string;
    LLMProvider: string;
    LLMApiKey: string;

// ═══════════════════════════════════════════════════════════════════
// Etapa 3 — Chave de ativação
// ═══════════════════════════════════════════════════════════════════
procedure CreateLicensePage;
begin
    LicensePage := CreateInputQueryPage(
        wpLicense,
        'Chave de Ativação',
        'Insira sua chave de ativação do GCA',
        'Você recebeu a chave por e-mail no momento da contratação.' + #13#10 +
        'Formato esperado: GCA-PROD-XXXXX-XXXXX-XXXXX-XXXXX'
    );
    LicensePage.Add('Chave:', False);
    LicensePage.Values[0] := 'GCA-PROD-';
end;

// ═══════════════════════════════════════════════════════════════════
// Etapa 4 — Pré-requisitos
// ═══════════════════════════════════════════════════════════════════
procedure CreatePrereqPage;
begin
    PrereqPage := CreateOutputMsgMemoPage(
        LicensePage.ID,
        'Pré-requisitos',
        'Verificação automática do sistema',
        'Os itens abaixo serão verificados quando você clicar em Avançar. ' +
        'Itens em vermelho precisam ser corrigidos antes de prosseguir.',
        '[ ] Windows 10/11 64-bit (build 19045+)' + #13#10 +
        '[ ] Memória RAM mínima 8 GB' + #13#10 +
        '[ ] Espaço em disco mínimo 30 GB' + #13#10 +
        '[ ] Docker Desktop versão 4.30+ com WSL 2 ativado' + #13#10 +
        '[ ] Conectividade com registry.gca-produto.com' + #13#10 +
        '[ ] Permissão de Administrador (confirmada na instalação)'
    );
end;

function CheckDocker: Boolean;
var
    ResultCode: Integer;
begin
    Result := Exec('cmd.exe', '/c docker version >nul 2>&1', '',
                   SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

// ═══════════════════════════════════════════════════════════════════
// Etapa 6 — Porta e domínio
// ═══════════════════════════════════════════════════════════════════
procedure CreateNetworkPage;
begin
    NetworkPage := CreateInputQueryPage(
        PrereqPage.ID,
        'Rede',
        'Configure o endereço de acesso ao GCA',
        'Em produção, recomendamos usar proxy reverso (nginx, Caddy, Cloudflare Tunnel).'
    );
    NetworkPage.Add('Domínio (opcional):', False);
    NetworkPage.Add('Porta frontend:', False);
    NetworkPage.Add('Porta API:', False);
    NetworkPage.Values[0] := 'localhost';
    NetworkPage.Values[1] := '5173';
    NetworkPage.Values[2] := '8000';
end;

// ═══════════════════════════════════════════════════════════════════
// Etapa 7 — Admin inicial
// ═══════════════════════════════════════════════════════════════════
procedure CreateAdminPage;
begin
    AdminPage := CreateInputQueryPage(
        NetworkPage.ID,
        'Primeiro Administrador',
        'Crie o usuário que terá acesso à camada administrativa',
        'Senha mínima: 10 caracteres, 1 maiúscula, 1 número, 1 caractere especial.'
    );
    AdminPage.Add('Nome completo:', False);
    AdminPage.Add('E-mail:', False);
    AdminPage.Add('Senha:', True);
    AdminPage.Add('Confirmar senha:', True);
end;

// ═══════════════════════════════════════════════════════════════════
// Etapa 8 — Provedor IA
// ═══════════════════════════════════════════════════════════════════
procedure CreateLLMPage;
begin
    LLMPage := CreateInputOptionPage(
        AdminPage.ID,
        'Provedor de IA',
        'Escolha o provedor padrão da instância',
        'Pode ser alterado depois por instância (em /admin) e também por projeto.',
        True, False
    );
    LLMPage.Add('Anthropic (Claude) — Recomendado para alta criticidade');
    LLMPage.Add('OpenAI (GPT-4) — Premium');
    LLMPage.Add('Google (Gemini) — Custo médio');
    LLMPage.Add('DeepSeek — Baixo custo');
    LLMPage.Add('Ollama (local) — Gratuito, requer GPU');
    LLMPage.SelectedValueIndex := 0;

    LLMKeyPage := CreateInputQueryPage(
        LLMPage.ID,
        'Chave de API',
        'Informe a chave do provedor escolhido',
        'Deixe vazio apenas se escolheu Ollama (local). A chave é criptografada com Fernet.'
    );
    LLMKeyPage.Add('Chave de API:', True);
end;

// ═══════════════════════════════════════════════════════════════════
// Etapa 9 — Resumo
// ═══════════════════════════════════════════════════════════════════
procedure CreateSummaryPage;
begin
    SummaryPage := CreateOutputMsgMemoPage(
        LLMKeyPage.ID,
        'Resumo',
        'Pronto para instalar',
        'Revise as configurações. Clique em Instalar para aplicar.',
        ''
    );
end;

procedure UpdateSummary;
var
    Summary: string;
    ProviderName: string;
begin
    case LLMPage.SelectedValueIndex of
        0: ProviderName := 'Anthropic (Claude)';
        1: ProviderName := 'OpenAI (GPT-4)';
        2: ProviderName := 'Google (Gemini)';
        3: ProviderName := 'DeepSeek';
        4: ProviderName := 'Ollama (local)';
    end;
    Summary :=
        'Pasta de instalação:  ' + ExpandConstant('{app}') + #13#10 +
        'Domínio:              ' + NetworkPage.Values[0] + #13#10 +
        'Porta frontend:       ' + NetworkPage.Values[1] + #13#10 +
        'Porta API:            ' + NetworkPage.Values[2] + #13#10 +
        'Administrador:        ' + AdminPage.Values[0] + ' <' + AdminPage.Values[1] + '>' + #13#10 +
        'Provedor de IA:       ' + ProviderName + #13#10 +
        'Chave de ativação:    ' + LicensePage.Values[0] + #13#10 +
        'Imagens a baixar:' + #13#10 +
        '  - registry.gca-produto.com/gca-backend:1.0' + #13#10 +
        '  - registry.gca-produto.com/gca-frontend:1.0' + #13#10 +
        '  - postgres:15-alpine' + #13#10 +
        'Volumes Docker:' + #13#10 +
        '  - gca-postgres-data' + #13#10 +
        '  - gca-uploads-storage' + #13#10 +
        '  - gca-backups' + #13#10 +
        'Tempo estimado: ~6 minutos (depende da rede)';
    SummaryPage.RichEditViewer.Lines.Text := Summary;
end;

// ═══════════════════════════════════════════════════════════════════
// InitializeWizard — registra as páginas
// ═══════════════════════════════════════════════════════════════════
procedure InitializeWizard;
begin
    CreateLicensePage;
    CreatePrereqPage;
    CreateNetworkPage;
    CreateAdminPage;
    CreateLLMPage;
    CreateSummaryPage;
end;

function GetFrontPort(Param: string): string;
begin
    if NetworkPage <> nil then
        Result := NetworkPage.Values[1]
    else
        Result := '5173';
end;

// ═══════════════════════════════════════════════════════════════════
// NextButtonClick — validações por página
// ═══════════════════════════════════════════════════════════════════
function NextButtonClick(CurPageID: Integer): Boolean;
begin
    Result := True;

    // Validação da chave
    if CurPageID = LicensePage.ID then begin
        if Copy(LicensePage.Values[0], 1, 9) <> 'GCA-PROD-' then begin
            MsgBox('Chave inválida. Formato esperado: GCA-PROD-XXXXX-XXXXX-XXXXX-XXXXX',
                   mbError, MB_OK);
            Result := False;
        end else begin
            GCALicense := LicensePage.Values[0];
        end;
    end;

    // Verificação de pré-requisitos
    if CurPageID = PrereqPage.ID then begin
        if not CheckDocker then begin
            MsgBox('Docker Desktop não encontrado ou não está rodando. ' +
                   'Instale em https://www.docker.com/products/docker-desktop',
                   mbError, MB_OK);
            Result := False;
        end;
    end;

    // Validação de rede
    if CurPageID = NetworkPage.ID then begin
        GCADomain := NetworkPage.Values[0];
        GCAPortFront := NetworkPage.Values[1];
        GCAPortAPI := NetworkPage.Values[2];
    end;

    // Validação de admin
    if CurPageID = AdminPage.ID then begin
        if Length(AdminPage.Values[2]) < 10 then begin
            MsgBox('Senha deve ter no mínimo 10 caracteres.', mbError, MB_OK);
            Result := False;
        end else if AdminPage.Values[2] <> AdminPage.Values[3] then begin
            MsgBox('Senhas não coincidem.', mbError, MB_OK);
            Result := False;
        end else if Pos('@', AdminPage.Values[1]) = 0 then begin
            MsgBox('E-mail inválido.', mbError, MB_OK);
            Result := False;
        end else begin
            AdminName := AdminPage.Values[0];
            AdminEmail := AdminPage.Values[1];
            AdminPassword := AdminPage.Values[2];
        end;
    end;

    // LLM
    if CurPageID = LLMPage.ID then begin
        case LLMPage.SelectedValueIndex of
            0: LLMProvider := 'anthropic';
            1: LLMProvider := 'openai';
            2: LLMProvider := 'gemini';
            3: LLMProvider := 'deepseek';
            4: LLMProvider := 'ollama';
        end;
    end;

    if CurPageID = LLMKeyPage.ID then begin
        LLMApiKey := LLMKeyPage.Values[0];
        UpdateSummary;
    end;
end;

// ═══════════════════════════════════════════════════════════════════
// Etapa 10 — Instalação (chama install.ps1 com params)
// ═══════════════════════════════════════════════════════════════════
procedure CurStepChanged(CurStep: TSetupStep);
var
    ResultCode: Integer;
    PowerShellCmd: string;
begin
    if CurStep = ssPostInstall then begin
        PowerShellCmd := '-ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\scripts\install.ps1') +
                        '" -License "' + GCALicense +
                        '" -Domain "' + GCADomain +
                        '" -PortFrontend "' + GCAPortFront +
                        '" -PortAPI "' + GCAPortAPI +
                        '" -AdminName "' + AdminName +
                        '" -AdminEmail "' + AdminEmail +
                        '" -AdminPassword "' + AdminPassword +
                        '" -LLMProvider "' + LLMProvider +
                        '" -LLMApiKey "' + LLMApiKey + '"';
        if not Exec('powershell.exe', PowerShellCmd, '', SW_SHOW,
                    ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then begin
            MsgBox('Instalação falhou. Código: ' + IntToStr(ResultCode) +
                   #13#10 + 'Veja log em ' + ExpandConstant('{app}\install.log'),
                   mbError, MB_OK);
        end;
    end;
end;

[Run]
Filename: "http://{code:GetFrontHost}:{code:GetFrontPort}"; \
    Flags: postinstall shellexec skipifsilent; \
    Description: "Abrir GCA no navegador"

[Code]
function GetFrontHost(Param: string): string;
begin
    if NetworkPage <> nil then
        Result := NetworkPage.Values[0]
    else
        Result := 'localhost';
end;
