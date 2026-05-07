@echo off
set IP=172.19.100.38
scp -r app.py templates requirements.txt .env qss@%IP%:/home/qss/qss-status-web/
ssh qss@%IP% "chmod 600 ~/qss-status-web/.env && sudo systemctl restart qss-status"
echo.
echo Deployed. Check http://%IP%:5000
pause
