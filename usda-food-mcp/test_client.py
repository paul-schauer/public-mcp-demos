import subprocess
import json
import os

# Set the API key
os.environ["USDA_FDC_API_KEY"] = "test"

# Path to the python executable in the virtual environment
python_executable = "C:\\Code\\food-mcp\\.venv\\Scripts\\python.exe"

# Start the server
server_process = subprocess.Popen(
    [python_executable, "usda_fdc_mcp_server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding='utf-8'
)

# Create a request to call the search_foods tool
request = {
    "tool_name": "search_foods",
    "arguments": {"query": "cheese"}
}

# Send the request to the server
server_process.stdin.write(json.dumps(request) + "\n")
server_process.stdin.flush()

# Read the response from the server
response = server_process.stdout.readline()

# Print the response
print("Response:", response)

# Print any errors from the server
stderr_output = server_process.stderr.read()
print("Stderr:", stderr_output)

# Terminate the server
server_process.terminate()