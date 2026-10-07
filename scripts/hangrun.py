import importlib.util,sys
spec=importlib.util.spec_from_file_location('m',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.API='http://127.0.0.1:61041'
print('calling mint_token with no server response...')
m.mint_token('jwt','2')
