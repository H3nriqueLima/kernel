# Prepara o ambiente do K.E.R.N.E.L: Python 3.12 + dependencias numa pasta .venv.
# Uso:  powershell -ExecutionPolicy Bypass -File instalar.ps1
#       (acrescente -SemTreino para pular o PyTorch, que e grande)
# (Sem acentos de proposito: o PowerShell 5.1 le arquivos .ps1 sem BOM como ANSI.)
param([switch]$SemTreino)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    # O torch-directml (treino na RX 570) so existe ate o Python 3.12.
    py -V:3.12 -c "print('Python 3.12 encontrado')"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Instalando o Python 3.12..."
        py install 3.12
    }
    py -V:3.12 -m venv .venv
}

$python = ".venv\Scripts\python.exe"
& $python -m pip install --quiet --disable-pip-version-check --upgrade pip
& $python -m pip install --quiet --disable-pip-version-check -r requirements.txt -r requirements-voz.txt -r requirements-dev.txt
if (-not $SemTreino) {
    Write-Host "Instalando o PyTorch com DirectML (uns 300 MB)..."
    & $python -m pip install --quiet --disable-pip-version-check -r requirements-treino.txt
}

if (-not (Test-Path "kernel.toml")) {
    Copy-Item "kernel.exemplo.toml" "kernel.toml"
    Write-Host "Criei o kernel.toml a partir do modelo. E nele que voce diz ate onde ele pode ir."
}

& $python -m pytest
Write-Host ""
Write-Host "Pronto. Para ligar: iniciar.bat"
