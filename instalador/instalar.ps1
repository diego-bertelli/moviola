# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
<#
.SYNOPSIS
  Instala Moviola y, por consola, todo lo que necesita para funcionar.

.DESCRIPTION
  Sin permisos de administrador (salvo, si hace falta, para el componente WebView2 o el runtime de Visual C++, que piden el suyo).
  Instala, en este orden:
    1. Moviola (con su propio Python, sus bibliotecas y FFmpeg: viene dentro del paquete, no baja nada).
    2. whisper.cpp (whisper-cli), para transcribir subtitulos.        -> %LOCALAPPDATA%\Programs\whisper.cpp
    3. Un modelo de whisper (ggml-*.bin), a eleccion.                   -> %USERPROFILE%\whisper-modelos
    4. yt-dlp, para bajar videos o audio de YouTube.                    -> <carpeta de Moviola>\bin
    5. WebView2 (la ventana de Moviola), si Windows no lo trae.
    6. Accesos directos, "Aplicaciones instaladas" de Windows y doble clic en los archivos .moviola.
  Lo que ya esta instalado en la PC no se vuelve a bajar. Todo lo que se baja se verifica con su suma SHA-256.

.EXAMPLE
  Instalar-Moviola.bat
  Instalar-Moviola.bat -Silencioso
  Instalar-Moviola.bat -Modelo small -SinYtdlp
#>
[CmdletBinding()]
param(
    [string]$Destino = (Join-Path $env:LOCALAPPDATA 'Programs\Moviola'),
    [ValidateSet('pregunta', 'turbo', 'turbo-q5', 'small', 'base', 'ninguno')][string]$Modelo = 'pregunta',
    [string]$Whisper = (Join-Path $env:LOCALAPPDATA 'Programs\whisper.cpp'),
    [string]$Modelos = (Join-Path $env:USERPROFILE 'whisper-modelos'),
    [switch]$SinWhisper,
    [switch]$SinYtdlp,
    [switch]$SinWebView2,
    [switch]$SinAccesos,
    [switch]$SinEscritorio,
    [switch]$SinAsociar,
    [switch]$Silencioso,
    [switch]$Forzar,
    [switch]$SinSalida
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }

# ----------------------------------------------------------------------------------------------------------- lo que se baja

$MODELO_POR_DEFECTO = 'turbo-q5'
$CATALOGO = [ordered]@{
    'turbo'    = @{ archivo = 'ggml-large-v3-turbo.bin';     bytes = 1624555275; sha = '1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69'
                    texto = 'large-v3-turbo completo: la mejor calidad' }
    'turbo-q5' = @{ archivo = 'ggml-large-v3-turbo-q5_0.bin'; bytes = 574041195;  sha = '394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2'
                    texto = 'large-v3-turbo comprimido: casi igual de bueno, ocupa un tercio' }
    'small'    = @{ archivo = 'ggml-small.bin';              bytes = 487601967;  sha = '1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b'
                    texto = 'small: mas rapido, sirve para voz clara' }
    'base'     = @{ archivo = 'ggml-base.bin';               bytes = 147951465;  sha = '60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe'
                    texto = 'base: el mas liviano, se equivoca mas' }
}
$URL_MODELOS = 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/'
# whisper.cpp: una version fija, la que se probo con Moviola (la ultima "etiquetada" no trae programas para Windows)
$WHISPER_ZIP = @{ url = 'https://github.com/ggml-org/whisper.cpp/releases/download/b5454/whisper-bin-x64.zip'
                  sha = '6ba69e3482d7826214f90a6a9c84ca07782aec1e1d0c6a7c30c994fd5d816ccb'; version = 'b5454' }
# yt-dlp: siempre la ultima (YouTube cambia seguido); se verifica con el archivo de sumas de esa misma version
$YTDLP_URL = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe'
$YTDLP_SUMAS = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-256SUMS'
$WEBVIEW2_URL = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'
$VCREDIST_URL = 'https://aka.ms/vs/17/release/vc_redist.x64.exe'

$MARCA = '.moviola-instalado'
$WhisperElegido = $PSBoundParameters.ContainsKey('Whisper')     # (dentro de una funcion, $PSBoundParameters seria el de la funcion)
$ModelosElegido = $PSBoundParameters.ContainsKey('Modelos')
$RAIZ = Split-Path -Parent $PSScriptRoot
$PAQUETE = Join-Path $RAIZ 'paquete'
$resumen = New-Object System.Collections.ArrayList
$avisos = New-Object System.Collections.ArrayList

# ----------------------------------------------------------------------------------------------------------- utilidades

function Titulo([string]$t) { Write-Host ''; Write-Host $t -ForegroundColor Cyan }
function Bien([string]$t) { Write-Host ('  [ok] ' + $t) -ForegroundColor Green }
function Info([string]$t) { Write-Host ('       ' + $t) }
function Ojo([string]$t) { Write-Host ('  [!]  ' + $t) -ForegroundColor Yellow; [void]$avisos.Add($t) }
function Resumir([string]$nombre, [string]$estado, [string]$detalle) { [void]$resumen.Add(@{ nombre = $nombre; estado = $estado; detalle = $detalle }) }

