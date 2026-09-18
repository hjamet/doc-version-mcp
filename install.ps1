# ==============================================================================
# install.ps1 — Moteur d'Installation Automatisé One-Liner Windows
# FastMCP doc-version : Content-Addressable Storage & AST Diffs Engine
# ==============================================================================
# Usage distant (One-Liner) :
#   irm https://raw.githubusercontent.com/hjamet/doc-version-mcp/main/install.ps1 | iex
# Usage local :
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
# ==============================================================================

[CmdletBinding()]
param(
    [string]$InstallDir = ""
)

$ErrorActionPreference = "Stop"

# Forcer la sortie en UTF-8 pour un rendu propre des caracteres speciaux
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

Write-Host ""
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "                   FastMCP doc-version - Windows Installer                    " -ForegroundColor Cyan
Write-Host "           Content-Addressable Storage (CAS) & AST Diffs Engine               " -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------------------------
# 1. Detection du mode d'execution & Repertoire Cible
# ------------------------------------------------------------------------------
Write-Host "[1/8] Analyse de l'environnement d'execution..." -ForegroundColor Yellow

$TargetDir = $null

if ($InstallDir -and (Test-Path $InstallDir)) {
    $TargetDir = (Resolve-Path $InstallDir).Path
    Write-Host "      Repertoire cible specifie manuellement : $TargetDir" -ForegroundColor Gray
} else {
    # Verification si le script s'execute deja au sein du depot clone
    $candidateDirs = @()
    if ($PSScriptRoot) {
        $candidateDirs += $PSScriptRoot
    }
    $candidateDirs += (Get-Location).Path

    foreach ($dir in $candidateDirs) {
        $pyproject = Join-Path $dir "pyproject.toml"
        if (Test-Path $pyproject) {
            $content = Get-Content -Path $pyproject -Raw -ErrorAction SilentlyContinue
            if ($content -match "doc-version-mcp" -or $content -match "doc_version_mcp") {
                $TargetDir = (Resolve-Path $dir).Path
                Write-Host "      Depot local detecte : $TargetDir" -ForegroundColor Gray
                break
            }
        }
    }

    if (-not $TargetDir) {
        $TargetDir = Join-Path $env:USERPROFILE "Documents\code\doc-version-mcp"
        Write-Host "      Mode One-Liner distant : deploiement dans $TargetDir" -ForegroundColor Gray
    }
}

# ------------------------------------------------------------------------------
# 2. Verification des Prerequis Systeme (git, python / uv >= 3.10)
# ------------------------------------------------------------------------------
Write-Host "[2/8] Verification des prerequis systeme..." -ForegroundColor Yellow

# Verification de git
$gitCmd = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitCmd) {
    Write-Error "Git est introuvable dans le PATH. Veuillez installer Git pour Windows : https://git-scm.com/download/win"
    exit 1
}
Write-Host "  [OK] Git detecte : $($gitCmd.Source)" -ForegroundColor Green

# Verification de Python / uv via snippet autonome
$pyCheckSnippet = "import sys; sys.stdout.write(sys.version.split()[0]); sys.exit(0 if sys.version_info >= (3, 10) else 1)"

function Find-CompatiblePython {
    param([string]$CheckScript)

    # 1. Detection uv
    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCmd) {
        try {
            $uvVer = & uv run python -c $CheckScript 2>$null
            if ($LASTEXITCODE -eq 0 -and $uvVer) {
                return @{
                    Tool    = "uv"
                    Command = "uv"
                    Version = $uvVer.Trim()
                }
            }
        } catch {}
    }

    # 2. Detection py launcher (Windows)
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $candidates = @("-3.12", "-3.11", "-3.10", "-3")
        foreach ($arg in $candidates) {
            try {
                $pyVer = & py $arg -c $CheckScript 2>$null
                if ($LASTEXITCODE -eq 0 -and $pyVer) {
                    return @{
                        Tool    = "py"
                        Command = "py"
                        Args    = @($arg)
                        Version = $pyVer.Trim()
                    }
                }
            } catch {}
        }
    }

    # 3. Detection python standard dans le PATH
    $pyExe = Get-Command python -ErrorAction SilentlyContinue
    if ($pyExe) {
        try {
            $pVer = & python -c $CheckScript 2>$null
            if ($LASTEXITCODE -eq 0 -and $pVer) {
                return @{
                    Tool    = "python"
                    Command = "python"
                    Args    = @()
                    Version = $pVer.Trim()
                }
            }
        } catch {}
    }

    return $null
}

$pythonInfo = Find-CompatiblePython -CheckScript $pyCheckSnippet
if (-not $pythonInfo) {
    Write-Error "Python >= 3.10 est introuvable. Veuillez installer Python 3.10+ (ou uv) : https://www.python.org/downloads/"
    exit 1
}
Write-Host "  [OK] Python detecte ($($pythonInfo.Tool)) : Version $($pythonInfo.Version)" -ForegroundColor Green

