@echo off
echo.
echo  ====================================
echo   DescriGeek — VR Thetford
echo  ====================================
echo.

cd /d "%~dp0"

:: Vérifier si l'environnement virtuel existe
if not exist "venv\Scripts\activate.bat" (
    echo  Creation de l'environnement virtuel...
    python -m venv venv
    echo  Installation des dependances...
    venv\Scripts\pip install -r requirements.txt
    echo.
)

echo  Demarrage de l'application...
echo  Ouvrez votre navigateur a : http://localhost:8000
echo  Connexion : admin / admin123
echo.
echo  Appuyez sur Ctrl+C pour arreter.
echo.

venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
