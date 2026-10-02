import sys

def find_matching_brace(s, start_pos):
    """
    Find the matching closing brace for an opening brace at start_pos.
    Assumes s[start_pos] == '{'
    Returns the index of the matching closing brace, or -1 if not found.
    """
    stack = 0
    for i in range(start_pos, len(s)):
        if s[i] == '{':
            stack += 1
        elif s[i] == '}':
            stack -= 1
            if stack == 0:
                return i
    return -1

with open('src/index.ts', 'r') as f:
    content = f.read()

# Find the fetch function signature
signature = "async fetch(req: Request): Promise<Response> {"
sig_index = content.find(signature)
if sig_index == -1:
    print("Error: Could not find fetch function signature")
    sys.exit(1)

# The opening brace of the function is at the end of the signature
opening_brace_index = sig_index + len(signature) - 1  # because the signature includes the opening brace at the end
if content[opening_brace_index] != '{':
    print("Error: Expected '{' at the end of the signature")
    sys.exit(1)

# Find the matching closing brace for the function
closing_brace_index = find_matching_brace(content, opening_brace_index)
if closing_brace_index == -1:
    print("Error: Could not find matching closing brace for fetch function")
    sys.exit(1)

# Extract the function body (between the braces)
function_body = content[opening_brace_index+1:closing_brace_index]

# Prepare the new function body with try-catch
new_body = (
    "\n  try {\n" +
    function_body +
    "\n  } catch (err) {\n    return Response.json({\n      success: false,\n      error: err instanceof Error ? err.message : 'Internal server error'\n    }, { status: 500 });\n  }\n"
)

# Replace the old function body with the new one
new_content = (
    content[:opening_brace_index+1] +
    new_body +
    content[closing_brace_index:]
)

# Write back
with open('src/index.ts', 'w') as f:
    f.write(new_content)

print("Successfully wrapped fetch function in try-catch.")
