$ErrorActionPreference = 'Stop'
$projectDirectory = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$toolsDirectory = Join-Path $projectDirectory '.tools'
$runtimeDirectory = Join-Path $toolsDirectory 'java21'
$firebaseCli = Join-Path $projectDirectory 'node_modules/firebase-tools/lib/bin/firebase.js'

if (-not (Test-Path -LiteralPath $firebaseCli -PathType Leaf)) {
    throw 'Execute npm install na raiz do repositorio antes de iniciar os emuladores.'
}

$javaExecutable = $null
if (Test-Path -LiteralPath $runtimeDirectory -PathType Container) {
    $javaExecutable = Get-ChildItem -LiteralPath $runtimeDirectory -Filter 'java.exe' -File -Recurse |
        Select-Object -First 1 -ExpandProperty FullName
}

if (-not $javaExecutable) {
    Write-Host 'Baixando Java 21 portatil para .tools (somente na primeira execucao)...'
    New-Item -ItemType Directory -Path $toolsDirectory -Force | Out-Null
    $runtimeAssets = Invoke-RestMethod -Uri 'https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&heap_size=normal&image_type=jre&jvm_impl=hotspot&os=windows&vendor=eclipse'
    $runtimePackage = $runtimeAssets[0].binary.package
    $runtimeArchive = Join-Path $toolsDirectory 'temurin21.zip'
    Invoke-WebRequest -Uri $runtimePackage.link -OutFile $runtimeArchive -UseBasicParsing
    $downloadChecksum = (Get-FileHash -LiteralPath $runtimeArchive -Algorithm SHA256).Hash
    if ($downloadChecksum -ne $runtimePackage.checksum) {
        throw 'O checksum do Java baixado difere do publicado pela Adoptium.'
    }
    Expand-Archive -LiteralPath $runtimeArchive -DestinationPath $runtimeDirectory -Force
    $javaExecutable = Get-ChildItem -LiteralPath $runtimeDirectory -Filter 'java.exe' -File -Recurse |
        Select-Object -First 1 -ExpandProperty FullName
    if (-not $javaExecutable) {
        throw 'O runtime Java baixado nao contem bin/java.exe.'
    }
}

$env:JAVA_HOME = Split-Path -Parent (Split-Path -Parent $javaExecutable)
$env:PATH = "$(Split-Path -Parent $javaExecutable);$env:PATH"
$env:FIREBASE_EMULATORS_PATH = Join-Path $toolsDirectory 'firebase-emulators'
$dataDirectory = Join-Path $projectDirectory '.firebase-data'
$emulatorArguments = @(
    $firebaseCli,
    'emulators:start',
    '--project', 'demo-coursesphere',
    '--only', 'auth,database',
    '--config', (Join-Path $projectDirectory 'firebase.json'),
    '--export-on-exit', $dataDirectory
)
if (Test-Path -LiteralPath (Join-Path $dataDirectory 'firebase-export-metadata.json')) {
    $emulatorArguments += @('--import', $dataDirectory)
}

& node @emulatorArguments
exit $LASTEXITCODE
