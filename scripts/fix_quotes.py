import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix broken onclick quotes for saveAPI and deleteAPI
content = content.replace(
    """onclick=\"saveAPI(''+p.id+'')\"""",
    """onclick=\"saveAPI('\"+p.id+\"')\""""
)
content = content.replace(
    """onclick=\"deleteAPI(''+p.id+'')\"""",
    """onclick=\"deleteAPI('\"+p.id+\"')\""""
)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed JavaScript quote escaping")