function Preguntar-SiNo([string]$texto, [bool]$defecto) {
    if ($Silencioso) { return $defecto }
    $sufijo = if ($defecto) { '[S/n]' } else { '[s/N]' }
    try { $r = Read-Host ('  ' + $texto + ' ' + $sufijo) } catch { return $defecto }
    if ([string]::IsNullOrWhiteSpace($r)) { return $defecto }
    return ($r.Trim().ToLower() -in @('s', 'si', 'sí', 'y', 'yes'))
}

function Formato-Tamano([double]$bytes) {
    if ($bytes -ge 1GB) { return ('{0:N1} GB' -f ($bytes / 1GB)) }
    return ('{0:N0} MB' -f ($bytes / 1MB))
}

function Espacio-Libre([string]$carpeta) {
    try {
        $letra = [System.IO.Path]::GetPathRoot((Resolve-Path -LiteralPath $carpeta -ErrorAction Stop).Path).Substring(0, 1)
        return (Get-PSDrive -Name $letra -ErrorAction Stop).Free
    } catch { return [double]::MaxValue }
}

function Hay-Internet {
    if ($env:MOVIOLA_SIN_INTERNET -eq '1') { return $false }     # solo para probar el camino sin conexion
    try {
        $r = Invoke-WebRequest -Uri 'https://github.com' -Method Head -UseBasicParsing -TimeoutSec 15
        return $true
    } catch { return $false }
}

# Baja un archivo con curl.exe (viene con Windows 10/11; muestra el avance y retoma si se corta) o, si no esta, con BITS.
# Lo deja en $archivo solo si la suma SHA-256 coincide (cuando se conoce).
function Descargar([string]$url, [string]$archivo, [string]$sha = '') {
    $carpeta = Split-Path -Parent $archivo
    if (-not (Test-Path -LiteralPath $carpeta)) { New-Item -ItemType Directory -Path $carpeta -Force | Out-Null }
    $parte = $archivo + '.part'
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    for ($intento = 1; $intento -le 2; $intento++) {
        $codigo = 0
        if ($curl) {
            & $curl.Source -L --fail --retry 5 --retry-delay 3 --connect-timeout 20 -C - -o $parte $url
            $codigo = $LASTEXITCODE
        } else {
            try { Start-BitsTransfer -Source $url -Destination $parte -ErrorAction Stop } catch { $codigo = 1 }
        }
        if (-not (Test-Path -LiteralPath $parte)) { continue }
        if ($sha) {
            $h = (Get-FileHash -LiteralPath $parte -Algorithm SHA256).Hash
            if ($h -ne $sha.ToUpper()) {
                Info 'La suma de verificación no coincide: empiezo de nuevo.'
                Remove-Item -LiteralPath $parte -Force
                continue
            }
        } elseif ($codigo -ne 0) { continue }
        Move-Item -LiteralPath $parte -Destination $archivo -Force
        return $true
    }
    if (Test-Path -LiteralPath $parte) { Remove-Item -LiteralPath $parte -Force -ErrorAction SilentlyContinue }
    return $false
}

function Descomprimir([string]$zip, [string]$carpeta) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if (Test-Path -LiteralPath $carpeta) { Remove-Item -LiteralPath $carpeta -Recurse -Force }
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $carpeta)
}

function Nuevo-Acceso([string]$ruta, [string]$objetivo, [string]$argumentos, [string]$carpeta, [string]$icono, [string]$descripcion) {
    $sh = New-Object -ComObject WScript.Shell
    $a = $sh.CreateShortcut($ruta)
    $a.TargetPath = $objetivo
    $a.Arguments = $argumentos
    $a.WorkingDirectory = $carpeta
    if ($icono -and (Test-Path -LiteralPath $icono)) { $a.IconLocation = $icono }
    $a.Description = $descripcion
    $a.Save()
}

