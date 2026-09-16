param(
    [string]$BindAddress = '127.0.0.1',
    [int]$Port = 8000,
    [switch]$NoReload
)

# 使用项目专用解释器启动 FastAPI，不自动启动或修改 MySQL 服务。
$ErrorActionPreference = 'Stop'
$backendDirectory = $PSScriptRoot
$projectPython = Join-Path $backendDirectory '.venv\Scripts\python.exe'
$environmentFile = Join-Path $backendDirectory '.env'

if (-not (Test-Path -LiteralPath $projectPython)) {
    throw '未找到项目虚拟环境，请先创建 backend/.venv 并安装 requirements.txt。'
}
if (-not (Test-Path -LiteralPath $environmentFile)) {
    throw '未找到 backend/.env，请复制 .env.example 并填写本机数据库配置。'
}

$serverArguments = @('-m', 'uvicorn', 'aidevops.main:app', '--host', $BindAddress, '--port', "$Port")
if (-not $NoReload) {
    $serverArguments += '--reload'
}

Push-Location -LiteralPath $backendDirectory
try {
    & $projectPython @serverArguments
    if ($LASTEXITCODE -ne 0) {
        throw "FastAPI 启动失败，退出码为 $LASTEXITCODE。"
    }
}
finally {
    Pop-Location
}
