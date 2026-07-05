param(
    [string]$Destination,
    [switch]$AddToPath
)

$ErrorActionPreference = 'Stop'
$sourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath = Join-Path $sourceDir 'install.py'
$arguments = @($scriptPath)

if ($PSBoundParameters.ContainsKey('Destination')) {
    $arguments += @('--destination', $Destination)
}

if ($AddToPath) {
    $arguments += '--add-to-path'
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 @arguments
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python @arguments
}
else {
    throw 'Python was not found in PATH.'
}

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
