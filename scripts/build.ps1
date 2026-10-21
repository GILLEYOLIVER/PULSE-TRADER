param([ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Name='PulseTrader')
$ErrorActionPreference='Stop'
$projectRoot=(Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
Set-Location -LiteralPath $projectRoot
$buildPython=Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) { throw 'Execute scripts\install.ps1 -Ui antes de compilar.' }
& $buildPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências de empacotamento.' }
$sourceCommit=(& git rev-parse HEAD)
$shortCommit=(& git rev-parse --short HEAD)
$distRoot=[IO.Path]::GetFullPath((Join-Path $projectRoot ('dist\'+$shortCommit)))
$workRoot=[IO.Path]::GetFullPath((Join-Path $projectRoot 'build'))
if (-not $distRoot.StartsWith($projectRoot+[IO.Path]::DirectorySeparatorChar) -or -not $workRoot.StartsWith($projectRoot+[IO.Path]::DirectorySeparatorChar)) { throw 'Saída fora da pasta do projeto.' }
$bundle=Join-Path $distRoot $Name
$existingData=Join-Path $bundle 'runtime'
if ((Test-Path -LiteralPath $existingData) -and (Get-ChildItem -LiteralPath $existingData -Force | Select-Object -First 1)) { throw 'Esta versão já tem dados runtime. Preserve a pasta existente e construa uma nova versão/commit.' }
& $buildPython -m PyInstaller --noconfirm --onedir --windowed --name $Name --collect-all customtkinter --collect-all tzdata --exclude-module numpy --exclude-module matplotlib --exclude-module pytest --distpath $distRoot --workpath $workRoot --specpath $workRoot main.py
if ($LASTEXITCODE -ne 0) { throw 'Falha ao construir o executável.' }
Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination $bundle
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs') -Destination $bundle -Recurse -Force
$manifest=[ordered]@{name=$Name;mode='PAPER';sourceCommit=$sourceCommit;builtAt=(Get-Date).ToUniversalTime().ToString('o');sqlite='embedded';dataDirectory='runtime beside executable'}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $bundle 'build-manifest.json') -Encoding utf8
$testReport=Join-Path $projectRoot 'reports\portable-smoke.json'
$executable=Join-Path $bundle ($Name+'.exe')
$testProcess=Start-Process -FilePath $executable -ArgumentList @('--smoke-test','--output',('"'+$testReport+'"')) -PassThru -Wait -WindowStyle Hidden
if ($testProcess.ExitCode -ne 0) { throw ('Falha no teste do executável; consulte '+$testReport) }
$test=Get-Content -LiteralPath $testReport -Raw | ConvertFrom-Json
if (-not $test.ok -or -not $test.frozen) { throw 'O teste não confirmou o executável empacotado.' }
$portableZip=Join-Path $distRoot ($Name+'-Windows-Portable.zip')
Compress-Archive -Path (Join-Path $bundle '*') -DestinationPath $portableZip -Force
Get-FileHash -LiteralPath $executable,$portableZip -Algorithm SHA256
$latest=[ordered]@{sourceCommit=$sourceCommit;executable=($shortCommit+'\'+$Name+'\'+$Name+'.exe');portableZip=($shortCommit+'\'+$Name+'-Windows-Portable.zip')}
$latest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $projectRoot 'dist\latest.json') -Encoding utf8
Write-Output ('Pronto: '+$executable)
Write-Output 'Os dados serão criados em runtime ao lado do executável. SQLite já está incluído; mantenha a pasta inteira.'
