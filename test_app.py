"""Simple test script to verify the FastAPI application structure is valid."""
import sys
import ast
import os

# Change to the backend directory to make imports work
backend_dir = r"C:\Users\asus\.cline\data\workspaces\chat\wind-forecast-dashboard\backend"
os.chdir(backend_dir)

# Verify app.py syntax
app_path = r"src\app.py"
with open(app_path) as f:
    try:
        ast.parse(f.read())
        print("✓ app.py syntax is valid")
    except SyntaxError as e:
        print(f"✗ app.py syntax error: {e}")
        sys.exit(1)

# Verify all service .py files exist and have valid syntax
service_files = [
    r"src\services\normalization.py",
    r"src\services\forecast_selection.py",
    r"src\services\metrics.py",
    r"src\services\matching.py",
]

for f in service_files:
    full_path = os.path.join(backend_dir, f)
    if os.path.exists(full_path):
        with open(full_path) as fh:
            try:
                ast.parse(fh.read())
                print(f"✗ {f} exists and syntax is valid")
            except SyntaxError as e:
                print(f"✗ {f} syntax error: {e}")
                sys.exit(1)
    else:
        print(f"✗ {f} not found")
        sys.exit(1)

# Verify elexon_client.py exists
client_path = r"src\api\elexon_client.py"
full_client_path = os.path.join(backend_dir, client_path)
if os.path.exists(full_client_path):
    with open(full_client_path) as fh:
        try:
            ast.parse(fh.read())
            print(f"✓ {client_path} exists and syntax is valid")
        except SyntaxError as e:
            print(f"✗ {client_path} syntax error: {e}")
            sys.exit(1)
else:
    print(f"✗ {client_path} not found")
    sys.exit(1)

# Verify requirements.txt exists
req_path = r"requirements.txt"
full_req_path = os.path.join(backend_dir, req_path)
if os.path.exists(full_req_path):
    print(f"✓ {req_path} exists")
else:
    print(f"✗ {req_path} not found")
    sys.exit(1)

# Verify app.py has the expected endpoints
with open(app_path) as f:
    content = f.read()
    required_endpoints = ["/api/health", "/api/overview", "/api/forecast-history"]
    for endpoint in required_endpoints:
        if endpoint in content:
            print(f"✓ Endpoint {endpoint} found in app.py")
        else:
            print(f"✗ Endpoint {endpoint} NOT found in app.py")
            sys.exit(1)

print(f"\nAll checks passed! Application structure is valid ({backend_dir})")