# ------------------------------------------------------------------------------
# 3. Clonage ou Mise a Jour Idempotente du Depot
# ------------------------------------------------------------------------------
Write-Host "[3/8] Preparation du code source..." -ForegroundColor Yellow

$repoUrl = "https://github.com/hjamet/doc-version-mcp.git"

if (-not (Test-Path $TargetDir)) {
    Write-Host "      Clonage du depot $repoUrl vers $TargetDir..." -ForegroundColor Cyan
    $parentDir = Split-Path -Parent $TargetDir
    if (-not (Test-Path $parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }
    git clone $repoUrl $TargetDir
    Write-Host "  [OK] Depot clone avec succes." -ForegroundColor Green
} else {
    if (Test-Path (Join-Path $TargetDir ".git")) {
        $hasOrigin = git -C $TargetDir remote | Select-String -Pattern "^origin$"
        if ($hasOrigin) {
            Write-Host "      Mise a jour du depot existant via git pull..." -ForegroundColor Cyan
            try {
                git -C $TargetDir pull --ff-only
                Write-Host "  [OK] Depot synchronise." -ForegroundColor Green
            } catch {
                Write-Warning "Impossible d'effectuer git pull --ff-only. Conservation des fichiers locaux."
            }
        } else {
            Write-Host "  [OK] Depot local actif (pas de remote 'origin' distant)." -ForegroundColor Green
        }
    } else {
        Write-Host "  [OK] Dossier cible pret : $TargetDir" -ForegroundColor Green
    }
}

# ------------------------------------------------------------------------------
# 4. Environnement Virtuel Python & Installation Editables
# ------------------------------------------------------------------------------
Write-Host "[4/8] Configuration de l'environnement virtuel (.venv)..." -ForegroundColor Yellow

$VenvDir = Join-Path $TargetDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvExe = Join-Path $VenvDir "Scripts\doc-version.exe"
$hasUv = [bool](Get-Command uv -ErrorAction SilentlyContinue)

if (-not (Test-Path $VenvPython)) {
    Write-Host "      Creation de l'environnement virtuel Python..." -ForegroundColor Cyan
    if ($hasUv) {
        & uv venv --clear $VenvDir
    } elseif ($pythonInfo.Tool -eq "py") {
        & py $pythonInfo.Args -m venv $VenvDir
    } else {
        & python -m venv $VenvDir
    }
}

Write-Host "      Installation du package doc-version-mcp en mode editable..." -ForegroundColor Cyan
if ($hasUv) {
    & uv pip install --python $VenvPython -e $TargetDir
} else {
    & $VenvPython -m pip install --upgrade pip --quiet
    & $VenvPython -m pip install -e $TargetDir --quiet
}

if (-not (Test-Path $VenvExe)) {
    # Fallback de securite si l'entrypoint n'a pas encore ete genere
    Write-Host "      Generation du wrapper d'entree doc-version.exe..." -ForegroundColor DarkGray
    & $VenvPython -m pip install -e $TargetDir
}
Write-Host "  [OK] Environnement virtuel configure : $VenvPython" -ForegroundColor Green

# ------------------------------------------------------------------------------
# 5. Initialisation du Repertoire CAS (Content-Addressable Storage)
# ------------------------------------------------------------------------------
Write-Host "[5/8] Initialisation du stockage CAS..." -ForegroundColor Yellow

$casBase = Join-Path $env:USERPROFILE ".gemini\antigravity\cas_commits"
$casCommits = Join-Path $casBase "commits"
$casObjects = Join-Path $casBase "objects"

if (-not (Test-Path $casCommits)) {
    New-Item -ItemType Directory -Path $casCommits -Force | Out-Null
}
if (-not (Test-Path $casObjects)) {
    New-Item -ItemType Directory -Path $casObjects -Force | Out-Null
}
Write-Host "  [OK] Repertoires CAS operationnels dans $casBase" -ForegroundColor Green

# ------------------------------------------------------------------------------
# 6. Enregistrement Atomique MCP Antigravity
# ------------------------------------------------------------------------------
Write-Host "[6/8] Enregistrement dans les configurations MCP Antigravity..." -ForegroundColor Yellow

$config1 = Join-Path $env:USERPROFILE ".gemini\antigravity\mcp_config.json"
$config2 = Join-Path $env:USERPROFILE ".gemini\config\mcp_config.json"

# Script Python inline autonome pour mise a jour atomique sans alterer les autres serveurs MCP
$pyMcpUpdater = @'
import sys
import json
import os
from pathlib import Path

exe_path = sys.argv[1]
cas_dir = sys.argv[2]
config_paths = sys.argv[3:]

sys_root = os.environ.get("SystemRoot", "C:\\Windows")
sys_path = os.environ.get("PATH", "")

server_def = {
    "command": exe_path,
    "args": [],
    "env": {
        "SystemRoot": sys_root,
        "PATH": sys_path,
        "DOC_VERSION_COMMITS_DIR": cas_dir
    }
}

updated_count = 0
for p in config_paths:
    cfg_file = Path(p)
    if not cfg_file.parent.exists():
        continue

    data = {}
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception as e:
            data = {}

    if not isinstance(data, dict):
        data = {}
    if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
        data["mcpServers"] = {}

    data["mcpServers"]["doc-version"] = server_def

    tmp_file = cfg_file.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    os.replace(tmp_file, cfg_file)
    print(f"      Configuration mise a jour : {cfg_file}")
    updated_count += 1

if updated_count == 0:
    print("      Aucun fichier de configuration MCP detecte a mettre a jour.")
'@

$b64Code = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($pyMcpUpdater))
& $VenvPython -c "import base64, sys; exec(compile(base64.b64decode('$b64Code').decode('utf-8'), '<inline>', 'exec'))" $VenvExe $casBase $config1 $config2
Write-Host "  [OK] Serveur 'doc-version' inscrit dans mcpServers." -ForegroundColor Green

