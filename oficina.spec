# -*- mode: python ; coding: utf-8 -*-
# Empaquetado para Windows (y Linux): pyinstaller --noconfirm oficina.spec
# Resultado en dist/MineOffice/ (carpeta que se comprime y se reparte).
a = Analysis(
    ["oficina_app.py"],
    pathex=["."],
    datas=[
        ("index.html", "."),
        ("lib", "lib"),
        ("rooms", "rooms"),
        ("vendor", "vendor"),
        ("tools/jefe.py", "tools"),
        ("LICENSE", "."),
    ],
    hiddenimports=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MineOffice",
    console=False,          # con consola: los errores se ven. Cámbialo a False cuando esté probado.
)
coll = COLLECT(exe, a.binaries, a.datas, name="MineOffice")
