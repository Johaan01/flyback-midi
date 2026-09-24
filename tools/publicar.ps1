<#
Publica o site no GitHub Pages.

    tools\publicar.cmd                  (duplo clique também serve)
    tools\publicar.cmd -Nome outro-nome

Na primeira vez abre o navegador para entrar na sua conta do GitHub, cria o
repositório público, envia os arquivos, liga o GitHub Pages pelo GitHub Actions
e mostra o endereço do site. Rodar de novo grava as mudanças locais num commit
e envia.
#>
param([string]$Nome = 'flyback-midi')

Set-Location (Split-Path -Parent $PSScriptRoot)
foreach ($d in @("$env:ProgramFiles\Git\cmd", "$env:ProgramFiles\GitHub CLI", "$env:LOCALAPPDATA\Programs\Git\cmd")) {
    if ((Test-Path $d) -and (($env:Path -split ';') -notcontains $d)) { $env:Path = "$d;$env:Path" }
}

function Parar([string]$msg) { Write-Host ''; Write-Host $msg -ForegroundColor Red; exit 1 }
function Passo([string]$msg) { Write-Host ''; Write-Host "== $msg" -ForegroundColor Cyan }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Parar 'Git não encontrado. Instale com: winget install Git.Git' }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { Parar 'GitHub CLI não encontrado. Instale com: winget install GitHub.cli' }
if (-not (Test-Path .git)) { git init -b main | Out-Null }

Passo 'Conta do GitHub'
gh auth status --hostname github.com 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Vai abrir o navegador. Copie o código que aparecer aqui e cole na página do GitHub.'
    gh auth login --hostname github.com --git-protocol https --web --scopes workflow
    if ($LASTEXITCODE -ne 0) { Parar 'Login no GitHub não concluído.' }
} else {
    # enviar arquivos de .github/workflows exige a permissão "workflow"
    $escopos = gh api -i user 2>$null | Select-String -Pattern '^X-Oauth-Scopes:' | Select-Object -First 1
    if ($escopos -and ($escopos.Line -notmatch '\bworkflow\b')) {
        Write-Host 'Falta a permissão "workflow" para enviar o arquivo de publicação. Vai abrir o navegador.'
        gh auth refresh --hostname github.com --scopes workflow
        if ($LASTEXITCODE -ne 0) { Parar 'Permissão não concedida.' }
    }
}
gh auth setup-git --hostname github.com | Out-Null
$login = (gh api user --jq .login).Trim()
$id = (gh api user --jq .id).Trim()
if (-not $login) { Parar 'Não consegui ler o usuário do GitHub.' }
Write-Host "Conta: $login"

# commits com o e-mail privado do GitHub, para o seu e-mail não ficar público no histórico
$email = "$id+$login@users.noreply.github.com"
git config user.email $email
if (-not (git config user.name)) { git config user.name $login }

Passo 'Gravando as mudanças locais'
git add -A
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    $primeiro = -not (git rev-parse --verify --quiet HEAD)
    git commit --quiet -m $(if ($primeiro) { 'player MIDI para dois flybacks' } else { 'atualiza o site' })
    if ($LASTEXITCODE -ne 0) { Parar 'Não consegui criar o commit.' }
}
git log --oneline -1

$remotos = @(git remote)
if ($remotos -notcontains 'origin') {
    # nada foi enviado ainda: a autoria dos commits locais passa para o e-mail privado
    git -c core.editor=true rebase --quiet --root --exec 'git commit --amend --no-edit --reset-author --quiet'
    if ($LASTEXITCODE -ne 0) { git rebase --abort 2>$null; Parar 'Não consegui ajustar a autoria dos commits.' }

    Passo "Repositório $login/$Nome"
    gh api "repos/$login/$Nome" --silent 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Já existe no GitHub; vou enviar para ele.'
    } else {
        gh repo create $Nome --public --description 'Fonte de áudio para alto-falantes de plasma: MIDI e Guitar Pro em dois canais de onda quadrada'
        if ($LASTEXITCODE -ne 0) { Parar 'Não consegui criar o repositório.' }
    }
    git remote add origin "https://github.com/$login/$Nome.git"
}

function Ligar-Pages {
    gh api -X POST "repos/$login/$Nome/pages" -f build_type=workflow --silent 2>$null
    if ($LASTEXITCODE -ne 0) { gh api -X PUT "repos/$login/$Nome/pages" -f build_type=workflow --silent 2>$null }
    return ($LASTEXITCODE -eq 0)
}

Passo 'GitHub Pages'
$pagesAntes = Ligar-Pages
if ($pagesAntes) { Write-Host 'Pages ligado, publicando pelo GitHub Actions.' }

Passo 'Enviando'
git push -u origin main
if ($LASTEXITCODE -ne 0) { Parar 'O envio falhou. Se o repositório no GitHub já tinha outros arquivos, apague-o ou use -Nome com outro nome.' }

if (-not $pagesAntes) {
    if (Ligar-Pages) {
        Write-Host 'Pages ligado depois do envio; disparando a publicação.'
        for ($i = 0; $i -lt 10; $i++) {
            Start-Sleep -Seconds 3
            gh workflow run pages.yml --ref main 2>$null
            if ($LASTEXITCODE -eq 0) { break }
        }
    } else {
        Write-Host 'Não consegui ligar o Pages sozinho. No GitHub, abra Settings > Pages e em Source escolha "GitHub Actions".' -ForegroundColor Yellow
    }
}

Passo 'Acompanhando a publicação'
Start-Sleep -Seconds 5
$run = gh run list --workflow pages.yml --limit 1 --json databaseId --jq '.[0].databaseId' 2>$null
if ($run) { gh run watch $run --exit-status }

$site = "https://$login.github.io/$Nome/"
Write-Host ''
Write-Host "Site: $site" -ForegroundColor Green
Write-Host "Enviar músicas pelo celular: https://github.com/$login/$Nome/upload/main/musicas"
Write-Host 'Pode levar um ou dois minutos para o endereço responder na primeira vez.'
