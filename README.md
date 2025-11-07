powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"


Step 1 allow cmd ps:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine
Allow All - [A]

Step 2
Enter virtual environment: .venv\Scripts\activate
