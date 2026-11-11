# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
<#
.SYNOPSIS
  Quita Moviola de esta PC: la carpeta del programa, los accesos directos y lo que se registró en Windows.

.DESCRIPTION
  Solo borra una carpeta que tenga la marca .moviola-instalado (la deja el instalador). Tus videos y tus proyectos (.moviola) no se tocan:
  están en otras carpetas. Lo que el instalador bajó aparte (whisper, el modelo, yt-dlp) se pregunta uno por uno, porque otros programas
  pueden usarlo; con -Silencioso se dejan.
#>
[CmdletBinding()]
param(
    [string]$Destino = (Join-Path $env:LOCALAPPDATA 'Programs\Moviola'),
    [switch]$Silencioso,
    [switch]$TodoLoBajado,
    [switch]$DesdeCopia
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$MARCA = '.moviola-instalado'

# El desinstalador vive dentro de la carpeta que va a borrar: se copia a TEMP y se sigue desde ahi.
if (-not $DesdeCopia) {
    $propia = [System.IO.Path]::GetFullPath($PSScriptRoot)
    $copia = Join-Path $env:TEMP ('moviola-desinstalar-' + [guid]::NewGuid().ToString('N') + '.ps1')
    Copy-Item -LiteralPath $PSCommandPath -Destination $copia -Force
    # si lo ejecutan desde la carpeta instalada, esa es la que hay que quitar
    if (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $propia) $MARCA)) { $Destino = Split-Path -Parent $propia }
    $argumentos = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $copia, '-DesdeCopia', '-Destino', $Destino)
    if ($Silencioso) { $argumentos += '-Silencioso' }
    if ($TodoLoBajado) { $argumentos += '-TodoLoBajado' }
    & powershell.exe @argumentos
    $codigo = $LASTEXITCODE
    Remove-Item -LiteralPath $copia -Force -ErrorAction SilentlyContinue
    exit $codigo
}

function Preguntar-SiNo([string]$texto, [bool]$defecto) {
    if ($Silencioso) { return $defecto }
    $sufijo = if ($defecto) { '[S/n]' } else { '[s/N]' }
    try { $r = Read-Host ('  ' + $texto + ' ' + $sufijo) } catch { return $defecto }
    if ([string]::IsNullOrWhiteSpace($r)) { return $defecto }
    return ($r.Trim().ToLower() -in @('s', 'si', 'sí', 'y', 'yes'))
}

