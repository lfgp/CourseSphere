$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$secretDirectory = Join-Path $projectRoot '.tools/docker'
$secretFile = Join-Path $secretDirectory 'metrics-token.txt'
New-Item -ItemType Directory -Path $secretDirectory -Force | Out-Null
if (-not (Test-Path -LiteralPath $secretFile)) {
    $randomBytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($randomBytes) } finally { $generator.Dispose() }
    $token = [Convert]::ToBase64String($randomBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    [System.IO.File]::WriteAllText($secretFile, $token)
}
$existingToken = [System.IO.File]::ReadAllText($secretFile).Trim()
if ($existingToken -notmatch '\A[A-Za-z0-9_-]{32,256}\z') {
    throw 'The local metrics secret is invalid; replace it with a random URL-safe token.'
}
Write-Host 'Docker metrics secret is ready in the ignored .tools/docker directory.'
