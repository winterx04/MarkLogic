powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"


allow cmd ps: (Use this command if cmd policy reject uv)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine
Allow All - [A]

If you see “running scripts is disabled”
PowerShell blocks scripts by default.
Run this once:

Set-ExecutionPolicy RemoteSigned -Scope CurrentUser       then         Y




🚀 1. Install uv
If you haven’t already:
pip install uv || Or (recommended official way): curl -Ls https://astral.sh/uv/install.sh | sh

✅ Step 1.1: Verify installation
Run:
pip show uv

Look for something like: Location: C:\Users\YourName\AppData\Local\Programs\Python\PythonXX\Lib\site-packages

Now we need the Scripts folder, usually:
C:\Users\YourName\AppData\Local\Programs\Python\PythonXX\Scripts

🛠️ Step 1.2: Add to PATH (Windows)
Search: Environment Variables
Click: Edit the system environment variables
Open: Environment Variables
Under User variables → Path → Edit
Add: 
C:\Users\YourName\AppData\Local\Programs\Python\PythonXX\Scripts

Restart terminal

🧪 Step 1.3: Test
uv --version

2. After installing UV
- Just use "uv sync" to use the given "pyproject.toml + uv.lock"

3. Run the app with "uv run app.py"

----------------------------------------------------------------------------------------------------------------------------------------------
DATABASE
1. Install database PostgreSQL (pgAdmin)
2. Install database from Google Drive https://drive.google.com/file/d/1AsOWa-jgXIl-NDpgoJIev3-gROqHFXMQ/view?usp=sharing
3. Once open pgAdmin, create a database and name it "Marklogic"
4. Right click the created database and click on "Restore"
5. In General tab, It shows you "Custom or Tar" change it to "Plain"
6. On Filename, when you click on it, above your "Open" button change the "BACKUP FILE.backup" to "All File"
7. Once selected Marklogic database file, click "Restore".