try {
    $Destino = [System.IO.Path]::GetFullPath($Destino)
    Write-Host ''
    Write-Host '  MOVIOLA - desinstalador' -ForegroundColor Magenta
    $marca = Join-Path $Destino $MARCA
    if (-not (Test-Path -LiteralPath $marca)) {
        throw ('En ' + $Destino + ' no hay una instalación de Moviola hecha por este instalador (falta ' + $MARCA + '): no borro nada.')
    }
    $m = $null
    try { $m = Get-Content -LiteralPath $marca -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
    Write-Host ('  Se va a quitar Moviola de ' + $Destino) -ForegroundColor Gray
    Write-Host '  (tus videos y tus proyectos .moviola no se tocan)' -ForegroundColor Gray
    if (-not (Preguntar-SiNo 'Sigo?' $true)) { Write-Host '  No se quitó nada.'; exit 0 }

    $corren = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($Destino, [StringComparison]::OrdinalIgnoreCase) })
    if ($corren.Count -gt 0) {
        Write-Host '  Moviola está abierto.' -ForegroundColor Yellow
        if (Preguntar-SiNo 'Lo cierro ahora (se pierde lo que no se haya guardado)?' $false) {
            $corren | ForEach-Object { try { $_.Kill() } catch { } }
            Start-Sleep -Seconds 2
        } else { throw 'Cerrá Moviola y volvé a ejecutar el desinstalador.' }
    }

    # accesos directos
    foreach ($ruta in @((Join-Path ([Environment]::GetFolderPath('Programs')) 'Moviola'))) {
        if (Test-Path -LiteralPath $ruta) { Remove-Item -LiteralPath $ruta -Recurse -Force; Write-Host '  [ok] Menú Inicio' -ForegroundColor Green }
    }
    $esc = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Moviola.lnk'
    if (Test-Path -LiteralPath $esc) { Remove-Item -LiteralPath $esc -Force; Write-Host '  [ok] Escritorio' -ForegroundColor Green }

    # registro de Windows (solo lo que puso el instalador, y solo si apunta a ESTA carpeta)
    $k = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Moviola'
    if (Test-Path -LiteralPath $k) {
        $loc = (Get-ItemProperty -LiteralPath $k -ErrorAction SilentlyContinue).InstallLocation
        if (-not $loc -or ([System.IO.Path]::GetFullPath($loc).TrimEnd('\') -eq $Destino.TrimEnd('\'))) {
            Remove-Item -LiteralPath $k -Recurse -Force
            Write-Host '  [ok] Quitado de «Aplicaciones instaladas»' -ForegroundColor Green
        }
    }
    $cmd = 'HKCU:\Software\Classes\Moviola.Proyecto\shell\open\command'
    if (Test-Path -LiteralPath $cmd) {
        $valor = (Get-ItemProperty -LiteralPath $cmd).'(default)'
        if ($valor -and $valor.IndexOf($Destino, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            Remove-Item -LiteralPath 'HKCU:\Software\Classes\Moviola.Proyecto' -Recurse -Force
            if (Test-Path -LiteralPath 'HKCU:\Software\Classes\.moviola') { Remove-Item -LiteralPath 'HKCU:\Software\Classes\.moviola' -Recurse -Force }
            Write-Host '  [ok] Los .moviola ya no se abren con doble clic' -ForegroundColor Green
        }
    }

    # lo que el instalador bajó aparte
    $extras = @()
    if ($m) {
        if ($m.PSObject.Properties['whisper'] -and $m.whisper -and (Test-Path -LiteralPath (Join-Path $m.whisper 'whisper-cli.exe'))) { $extras += , @('whisper-cli (whisper.cpp)', $m.whisper, 'carpeta') }
        if ($m.PSObject.Properties['modelo'] -and $m.modelo -and (Test-Path -LiteralPath $m.modelo)) { $extras += , @(('el modelo de whisper ' + (Split-Path -Leaf $m.modelo)), $m.modelo, 'archivo') }
    }
    foreach ($e in $extras) {
        $quitar = $TodoLoBajado
        if (-not $quitar) { $quitar = Preguntar-SiNo ('También quito ' + $e[0] + ', que bajó el instalador? Otros programas pueden usarlo.') $false }
        if ($quitar) {
            Remove-Item -LiteralPath $e[1] -Recurse:($e[2] -eq 'carpeta') -Force
            Write-Host ('  [ok] Quitado ' + $e[0]) -ForegroundColor Green
        } else { Write-Host ('  [--] Se deja ' + $e[0] + ' en ' + $e[1]) -ForegroundColor Gray }
    }
    # yt-dlp: si el instalador lo bajó, vive en la carpeta de Moviola y se va con ella

    # ajustes, registro y caché (copias livianas para reproducir): viven en el perfil, no en la carpeta del programa
    $datos = Join-Path $env:LOCALAPPDATA 'Moviola'
    if ((Test-Path -LiteralPath $datos) -and ([System.IO.Path]::GetFullPath($datos).TrimEnd('\') -ne $Destino.TrimEnd('\'))) {
        $quitar = $TodoLoBajado
        if (-not $quitar) { $quitar = Preguntar-SiNo 'También borro tus ajustes y la caché de Moviola? (si vas a reinstalar, conviene dejarlos)' $false }
        if ($quitar) { Remove-Item -LiteralPath $datos -Recurse -Force; Write-Host '  [ok] Ajustes y caché' -ForegroundColor Green }
        else { Write-Host ('  [--] Se dejan los ajustes y la caché en ' + $datos) -ForegroundColor Gray }
    }

    # la carpeta del programa
    Set-Location -Path $env:TEMP
    Remove-Item -LiteralPath $Destino -Recurse -Force
    Write-Host '  [ok] Carpeta del programa' -ForegroundColor Green
    Write-Host ''
    Write-Host '  Moviola se quitó de esta PC.' -ForegroundColor Cyan
    exit 0
}
catch {
    Write-Host ''
    Write-Host ('  No se pudo desinstalar: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
