import sys
import re

with open('src/index.ts', 'r') as f:
    content = f.read()

# We want to wrap the fetch function in a try-catch.
# The pattern: export default { ... async fetch(req: Request): Promise<Response> { ... } ... }
// We'll replace the fetch function with a try-catch version.

# We'll use a regex to find the fetch function inside the export default block.
# But note: the file might have other functions? We'll assume the fetch function is the only one in the export default.

# Let's split the content into three parts: before export default, the export default block, and after.
# However, the file is just the export default block and nothing else? Let's check.

# Actually, the file starts with a comment and then the export default.
# We'll find the export default { and then the matching }.

# We'll do a simple brace matching for the export default block.

def find_matching_brace(s, start):
    """Find the matching closing brace for an opening brace at index start.
    Assumes s[start] == '{'
    Returns the index of the matching closing brace, or -1 if not found.
    """
    stack = 0
    for i in range(start, len(s)):
        if s[i] == '{':
            stack += 1
        elif s[i] == '}':
            stack -= 1
            if stack == 0:
                return i
    return -1

# Find the start of the export default block.
export_default_match = re.search(r'export default\s*{', content)
if not export_default_match:
    print("Could not find 'export default {'")
    sys.exit(1)

export_default_start = export_default_match.start()
# The opening brace is at the end of the match.
opening_brace_index = export_default_match.end() - 1  # because the match includes the '{'

# Find the matching closing brace for the export default block.
closing_brace_index = find_matching_brace(content, opening_brace_index)
if closing_brace_index == -1:
    print("Could not find matching closing brace for export default block")
    sys.exit(1)

# Now we have the export default block: from export_default_start to closing_brace_index+1
# Let's extract the inner part (without the outer braces).
inner = content[opening_brace_index+1:closing_brace_index]

# Now we need to find the fetch function in the inner part.
# We'll look for the pattern: async fetch(req: Request): Promise<Response> {
fetch_match = re.search(r'async\s+fetch\s*\(\s*req\s*:\s*Request\s*\)\s*:\s*Promise\s*<\s*Response\s*>\s*{', inner)
if not fetch_match:
    print("Could not find fetch function")
    sys.exit(1)

# The start of the fetch function in the inner string.
fetch_start_inner = fetch_match.start()
# The opening brace of the fetch function is at the end of the match.
fetch_opening_brace_inner = fetch_match.end() - 1

# Now we need to find the matching closing brace for the fetch function.
fetch_closing_brace_inner = find_matching_brace(inner, fetch_opening_brace_inner)
if fetch_closing_brace_inner == -1:
    print("Could not find matching closing brace for fetch function")
    sys.exit(1)

# Now we have the fetch function body: from fetch_opening_brace_inner+1 to fetch_closing_brace_inner
fetch_body_inner = inner[fetch_opening_brace_inner+1:fetch_closing_brace_inner]

# We will replace the fetch function with:
#   async fetch(req: Request): Promise<Response> {
//     try {
//       [original body]
//     } catch (err) {
//       return Response.json({
//         success: false,
//         error: err instanceof Error ? err.message : 'Internal server error'
//       }, { status: 500 });
//     }
//   }

new_fetch = f'''async fetch(req: Request): Promise<Response> {{
  try {{
{fetch_body_inner}
  }} catch (err) {{
    return Response.json({{
      success: false,
      error: err instanceof Error ? err.message : 'Internal server error'
    }}, {{ status: 500 }});
  }}
}}'''

# Now we need to replace the old fetch function in the inner string with the new one.
# We'll replace from fetch_start_inner to fetch_closing_brace_inner+1 (to include the closing brace).
new_inner = inner[:fetch_start_inner] + new_fetch + inner[fetch_closing_brace_inner+1:]

# Now we need to put the new inner back into the content.
new_content = content[:opening_brace_index+1] + new_inner + content[closing_brace_index:]

# Write back
with open('src/index.ts', 'w') as f:
    f.write(new_content)

print("Successfully wrapped fetch function in try-catch.")