function Avisar-Al-Explorador {
    try {
        Add-Type -Namespace Moviola -Name Shell -MemberDefinition '[System.Runtime.InteropServices.DllImport("shell32.dll")] public static extern void SHChangeNotify(int e, uint f, IntPtr a, IntPtr b);' -ErrorAction SilentlyContinue
        [Moviola.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
    } catch { }
}

# ----------------------------------------------------------------------------------------------------------- lo que ya hay

function Buscar-Whisper {
    if (-not $Forzar) {
        if ($WhisperElegido) {
            $c = Join-Path $Whisper 'whisper-cli.exe'
            if (Test-Path -LiteralPath $c) { return $c }
            return $null
        }
        $g = Get-Command whisper-cli -ErrorAction SilentlyContinue
        if ($g) { return $g.Source }
        foreach ($c in @((Join-Path $env:LOCALAPPDATA 'Programs\whisper.cpp\whisper-cli.exe'), (Join-Path $env:USERPROFILE 'whisper.cpp\build\bin\whisper-cli.exe'))) {
            if (Test-Path -LiteralPath $c) { return $c }
        }
    }
    return $null
}

function Buscar-Modelo {
    if ($Forzar) { return $null }
    $carpetas = @()
    if ($ModelosElegido) { $carpetas = @($Modelos) }
    else {
        if ($env:WHISPER_MODEL -and (Test-Path -LiteralPath $env:WHISPER_MODEL)) { return $env:WHISPER_MODEL }
        $carpetas = @((Join-Path $env:USERPROFILE 'whisper-modelos'), (Join-Path $env:USERPROFILE 'whisper.cpp\models'))
    }
    foreach ($c in $carpetas) {
        if (Test-Path -LiteralPath $c) {
            $f = Get-ChildItem -LiteralPath $c -Filter 'ggml-*.bin' -File -ErrorAction SilentlyContinue | Sort-Object Length -Descending | Select-Object -First 1
            if ($f) { return $f.FullName }
        }
    }
    return $null
}

function Buscar-Ytdlp {
    if (-not $Forzar) {
        $g = Get-Command yt-dlp -ErrorAction SilentlyContinue
        if ($g) { return $g.Source }
        $propio = Join-Path $Destino 'bin\yt-dlp.exe'
        if (Test-Path -LiteralPath $propio) { return $propio }
        $base = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
        if (Test-Path -LiteralPath $base) {
            foreach ($d in (Get-ChildItem -LiteralPath $base -Directory -Filter 'yt-dlp.yt-dlp*' -ErrorAction SilentlyContinue)) {
                $c = Join-Path $d.FullName 'yt-dlp.exe'
                if (Test-Path -LiteralPath $c) { return $c }
            }
        }
    }
    return $null
}

function Hay-WebView2 {
    $guid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    foreach ($k in @("HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$guid", "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$guid", "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$guid")) {
        try {
            $v = (Get-ItemProperty -LiteralPath $k -Name pv -ErrorAction Stop).pv
            if ($v -and $v -ne '0.0.0.0') { return $true }
        } catch { }
    }
    return $false
}

# Los instaladores de Microsoft (WebView2, Visual C++) se ejecutan solo si traen una firma digital valida de Microsoft.
function Firma-De-Microsoft([string]$archivo) {
    try {
        $f = Get-AuthenticodeSignature -LiteralPath $archivo
        return ($f.Status -eq 'Valid' -and $f.SignerCertificate -and $f.SignerCertificate.Subject -match 'O=Microsoft Corporation')
    } catch { return $false }
}

function Probar-Programa([string]$exe, [string[]]$argumentos) {
    try {
        $texto = ($argumentos | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '     # Start-Process no entrecomilla solo
        $p = Start-Process -FilePath $exe -ArgumentList $texto -NoNewWindow -Wait -PassThru -RedirectStandardOutput (Join-Path $env:TEMP 'moviola-prueba.out') -RedirectStandardError (Join-Path $env:TEMP 'moviola-prueba.err')
        return $p.ExitCode
    } catch { return -1 }
}

# ----------------------------------------------------------------------------------------------------------- manifiesto

function Leer-Manifiesto([string]$carpeta) {
    $f = Join-Path $carpeta $MARCA
    if (Test-Path -LiteralPath $f) {
        try { return (Get-Content -LiteralPath $f -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { }
    }
    return $null
}

# ============================================================================================================ programa
# ----------------------------------------------------------------------------------------------------------- 0. el punto de partida

$registro = Join-Path $env:TEMP 'moviola-instalacion.log'
try { Start-Transcript -Path $registro -Force | Out-Null } catch { }

try {
    Write-Host ''
    Write-Host '  MOVIOLA - instalador' -ForegroundColor Magenta
    Write-Host '  Editor de video y audio, local. Software libre (GNU GPL v3 o posterior), sin ninguna garantía.'
    Write-Host '  Autores: Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5).'

    if (-not [Environment]::Is64BitOperatingSystem) { throw 'Moviola necesita Windows de 64 bits.' }
    if ($PSVersionTable.PSVersion.Major -lt 5) { throw 'Hace falta Windows PowerShell 5 o más nuevo (viene con Windows 10 y 11).' }
    if (-not (Test-Path -LiteralPath (Join-Path $PAQUETE 'app.py')) -or -not (Test-Path -LiteralPath (Join-Path $PAQUETE 'python\pythonw.exe'))) {
        throw ('No encuentro el programa para instalar en ' + $PAQUETE + '. Descomprimí todo el instalador (no ejecutes Instalar-Moviola.bat desde adentro del .zip).')
    }
    $version = '?'
    $m = Select-String -LiteralPath (Join-Path $PAQUETE 'app.py') -Pattern "^VERSION\s*=\s*'([^']+)'" | Select-Object -First 1
    if ($m) { $version = $m.Matches[0].Groups[1].Value }
    $Destino = [System.IO.Path]::GetFullPath($Destino)
    Write-Host ('  Versión ' + $version + '  ->  ' + $Destino) -ForegroundColor Gray

    $internet = $null     # se averigua la primera vez que hace falta
    function Conexion { if ($null -eq $script:internet) { $script:internet = (Hay-Internet) }; return $script:internet }

    # ------------------------------------------------------------------------------------------------------- 1. Moviola
    Titulo '[1/6] Moviola'
    $anterior = Leer-Manifiesto $Destino
    if (Test-Path -LiteralPath $Destino) {
        $hay = @(Get-ChildItem -LiteralPath $Destino -Force -ErrorAction SilentlyContinue)
        if ($hay.Count -gt 0 -and -not $anterior) {
            throw ('La carpeta ' + $Destino + ' ya existe, tiene archivos y no la creó este instalador: no la toco. Elegí otra con  -Destino "C:\\otra\\carpeta".')
        }
    }
    if ($anterior) {
        $corren = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($Destino, [StringComparison]::OrdinalIgnoreCase) })
        if ($corren.Count -gt 0) {
            Ojo 'Moviola está abierto. Hay que cerrarlo para actualizarlo.'
            if (Preguntar-SiNo 'Lo cierro ahora (se pierde lo que no se haya guardado)?' $false) {
                $corren | ForEach-Object { try { $_.Kill() } catch { } }
                Start-Sleep -Seconds 2
            } else { throw 'Cerrá Moviola y volvé a ejecutar el instalador.' }
        }
        Info ('Ya hay una versión instalada (' + $anterior.version + '): se actualiza. Tus ajustes y tu caché se conservan (están en %LOCALAPPDATA%\Moviola).')
        foreach ($sub in @('python', 'motor', 'web', 'licencias')) {
            $r = Join-Path $Destino $sub
            if (Test-Path -LiteralPath $r) { Remove-Item -LiteralPath $r -Recurse -Force }
        }
    } else {
        New-Item -ItemType Directory -Path $Destino -Force | Out-Null
    }
    if ((Espacio-Libre $Destino) -lt 1.2GB) { throw 'No hay lugar en el disco (Moviola ocupa unos 600 MB).' }
    Info 'Copiando los archivos...'
    & robocopy.exe $PAQUETE $Destino /E /NFL /NDL /NJH /NJS /NP /R:2 /W:2 | Out-Null
    if ($LASTEXITCODE -ge 8) { throw ('No pude copiar los archivos (robocopy devolvió ' + $LASTEXITCODE + ').') }
    $global:LASTEXITCODE = 0
    $py = Join-Path $Destino 'python\python.exe'
    $c = Probar-Programa $py @('-I', '-c', 'import av, webview, PIL')
    if ($c -ne 0) { throw 'El Python de Moviola no arranca en esta PC (falta algo de Windows).' }
    Bien ('Moviola ' + $version + ' copiado y probado (Python, PyAV, pywebview, Pillow).')
    Resumir 'Moviola' 'ok' ($version + ' en ' + $Destino)

    # FFmpeg: viene en el paquete; si el paquete se armó sin él, se busca en la PC
    Titulo '[2/6] FFmpeg'
    $ffmpegPropio = Join-Path $Destino 'bin\ffmpeg.exe'
    if ((Test-Path -LiteralPath $ffmpegPropio) -and (Test-Path -LiteralPath (Join-Path $Destino 'bin\ffprobe.exe'))) {
        $v = ''
        try { $v = ((& $ffmpegPropio -version 2>&1 | Select-Object -First 1) -replace '^ffmpeg version\s+(\S+).*$', '$1') } catch { }
        Bien ('FFmpeg viene incluido (' + $v + ').')
        Resumir 'FFmpeg' 'ok' ('incluido: ' + $v)
    } else {
        $g = Get-Command ffmpeg -ErrorAction SilentlyContinue
        $gp = Get-Command ffprobe -ErrorAction SilentlyContinue
        if ($g -and $gp) {
            Bien ('FFmpeg ya está en la PC: ' + $g.Source)
            Resumir 'FFmpeg' 'ok' ('de la PC: ' + $g.Source)
        } else {
            Ojo 'Este paquete no trae FFmpeg y la PC tampoco lo tiene. Intento instalarlo con winget (Gyan.FFmpeg).'
            $w = Get-Command winget -ErrorAction SilentlyContinue
            $logrado = $false
            if ($w -and (Conexion)) {
                & $w.Source install --id Gyan.FFmpeg -e --silent --accept-package-agreements --accept-source-agreements
                $base = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
                $ff = Get-ChildItem -LiteralPath $base -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Where-Object { $_.FullName -like '*Gyan.FFmpeg*' } | Select-Object -First 1
                if ($ff) {
                    New-Item -ItemType Directory -Path (Join-Path $Destino 'bin') -Force | Out-Null
                    Copy-Item -LiteralPath $ff.FullName -Destination (Join-Path $Destino 'bin\ffmpeg.exe') -Force
                    Copy-Item -LiteralPath (Join-Path $ff.DirectoryName 'ffprobe.exe') -Destination (Join-Path $Destino 'bin\ffprobe.exe') -Force
                    $logrado = $true
                }
            }
            if ($logrado) { Bien 'FFmpeg instalado y copiado a la carpeta de Moviola.'; Resumir 'FFmpeg' 'ok' 'instalado con winget' }
            else { Ojo 'No pude instalar FFmpeg. Sin él Moviola no puede exportar: instalalo con  winget install Gyan.FFmpeg  y volvé a abrir Moviola.'; Resumir 'FFmpeg' 'falta' 'winget install Gyan.FFmpeg' }
        }
    }

    # ------------------------------------------------------------------------------------------------------- 3. whisper
    Titulo '[3/6] Transcripción (whisper.cpp y un modelo)'
    $whisperExe = $null
    $whisperNuevo = $false
    $whisperCarpetaPropia = $false
    $modeloRuta = $null
    $modeloNuevo = $false
    if ($SinWhisper) {
        Info 'Se omite (-SinWhisper). Los subtítulos se pueden escribir a mano.'
        Resumir 'Transcribir (whisper)' 'omitido' 'con -SinWhisper'
    } else {
        $whisperExe = Buscar-Whisper
        if ($whisperExe) {
            Bien ('whisper-cli ya está: ' + $whisperExe)
        } elseif (-not (Conexion)) {
            Ojo 'No hay conexión: no puedo bajar whisper.cpp. Volvé a ejecutar el instalador con internet.'
        } else {
            Info ('Bajando whisper.cpp ' + $WHISPER_ZIP.version + ' (8,5 MB)...')
            $zip = Join-Path $env:TEMP 'moviola-whisper-bin-x64.zip'
            if (Descargar $WHISPER_ZIP.url $zip $WHISPER_ZIP.sha) {
                $tmp = Join-Path $env:TEMP 'moviola-whisper-extraido'
                Descomprimir $zip $tmp
                $origen = Join-Path $tmp 'Release'
                if (-not (Test-Path -LiteralPath (Join-Path $origen 'whisper-cli.exe'))) { $origen = $tmp }
                # solo se anota como «mía» (para poder quitarla al desinstalar) una carpeta que no existía o estaba vacía
                $whisperCarpetaPropia = (-not (Test-Path -LiteralPath $Whisper)) -or (@(Get-ChildItem -LiteralPath $Whisper -Force -ErrorAction SilentlyContinue).Count -eq 0)
                New-Item -ItemType Directory -Path $Whisper -Force | Out-Null
                Copy-Item -Path (Join-Path $origen '*') -Destination $Whisper -Recurse -Force
                Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
                Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
                $whisperExe = Join-Path $Whisper 'whisper-cli.exe'
                $whisperNuevo = $true
                Bien ('whisper-cli instalado en ' + $Whisper)
            } else { Ojo 'No pude bajar whisper.cpp (la verificación falló o se cortó la conexión).' }
        }
        if ($whisperExe) {
            $c = Probar-Programa $whisperExe @('--help')
            if ($c -eq -1073741515) {
                Ojo 'whisper-cli no arranca: falta el runtime de Visual C++ de Windows.'
                if ((Conexion) -and (Preguntar-SiNo 'Lo instalo ahora? (Windows va a pedir permiso de administrador)' $true)) {
                    $vc = Join-Path $env:TEMP 'vc_redist.x64.exe'
                    if ((Descargar $VCREDIST_URL $vc) -and -not (Firma-De-Microsoft $vc)) {
                        Ojo 'El instalador de Visual C++ que bajé no tiene una firma válida de Microsoft: no lo ejecuto.'
                        Remove-Item -LiteralPath $vc -Force -ErrorAction SilentlyContinue
                    } elseif ((Test-Path -LiteralPath $vc) -and (Firma-De-Microsoft $vc)) {
                        Start-Process -FilePath $vc -ArgumentList '/install', '/quiet', '/norestart' -Wait | Out-Null
                        $c = Probar-Programa $whisperExe @('--help')
                    }
                }
            }
            if ($c -ne 0) { Ojo ('whisper-cli no responde bien en esta PC (código ' + $c + ').') }
            else { Bien 'whisper-cli responde.' }
        }

        # el modelo
        $modeloRuta = Buscar-Modelo
        if ($modeloRuta) {
            Bien ('Ya hay un modelo de whisper: ' + (Split-Path -Leaf $modeloRuta))
        } else {
            $eleccion = $Modelo
            if ($eleccion -eq 'pregunta') {
                if ($Silencioso) { $eleccion = $MODELO_POR_DEFECTO }
                else {
                    Write-Host ''
                    Write-Host '  Hace falta un modelo de whisper para transcribir. ¿Cuál instalo?'
                    $claves = @($CATALOGO.Keys)
                    for ($i = 0; $i -lt $claves.Count; $i++) {
                        $k = $claves[$i]
                        $marca = if ($k -eq $MODELO_POR_DEFECTO) { '  (recomendado)' } else { '' }
                        Write-Host ('    [{0}] {1}, {2}{3}' -f ($i + 1), $CATALOGO[$k].texto, (Formato-Tamano $CATALOGO[$k].bytes), $marca)
                    }
                    Write-Host '    [5] ninguno: escribo los subtítulos a mano'
                    $r = ''
                    try { $r = Read-Host ('  Número [Enter = ' + ([array]::IndexOf($claves, $MODELO_POR_DEFECTO) + 1) + ']') } catch { }
                    $n = 0
                    if ([string]::IsNullOrWhiteSpace($r)) { $eleccion = $MODELO_POR_DEFECTO }
                    elseif ([int]::TryParse($r.Trim(), [ref]$n) -and $n -ge 1 -and $n -le $claves.Count) { $eleccion = $claves[$n - 1] }
                    else { $eleccion = 'ninguno' }
                }
            }
            if ($eleccion -eq 'ninguno') {
                Info 'Sin modelo: se puede instalar más tarde volviendo a ejecutar el instalador.'
            } elseif (-not (Conexion)) {
                Ojo 'No hay conexión: no puedo bajar el modelo. Volvé a ejecutar el instalador con internet.'
            } else {
                $mo = $CATALOGO[$eleccion]
                $destinoModelo = Join-Path $Modelos $mo.archivo
                New-Item -ItemType Directory -Path $Modelos -Force | Out-Null
                if ((Espacio-Libre $Modelos) -lt ($mo.bytes * 1.1)) {
                    Ojo ('No hay lugar para el modelo (' + (Formato-Tamano $mo.bytes) + ') en ' + $Modelos + '.')
                } else {
                    Info ('Bajando ' + $mo.archivo + ' (' + (Formato-Tamano $mo.bytes) + '). Si se corta, volvé a ejecutar el instalador: sigue donde quedó.')
                    if (Descargar ($URL_MODELOS + $mo.archivo) $destinoModelo $mo.sha) {
                        $modeloRuta = $destinoModelo
                        $modeloNuevo = $true
                        Bien ('Modelo instalado y verificado: ' + $destinoModelo)
                    } else { Ojo 'No pude bajar el modelo.' }
                }
            }
        }
        if ($whisperExe -and $modeloRuta) { Resumir 'Transcribir (whisper)' 'ok' ((Split-Path -Leaf $modeloRuta)) }
        elseif ($whisperExe) { Resumir 'Transcribir (whisper)' 'falta' 'falta el modelo' }
        else { Resumir 'Transcribir (whisper)' 'falta' 'falta whisper-cli' }
    }

    # ------------------------------------------------------------------------------------------------------- 4. yt-dlp
    Titulo '[4/6] YouTube (yt-dlp)'
    $ytdlp = $null
    $ytdlpNuevo = $false
    if ($SinYtdlp) {
        Info 'Se omite (-SinYtdlp).'
        Resumir 'Bajar de YouTube (yt-dlp)' 'omitido' 'con -SinYtdlp'
    } else {
        $ytdlp = Buscar-Ytdlp
        if ($ytdlp) {
            Bien ('yt-dlp ya está: ' + $ytdlp)
        } elseif (-not (Conexion)) {
            Ojo 'No hay conexión: no puedo bajar yt-dlp.'
        } else {
            Info 'Bajando yt-dlp (la última versión, 23 MB)...'
            $sumas = Join-Path $env:TEMP 'moviola-yt-sumas.txt'
            $esperada = ''
            if (Descargar $YTDLP_SUMAS $sumas) {
                foreach ($l in (Get-Content -LiteralPath $sumas)) { if ($l -match '^([0-9a-fA-F]{64})\s+\*?yt-dlp\.exe\s*$') { $esperada = $Matches[1] } }
                Remove-Item -LiteralPath $sumas -Force -ErrorAction SilentlyContinue
            }
            if (-not $esperada) { Ojo 'No pude leer la suma de verificación de yt-dlp: no lo instalo.' }
            else {
                $nuevo = Join-Path $Destino 'bin\yt-dlp.exe'
                if (Descargar $YTDLP_URL $nuevo $esperada) {
                    $ytdlp = $nuevo
                    $ytdlpNuevo = $true
                    Bien ('yt-dlp instalado y verificado: ' + $nuevo)
                } else { Ojo 'No pude bajar yt-dlp.' }
            }
        }
        if ($ytdlp) {
            $c = Probar-Programa $ytdlp @('--version')
            if ($c -ne 0) { Ojo ('yt-dlp no responde bien (código ' + $c + ').') }
            else { $vy = (Get-Content -LiteralPath (Join-Path $env:TEMP 'moviola-prueba.out') -ErrorAction SilentlyContinue | Select-Object -First 1); Bien ('yt-dlp responde (versión ' + $vy + ').') }
            Resumir 'Bajar de YouTube (yt-dlp)' 'ok' $ytdlp
        } else { Resumir 'Bajar de YouTube (yt-dlp)' 'falta' 'no se pudo instalar' }
    }

    # ------------------------------------------------------------------------------------------------------- 5. WebView2
    Titulo '[5/6] La ventana (WebView2)'
    if ($SinWebView2) {
        Info 'Se omite (-SinWebView2).'
        Resumir 'Ventana (WebView2)' 'omitido' 'con -SinWebView2'
    } elseif (Hay-WebView2) {
        Bien 'WebView2 ya está (Windows 11 lo trae).'
        Resumir 'Ventana (WebView2)' 'ok' 'ya instalado'
    } else {
        Ojo 'Falta WebView2. Sin él Moviola se abre igual, pero en el navegador.'
        $listo = $false
        if ((Conexion) -and (Preguntar-SiNo 'Lo instalo ahora? (Windows puede pedir permiso de administrador)' $true)) {
            $wv = Join-Path $env:TEMP 'MicrosoftEdgeWebview2Setup.exe'
            if ((Descargar $WEBVIEW2_URL $wv) -and -not (Firma-De-Microsoft $wv)) {
                Ojo 'El instalador de WebView2 que bajé no tiene una firma válida de Microsoft: no lo ejecuto.'
                Remove-Item -LiteralPath $wv -Force -ErrorAction SilentlyContinue
            } elseif ((Test-Path -LiteralPath $wv) -and (Firma-De-Microsoft $wv)) {
                try { Start-Process -FilePath $wv -ArgumentList '/silent', '/install' -Wait | Out-Null } catch { Info 'Se canceló la instalación de WebView2.' }
                $listo = Hay-WebView2
            }
        }
        if ($listo) { Bien 'WebView2 instalado.'; Resumir 'Ventana (WebView2)' 'ok' 'instalado' }
        else { Ojo 'WebView2 no quedó instalado: Moviola va a abrirse en el navegador (funciona igual).'; Resumir 'Ventana (WebView2)' 'navegador' 'se abre en el navegador' }
    }

    # ------------------------------------------------------------------------------------------------------- 6. accesos y registro
    Titulo '[6/6] Accesos directos y Windows'
    $manifiesto = [ordered]@{
        version = $version; fecha = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'); destino = $Destino
        whisper = $(if ($whisperNuevo -and $whisperCarpetaPropia) { $Whisper } elseif ($anterior -and $anterior.PSObject.Properties['whisper']) { $anterior.whisper } else { '' })
        modelo = $(if ($modeloNuevo) { $modeloRuta } elseif ($anterior -and $anterior.PSObject.Properties['modelo']) { $anterior.modelo } else { '' })
        ytdlp = $(if ($ytdlpNuevo) { $ytdlp } elseif ($anterior -and $anterior.PSObject.Properties['ytdlp']) { $anterior.ytdlp } else { '' })
        accesos = (-not $SinAccesos)
    }
    if ($SinAccesos) {
        Info 'Se omiten los accesos directos y el registro en Windows (-SinAccesos).'
    } else {
        $pythonw = Join-Path $Destino 'python\pythonw.exe'
        $icono = Join-Path $Destino 'moviola.ico'
        $inicio = Join-Path ([Environment]::GetFolderPath('Programs')) 'Moviola'
        New-Item -ItemType Directory -Path $inicio -Force | Out-Null
        Nuevo-Acceso (Join-Path $inicio 'Moviola.lnk') $pythonw ('"' + (Join-Path $Destino 'app.py') + '"') $Destino $icono 'Editor de video y audio, local'
        Nuevo-Acceso (Join-Path $inicio 'Moviola (en el navegador).lnk') $pythonw ('"' + (Join-Path $Destino 'app.py') + '" --navegador') $Destino $icono 'Moviola en el navegador, si la ventana no abre'
        Nuevo-Acceso (Join-Path $inicio 'Desinstalar Moviola.lnk') (Join-Path $Destino 'Desinstalar-Moviola.bat') '' $Destino $icono 'Quita Moviola de esta PC'
        Bien ('Menú Inicio: ' + $inicio)
        if (-not $SinEscritorio -and (Preguntar-SiNo 'Pongo un acceso directo en el Escritorio?' $true)) {
            Nuevo-Acceso (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Moviola.lnk') $pythonw ('"' + (Join-Path $Destino 'app.py') + '"') $Destino $icono 'Editor de video y audio, local'
            Bien 'Escritorio: Moviola.lnk'
        }
        # "Aplicaciones instaladas" de Windows
        $tam = [int]((Get-ChildItem -LiteralPath $Destino -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1KB)
        $k = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Moviola'
        New-Item -Path $k -Force | Out-Null
        $uni = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Destino 'instalador\desinstalar.ps1') + '"'
        $valores = @{
            DisplayName = 'Moviola'; DisplayVersion = $version; Publisher = 'Diego Bertelli'; InstallLocation = $Destino
            DisplayIcon = $icono; UninstallString = $uni; URLInfoAbout = ''; Comments = 'Editor de video y audio, local (GNU GPL v3 o posterior)'
        }
        foreach ($n in $valores.Keys) { New-ItemProperty -Path $k -Name $n -Value $valores[$n] -PropertyType String -Force | Out-Null }
        New-ItemProperty -Path $k -Name EstimatedSize -Value $tam -PropertyType DWord -Force | Out-Null
        New-ItemProperty -Path $k -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null
        New-ItemProperty -Path $k -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null
        Bien 'Registrado en «Aplicaciones instaladas» de Windows (para desinstalarlo desde ahí).'
        # doble clic en un .moviola
        if (-not $SinAsociar) {
            $cl = 'HKCU:\Software\Classes'
            New-Item -Path "$cl\.moviola" -Force | Out-Null
            Set-ItemProperty -Path "$cl\.moviola" -Name '(default)' -Value 'Moviola.Proyecto'
            New-Item -Path "$cl\Moviola.Proyecto" -Force | Out-Null
            Set-ItemProperty -Path "$cl\Moviola.Proyecto" -Name '(default)' -Value 'Proyecto de Moviola'
            New-Item -Path "$cl\Moviola.Proyecto\DefaultIcon" -Force | Out-Null
            Set-ItemProperty -Path "$cl\Moviola.Proyecto\DefaultIcon" -Name '(default)' -Value $icono
            New-Item -Path "$cl\Moviola.Proyecto\shell\open\command" -Force | Out-Null
            Set-ItemProperty -Path "$cl\Moviola.Proyecto\shell\open\command" -Name '(default)' -Value ('"' + $pythonw + '" "' + (Join-Path $Destino 'app.py') + '" "%1"')
            Avisar-Al-Explorador
            Bien 'Los archivos .moviola se abren con doble clic.'
        }
    }
    New-Item -ItemType Directory -Path (Join-Path $Destino 'instalador') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'desinstalar.ps1') -Destination (Join-Path $Destino 'instalador\desinstalar.ps1') -Force
    [System.IO.File]::WriteAllText((Join-Path $Destino 'Desinstalar-Moviola.bat'),
        "@echo off`r`nchcp 65001 >nul`r`ntitle Desinstalar Moviola`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"%~dp0instalador\desinstalar.ps1`" %*`r`nif not `"%MOVIOLA_SIN_PAUSA%`"==`"1`" pause`r`n",
        (New-Object System.Text.UTF8Encoding($false)))
    [System.IO.File]::WriteAllText((Join-Path $Destino $MARCA), ($manifiesto | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))

    # ------------------------------------------------------------------------------------------------------- el final
    Titulo 'Qué quedó instalado'
    $python = Join-Path $Destino 'python\python.exe'
    Write-Host ''
    foreach ($r in $resumen) {
        $simbolo = switch ($r.estado) { 'ok' { '[ok]' } 'omitido' { '[--]' } 'navegador' { '[ok]' } default { '[!!]' } }
        $color = switch ($r.estado) { 'ok' { 'Green' } 'omitido' { 'Gray' } 'navegador' { 'Yellow' } default { 'Yellow' } }
        Write-Host ('  {0} {1,-28} {2}' -f $simbolo, $r.nombre, $r.detalle) -ForegroundColor $color
    }
    if ($avisos.Count -gt 0) {
        Write-Host ''
        Write-Host '  Cosas para revisar:' -ForegroundColor Yellow
        foreach ($a in $avisos) { Write-Host ('   - ' + $a) -ForegroundColor Yellow }
    }
    Write-Host ''
    if ($SinAccesos) { Write-Host '  Moviola se abre con ' -NoNewline }
    else { Write-Host '  Moviola se abre desde el menú Inicio (Moviola) o con ' -NoNewline }
    Write-Host (Join-Path $Destino 'Moviola.bat') -ForegroundColor White
    Write-Host ('  Registro de esta instalación: ' + $registro) -ForegroundColor Gray
    if (-not $Silencioso -and -not $SinSalida -and (Preguntar-SiNo 'Abro Moviola ahora?' $true)) {
        Start-Process -FilePath (Join-Path $Destino 'python\pythonw.exe') -ArgumentList ('"' + (Join-Path $Destino 'app.py') + '"') -WorkingDirectory $Destino
    }
    try { Stop-Transcript | Out-Null } catch { }
    exit 0
}
catch {
    Write-Host ''
    Write-Host ('  No se pudo instalar: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ('  Registro: ' + $registro) -ForegroundColor Gray
    try { Stop-Transcript | Out-Null } catch { }
    exit 1
}
