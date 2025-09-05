# web/bridge.py
# Replace the body of run() to call your existing code.
# Example signatures supported by web/app.py: run({"text": "...", "file_path": "... or None"})
def run(payload: dict) -> dict:
    text = payload.get("text") or ""
    file_path = payload.get("file_path")
    # TODO: call your real function here, e.g.:
    # from my_module import process
    # result = process(text, file_path)
    # return {"result": result}
    return {"echo": text, "has_file": bool(file_path)}
