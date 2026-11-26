@echo off
setlocal
set "KADR_SELF=%~f0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$raw=[IO.File]::ReadAllText($env:KADR_SELF,[Text.Encoding]::UTF8); $mark='@@KADR_PS@@'; $a=$raw.LastIndexOf($mark)+$mark.Length; if($a -lt $mark.Length){throw 'Invalid Kadr launcher'}; Invoke-Expression $raw.Substring($a)"
exit /b %errorlevel%
@@KADR_PS@@
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Download-File([string]$Url, [string]$Destination) {
    Write-Host "Завантажую $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
    if (-not (Test-Path -LiteralPath $Destination) -or (Get-Item -LiteralPath $Destination).Length -eq 0) {
        throw "Завантаження не вдалося: $Url"
    }
}

function Run-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Команда завершилася з помилкою $LASTEXITCODE`: $Exe" }
}

function Update-App([string]$Root, [string]$App, [string]$Cache) {
    $versionFile = Join-Path $App '.release-version'
    $installed = if (Test-Path -LiteralPath $versionFile) { (Get-Content -LiteralPath $versionFile -Raw).Trim() } else { '' }
    try {
        $api = if ($env:KADR_RELEASE_API) { $env:KADR_RELEASE_API } else { 'https://api.github.com/repos/HOKER1597/DownloadSerialsUA/releases/latest' }
        $release = Invoke-RestMethod -Uri $api -Headers @{ 'User-Agent' = 'DownloadSerialsUA'; 'Accept' = 'application/vnd.github+json' }
        $version = [string]$release.tag_name
        if (-not $version) { throw 'У релізі немає версії.' }
        if ($installed -eq $version -and (Test-Path -LiteralPath (Join-Path $App 'backend\launch.py'))) {
            Write-Host "Кадр уже оновлений: $version"
            return
        }
        $asset = $release.assets | Where-Object { $_.name -eq 'kadr-app.zip' } | Select-Object -First 1
        $checksum = $release.assets | Where-Object { $_.name -eq 'kadr-app.zip.sha256' } | Select-Object -First 1
        if (-not $asset -or -not $checksum) { throw 'Реліз не містить архіву або контрольної суми.' }
        Write-Host "Оновлюю Кадр до $version..."
        $zip = Join-Path $Cache 'kadr-app.zip'
        $sum = Join-Path $Cache 'kadr-app.zip.sha256'
        Download-File $asset.browser_download_url $zip
        Download-File $checksum.browser_download_url $sum
        $expected = ((Get-Content -LiteralPath $sum -Raw) -split '\s+')[0].ToLowerInvariant()
        $actual = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([IO.File]::ReadAllBytes($zip))).Replace('-', '').ToLowerInvariant()
        if ($expected -notmatch '^[a-f0-9]{64}$' -or $actual -ne $expected) { throw 'Контрольна сума архіву не збігається.' }
        $stage = Join-Path $Root 'app.new'
        $backup = Join-Path $Root 'app.old'
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
        Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force
        foreach ($required in @('backend\launch.py', 'frontend\dist\index.html', 'requirements-runtime.txt')) {
            if (-not (Test-Path -LiteralPath (Join-Path $stage $required))) { throw "В архіві немає $required" }
        }
        Set-Content -LiteralPath (Join-Path $stage '.release-version') -Value $version -Encoding Ascii
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
        if (Test-Path -LiteralPath $App) { Move-Item -LiteralPath $App -Destination $backup }
        try { Move-Item -LiteralPath $stage -Destination $App }
        catch {
            if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $App }
            throw
        }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
        Remove-Item -LiteralPath $zip, $sum -Force
        Write-Host "Кадр оновлено: $version"
    } catch {
        if (-not (Test-Path -LiteralPath (Join-Path $App 'backend\launch.py'))) { throw "Не вдалося встановити Кадр: $($_.Exception.Message)" }
        Write-Warning "Не вдалося перевірити оновлення; запускаю встановлену версію. $($_.Exception.Message)"
    }
}

try {
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'Потрібна 64-бітна Windows.' }
    $root = if ($env:KADR_INSTALL_ROOT) { $env:KADR_INSTALL_ROOT } else { Join-Path $env:LOCALAPPDATA 'DownloadSerialsUA' }
    $root = [IO.Path]::GetFullPath($root)
    $app = Join-Path $root 'app'
    $runtime = Join-Path $root 'runtime'
    $pythonDir = Join-Path $runtime 'python'
    $python = Join-Path $pythonDir 'python.exe'
    $ffmpegDir = Join-Path $runtime 'ffmpeg'
    $browsers = Join-Path $runtime 'browsers'
    $cache = Join-Path $root 'cache'
    New-Item -ItemType Directory -Force -Path $root, $runtime, $cache | Out-Null
    Update-App $root $app $cache
    $env:KADR_DATA_DIR = Join-Path $root 'data'
    New-Item -ItemType Directory -Force -Path $env:KADR_DATA_DIR | Out-Null

    if (-not (Test-Path -LiteralPath $python)) {
        Write-Host 'Встановлюю приватний Python 3.12...'
        $zip = Join-Path $cache 'python.zip'
        Download-File 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' $zip
        $stage = Join-Path $root 'python.new'
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
        Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force
        $pth = Get-ChildItem -LiteralPath $stage -Filter '*._pth' | Select-Object -First 1
        if (-not $pth) { throw 'Не знайдено конфігурацію вбудованого Python.' }
        Add-Content -LiteralPath $pth.FullName -Value "`r`nLib\site-packages`r`nimport site" -Encoding Ascii
        New-Item -ItemType Directory -Force -Path (Join-Path $stage 'Lib\site-packages') | Out-Null
        Move-Item -LiteralPath $stage -Destination $pythonDir
        Remove-Item -LiteralPath $zip -Force
    }

    $pythonPathFile = (Get-ChildItem -LiteralPath $pythonDir -Filter '*._pth' | Select-Object -First 1).FullName
    $backendPath = Join-Path $app 'backend'
    if (-not ((Get-Content -LiteralPath $pythonPathFile) -contains $backendPath)) {
        Add-Content -LiteralPath $pythonPathFile -Value $backendPath -Encoding UTF8
    }

    if (-not (Test-Path -LiteralPath (Join-Path $pythonDir 'Lib\site-packages\pip'))) {
        Write-Host 'Встановлюю pip...'
        $getPip = Join-Path $cache 'get-pip.py'
        Download-File 'https://bootstrap.pypa.io/get-pip.py' $getPip
        Run-Checked $python @($getPip, '--no-warn-script-location')
        Remove-Item -LiteralPath $getPip -Force
    }

    $requirements = Join-Path $app 'requirements-runtime.txt'
    $requirementsHash = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([IO.File]::ReadAllBytes($requirements))).Replace('-', '')
    $requirementsMarker = Join-Path $runtime 'requirements.sha256'
    $installedRequirements = if (Test-Path -LiteralPath $requirementsMarker) { (Get-Content -LiteralPath $requirementsMarker -Raw).Trim() } else { '' }
    if ($installedRequirements -ne $requirementsHash) {
        Write-Host 'Встановлюю бібліотеки Кадру...'
        Run-Checked $python @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-warn-script-location', '--no-cache-dir', '-r', $requirements)
        Set-Content -LiteralPath $requirementsMarker -Value $requirementsHash -Encoding Ascii
    }

    if (-not (Test-Path -LiteralPath (Join-Path $ffmpegDir 'ffmpeg.exe')) -or -not (Test-Path -LiteralPath (Join-Path $ffmpegDir 'ffprobe.exe'))) {
        Write-Host 'Встановлюю FFmpeg...'
        $zip = Join-Path $cache 'ffmpeg.zip'
        Download-File 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' $zip
        $stage = Join-Path $root 'ffmpeg.new'
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
        Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force
        $ffmpeg = Get-ChildItem -LiteralPath $stage -Filter 'ffmpeg.exe' -Recurse | Select-Object -First 1
        $ffprobe = Get-ChildItem -LiteralPath $stage -Filter 'ffprobe.exe' -Recurse | Select-Object -First 1
        if (-not $ffmpeg -or -not $ffprobe) { throw 'Архів FFmpeg не містить потрібних програм.' }
        New-Item -ItemType Directory -Force -Path $ffmpegDir | Out-Null
        Copy-Item -LiteralPath $ffmpeg.FullName -Destination (Join-Path $ffmpegDir 'ffmpeg.exe') -Force
        Copy-Item -LiteralPath $ffprobe.FullName -Destination (Join-Path $ffmpegDir 'ffprobe.exe') -Force
        Remove-Item -LiteralPath $stage -Recurse -Force
        Remove-Item -LiteralPath $zip -Force
    }

    $env:PLAYWRIGHT_BROWSERS_PATH = $browsers
    $browserExecutable = (& $python -c 'from playwright.sync_api import sync_playwright; p=sync_playwright().start(); print(p.chromium.executable_path); p.stop()' | Select-Object -Last 1).Trim()
    if (-not (Test-Path -LiteralPath $browserExecutable)) {
        Write-Host 'Встановлюю Chromium для пошуку UAKINO...'
        Run-Checked $python @('-m', 'playwright', 'install', '--no-shell', 'chromium')
    }

    $env:PATH = "$ffmpegDir;$env:PATH"
    Write-Host "Кадр готовий. Папка програми: $root"
    Run-Checked $python @((Join-Path $app 'backend\launch.py'))
} catch {
    Write-Host "Помилка: $($_.Exception.Message)" -ForegroundColor Red
    if (-not $env:KADR_NONINTERACTIVE) {
        Write-Host 'Натисніть Enter, щоб закрити вікно.'
        [Console]::ReadLine() | Out-Null
    }
    exit 1
}