# ------------------------------------------------------------------------------
# 7. Deploiement des Schemas et Metadonnees MCP
# ------------------------------------------------------------------------------
Write-Host "[7/8] Deploiement des schemas MCP locaux..." -ForegroundColor Yellow

$metadataSrc = Join-Path $TargetDir "mcp_metadata"
$metadataDst = Join-Path $env:USERPROFILE ".gemini\antigravity\mcp\doc-version"

if (Test-Path $metadataSrc) {
    if (-not (Test-Path $metadataDst)) {
        New-Item -ItemType Directory -Path $metadataDst -Force | Out-Null
    }
    Copy-Item -Path (Join-Path $metadataSrc "*") -Destination $metadataDst -Recurse -Force
    Write-Host "  [OK] Schemas et instructions deployes dans $metadataDst" -ForegroundColor Green
} else {
    Write-Host "      Dossier mcp_metadata absent du depot local (etape optionnelle ignoree)." -ForegroundColor Gray
}

# ------------------------------------------------------------------------------
# 8. Wrappers CLI Universels & Smoke Test In-Situ
# ------------------------------------------------------------------------------
Write-Host "[8/8] Generation des wrappers CLI et Smoke Test..." -ForegroundColor Yellow

$localBin = Join-Path $env:USERPROFILE ".local\bin"
if (-not (Test-Path $localBin)) {
    New-Item -ItemType Directory -Path $localBin -Force | Out-Null
}

$cmdWrapper = Join-Path $localBin "doc-version.cmd"
$ps1Wrapper = Join-Path $localBin "doc-version.ps1"

$cmdContent = "@echo off`r`n`"$VenvExe`" %*`r`n"
[System.IO.File]::WriteAllText($cmdWrapper, $cmdContent, [System.Text.Encoding]::ASCII)

$ps1Content = '& "' + $VenvExe + '" @args' + "`r`n"
[System.IO.File]::WriteAllText($ps1Wrapper, $ps1Content, [System.Text.Encoding]::UTF8)

Write-Host "  [OK] Wrappers generes : $cmdWrapper et $ps1Wrapper" -ForegroundColor Green

# Smoke Test in-situ
try {
    $smokeOutput = & $VenvPython -c "import doc_version_mcp; print('FastMCP doc-version operationnel')" 2>&1
    Write-Host "  [OK] Smoke Test reussi : $smokeOutput" -ForegroundColor Green
} catch {
    Write-Error "Echec du smoke test doc_version_mcp : $_"
    exit 1
}

# ------------------------------------------------------------------------------
# Succes & Instructions d'Utilisation
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "              INSTALLATION DE doc-version-mcp REUSSIE AVEC SUCCES !           " -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Emplacement : $TargetDir" -ForegroundColor White
Write-Host "  Executable  : $VenvExe" -ForegroundColor White
Write-Host "  Stockage CAS: $casBase" -ForegroundColor White
Write-Host "  Serveur MCP : doc-version (enregistre dans Antigravity)" -ForegroundColor White
Write-Host ""
Write-Host "  Utilisation en ligne de commande :" -ForegroundColor Yellow
Write-Host "     doc-version" -ForegroundColor Cyan
Write-Host "     python -m doc_version_mcp.server" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Si '.local\bin' n'est pas encore dans votre PATH utilisateur :" -ForegroundColor Gray
Write-Host "     [Environment]::SetEnvironmentVariable('Path', `"$([Environment]::GetEnvironmentVariable('Path', 'User'));$localBin`", 'User')" -ForegroundColor DarkGray
Write-Host ""
