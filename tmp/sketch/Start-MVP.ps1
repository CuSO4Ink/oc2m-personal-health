$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$nodeExe = (Get-Command node -ErrorAction Stop).Source
$npmCli = Join-Path (Split-Path $nodeExe) 'node_modules\npm\bin\npm-cli.js'
if (-not (Test-Path -LiteralPath $npmCli)) { throw 'Please install Node.js 22.13+ with npm.' }
if (-not (Test-Path -LiteralPath 'node_modules\vinext')) {
    & $nodeExe $npmCli run install:ci
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
& $nodeExe $npmCli run build
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
$dbCheck = & $nodeExe --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --command "SELECT name FROM sqlite_master WHERE type='table' AND name='records'" --json
if ($LASTEXITCODE -ne 0) { throw 'Database check failed.' }
$dbRows = ($dbCheck -join "`n") | ConvertFrom-Json
if (-not $dbRows[0].results.Count) {
    & $nodeExe --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0000_massive_runaways.sql
    if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed.' }
}
Write-Host 'Open http://127.0.0.1:8787 in your browser. Keep this window open.'
& $nodeExe --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js dev --config dist/server/wrangler.json --local --persist-to .wrangler/state --ip 127.0.0.1 --port 8787 --inspector-port 0
