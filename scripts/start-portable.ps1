$ErrorActionPreference='Stop'
$projectRoot=(Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$manifest=Get-Content -LiteralPath (Join-Path $projectRoot 'dist\latest.json') -Raw | ConvertFrom-Json
$executable=[IO.Path]::GetFullPath((Join-Path (Join-Path $projectRoot 'dist') $manifest.executable))
if (-not $executable.StartsWith($projectRoot+[IO.Path]::DirectorySeparatorChar) -or -not (Test-Path -LiteralPath $executable)) { throw 'Executável portátil não encontrado nesta pasta.' }
$runtime=Join-Path $projectRoot 'runtime'
Start-Process -FilePath $executable -ArgumentList @('--data-dir',('"'+$runtime+'"')) -WorkingDirectory $projectRoot
