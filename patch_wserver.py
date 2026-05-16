import re

with open("web/wserver.py", "r") as f:
    content = f.read()

route_code = r"""@app.get("/app/miniapp", response_class=HTMLResponse)
async def miniapp(request: Request):
    return templates.TemplateResponse(request, "miniapp.html")

@app.get("/", response_class=HTMLResponse)"""

content = re.sub(r"@app\.get\(\"/\", response_class=HTMLResponse\)", route_code, content)

with open("web/wserver.py", "w") as f:
    f.write(content)
