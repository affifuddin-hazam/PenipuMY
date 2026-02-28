import py_compile
try:
    py_compile.compile(r'c:\Users\Desktop\AppData\Local\Programs\Python\Python38-32\PenipuMYV2\PDC\admin_dashboard.py', doraise=True)
    print('SYNTAX OK')
except py_compile.PyCompileError as e:
    print(f'SYNTAX ERROR: {e}')
