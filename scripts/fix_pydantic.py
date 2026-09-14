import pathlib

# Pydantic v2: class-based Config -> model_config = ConfigDict(...)
edits = {
    "backend/api/brands.py": ("    class Config:\n        from_attributes = True",
                              "    model_config = {\"from_attributes\": True}"),
    "backend/api/alerts.py": ("    class Config:\n        from_attributes = True",
                              "    model_config = {\"from_attributes\": True}"),
    "backend/api/rag_monitor.py": ("    class Config:\n        from_attributes = True",
                                   "    model_config = {\"from_attributes\": True}"),
    "config/settings.py": ("    class Config:\n        env_file = \".env\"\n        env_file_encoding = \"utf-8\"\n        extra = \"ignore\"",
                           "    model_config = {\"env_file\": \".env\", \"env_file_encoding\": \"utf-8\", \"extra\": \"ignore\"}"),
}
for f, (old, new) in edits.items():
    p = pathlib.Path(f)
    src = p.read_text(encoding="utf-8", errors="replace")
    assert old in src, f"pattern missing in {f}"
    p.write_text(src.replace(old, new, 1), encoding="utf-8")
    print("fixed", f)
