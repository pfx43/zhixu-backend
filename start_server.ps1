$env:PYTHONPATH = "c:\zhixu-backend\zhishi-master\backend"
$pythonCode = @"
import sys
sys.path.insert(0, r'c:\zhixu-backend\zhishi-master\backend')
import uvicorn
uvicorn.run('server:app', host='0.0.0.0', port=8765)
"@
Start-Process -NoNewWindow -FilePath "C:\Program Files\Python312\python.exe" -ArgumentList "-c", $pythonCode -RedirectStandardOutput "C:\zhixu-backend\server.log" -RedirectStandardError "C:\zhixu-backend\server_error.log"
Write-Host "Server started in background. PID check..."
Start-Sleep 2
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select State, LocalPort, OwningProcess
