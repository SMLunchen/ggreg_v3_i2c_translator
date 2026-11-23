# Regenerates schematic + PCB from design.py, runs ERC/DRC and exports all
# fabrication data.  Usage:  powershell -File hardware\gen\build.ps1
$ErrorActionPreference = "Stop"
$kicad = "C:\Program Files\KiCad\9.0\bin"
$py    = Join-Path $kicad "python.exe"
$cli   = Join-Path $kicad "kicad-cli.exe"
$hw    = Split-Path -Parent $PSScriptRoot
$name  = "ggreg_i2c_translator"
$sch   = Join-Path $hw "$name.kicad_sch"
$pcb   = Join-Path $hw "$name.kicad_pcb"
$fab   = Join-Path $hw "fab"
$doc   = Join-Path $hw "doc"
$gerb  = Join-Path $fab "gerber"

function Invoke-Step($what, [scriptblock]$cmd) {
    Write-Host "== $what"
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" }
}

if (Test-Path $fab) { Remove-Item -Recurse -Force $fab }
New-Item -ItemType Directory -Force $gerb, $doc | Out-Null

Invoke-Step "generate schematic" { & $py (Join-Path $PSScriptRoot "gen_sch.py") }
Invoke-Step "generate PCB"       { & $py (Join-Path $PSScriptRoot "gen_pcb.py") }
Invoke-Step "ERC" { & $cli sch erc --severity-all --exit-code-violations -o (Join-Path $doc "erc.rpt") $sch }
Invoke-Step "DRC" { & $cli pcb drc --schematic-parity --severity-all --exit-code-violations -o (Join-Path $doc "drc.rpt") $pcb }

Invoke-Step "schematic PDF" { & $cli sch export pdf -o (Join-Path $doc "schematic.pdf") $sch }
Invoke-Step "render top"    { & $cli pcb render --side top --width 1600 --height 1250 --zoom 0.9 -o (Join-Path $doc "render_top.png") $pcb }
Invoke-Step "render bottom" { & $cli pcb render --side bottom --width 1600 --height 1250 --zoom 0.9 -o (Join-Path $doc "render_bottom.png") $pcb }

Invoke-Step "gerbers" { & $cli pcb export gerbers -o "$gerb\" --layers "F.Cu,B.Cu,F.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts" --subtract-soldermask $pcb }
Invoke-Step "drill"   { & $cli pcb export drill -o "$gerb\" --format excellon --excellon-separate-th $pcb }
Invoke-Step "positions" { & $cli pcb export pos -o (Join-Path $fab "positions.csv") --format csv --units mm --side front --exclude-dnp $pcb }
Invoke-Step "BOM" { & $cli sch export bom -o (Join-Path $fab "bom.csv") --fields 'Reference,Value,Footprint,${QUANTITY},${DNP}' --labels 'Refs,Value,Footprint,Qty,DNP' --group-by 'Value,Footprint,${DNP}' $sch }

$zip = Join-Path $fab "gerber_$name.zip"
Compress-Archive -Path (Join-Path $gerb "*") -DestinationPath $zip -Force
Write-Host "done: $zip"
