Set-Location $PSScriptRoot

$puerto = 27018
$carpetaDatos = Join-Path $env:LOCALAPPDATA "SaborLocal\datos_mongo"
$env:MONGO_URI = "mongodb://127.0.0.1:$puerto"
$env:MONGO_DB  = "saborlocal_web"
Remove-Item Env:SABORLOCAL_MOCK -ErrorAction SilentlyContinue

function Test-Puerto([int]$p) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $r = $c.BeginConnect("127.0.0.1", $p, $null, $null)
        $ok = $r.AsyncWaitHandle.WaitOne(500)
        $conectado = $ok -and $c.Connected
        $c.Close()
        return $conectado
    } catch { return $false }
}

# 1) Python
$python = $null
foreach ($cmd in @("python", "py")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        & $cmd --version 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $python = $cmd; break }
    }
}
if (-not $python) {
    Write-Host "No se encontró Python. Instálalo desde python.org (marca 'Add Python to PATH')" -ForegroundColor Red
    exit 1
}

# 2) Librerías
Write-Host "Instalando librerías (solo tarda la primera vez)..." -ForegroundColor Cyan
& $python -m pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "No se pudieron instalar las librerías. Revisa tu conexión a internet." -ForegroundColor Red
    exit 1
}

# 3) Buscar mongod.exe
$mongod = $null
$cmd = Get-Command mongod -ErrorAction SilentlyContinue
if ($cmd) { $mongod = $cmd.Source }
if (-not $mongod) {
    $hallado = Get-ChildItem "C:\Program Files\MongoDB\Server\*\bin\mongod.exe" -ErrorAction SilentlyContinue |
               Sort-Object FullName -Descending | Select-Object -First 1
    if ($hallado) { $mongod = $hallado.FullName }
}

if (-not $mongod) {
    Write-Host ""
    Write-Host "No esta MongoDB instalado en este equipo." -ForegroundColor Yellow
    Write-Host "MODO DEMO (base en memoria): los datos se borran al cerrarla." -ForegroundColor Yellow
    Write-Host "Para guardar datos instala MongoDB Community Server (mongodb.com/try/download/community)" -ForegroundColor Yellow
    $env:SABORLOCAL_MOCK = "1"
} else {
    # 4) Encender SU propia base de datos (si no está ya encendida)
    New-Item -ItemType Directory -Force $carpetaDatos | Out-Null
    if (-not (Test-Puerto $puerto)) {
        Write-Host "Encendiendo la base de datos nueva en el puerto $puerto ..." -ForegroundColor Cyan
        $argumentos = @("--dbpath", "`"$carpetaDatos`"", "--port", "$puerto", "--bind_ip", "127.0.0.1")
        Start-Process -FilePath $mongod -ArgumentList $argumentos -WindowStyle Minimized
        $listo = $false
        for ($i = 0; $i -lt 40; $i++) {
            Start-Sleep -Milliseconds 500
            if (Test-Puerto $puerto) { $listo = $true; break }
        }
        if (-not $listo) {
            Write-Host "La base de datos no arrancó." -ForegroundColor Red
            exit 1
        }
    }
    Write-Host "Base de datos lista: saborlocal_web  (mongodb://127.0.0.1:$puerto)" -ForegroundColor Green
}

# 5) Abrir el navegador y correr la app
Write-Host ""
Write-Host "Abre http://127.0.0.1:5000 en el navegador. Para detener la app presiona Ctrl + C." -ForegroundColor Green
Start-Process "http://127.0.0.1:5000"
& $python app.py
